package auth

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	usageStreamKey = "usage:events"
	usageMaxLen    = 1_000_000
)

// UsageEmitter writes billing events to the Redis Stream consumed by
// the Temporal UsageConsumerWorkflow. Same stream + schema as the Python
// emitter (ee/usage/services/emitter.py).
type UsageEmitter struct {
	rdb *redis.Client
	pg  *pgxpool.Pool
	log *slog.Logger
}

// NewUsageEmitter creates an emitter. Returns nil if rdb is nil (disabled).
// pg (read pool) resolves the org's tracing billing mode; nil → storage default.
func NewUsageEmitter(rdb *redis.Client, pg *pgxpool.Pool, log *slog.Logger) *UsageEmitter {
	if rdb == nil {
		return nil
	}
	return &UsageEmitter{rdb: rdb, pg: pg, log: log}
}

// Namespace for deterministic billing event_ids (re-poll → same id → consumer dedups).
var billingDedupNS = uuid.MustParse("a7c3e1f0-5d29-4b6a-8c14-9f2b0e6d3a71")

// billingEventID is deterministic per (dedupKey, eventType) so re-polls dedup;
// empty dedupKey → random id (SDK batches don't re-poll).
func billingEventID(dedupKey, eventType string) string {
	if dedupKey == "" {
		return uuid.New().String()
	}
	return uuid.NewSHA1(billingDedupNS, []byte(eventType+":"+dedupKey)).String()
}

// EmitIngestion records usage for the ONE dimension the org is billed on,
// resolved from its tracing_billing_mode (mirrors Python emit_span_ingestion_usage):
// storage mode → observe_add (bytes); events mode → tracing_event (traces+spans).
// Emitting both would double-bill. Non-empty dedupKey → deterministic event_ids
// so re-exports bill once. Fire-and-forget; errors logged, not returned.
func (u *UsageEmitter) EmitIngestion(orgID string, numTraces, numSpans int, payloadBytes int64, dedupKey string) {
	if u == nil {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	now := time.Now().UTC().Format(time.RFC3339)

	if tracingBillingMode(ctx, u.rdb, u.pg, u.log, orgID) == "storage" {
		if payloadBytes > 0 {
			u.xadd(ctx, map[string]any{
				"event_id":   billingEventID(dedupKey, "observe_add"),
				"org_id":     orgID,
				"event_type": "observe_add",
				"timestamp":  now,
				"amount":     strconv.FormatInt(payloadBytes, 10),
				"properties": fmt.Sprintf(`{"spans":%d,"source":"fi-collector"}`, numSpans),
			})
		}
		return
	}

	// events mode: bill traces+spans; span storage is not billed here, so
	// payloadBytes is intentionally ignored.
	tracingUnits := numTraces + numSpans
	if tracingUnits > 0 {
		u.xadd(ctx, map[string]any{
			"event_id":   billingEventID(dedupKey, "tracing_event"),
			"org_id":     orgID,
			"event_type": "tracing_event",
			"timestamp":  now,
			"amount":     strconv.Itoa(tracingUnits),
			"properties": fmt.Sprintf(`{"traces":%d,"source":"fi-collector"}`, tracingUnits),
		})
	}
}

func (u *UsageEmitter) xadd(ctx context.Context, fields map[string]any) {
	err := u.rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: usageStreamKey,
		MaxLen: usageMaxLen,
		Approx: true,
		Values: fields,
	}).Err()
	if err != nil {
		u.log.Warn("usage event emit failed", "err", err)
	}
}
