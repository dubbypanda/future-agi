package auth

import (
	"context"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// tracingBillingModeTTL matches the Python emitter's cache (ee.usage) so both
// services share the same tracing_billing_mode:{org} key.
const tracingBillingModeTTL = 5 * time.Minute

// tracingBillingMode resolves the org's tracing billing mode ("storage" or
// "events"): Redis cache first, Postgres fallback, "storage" default. Mirrors
// Python _tracing_billing_mode and Metering.getCachedPlan so the dimension we
// emit is the one we bill.
func tracingBillingMode(ctx context.Context, rdb *redis.Client, pg *pgxpool.Pool, log *slog.Logger, orgID string) string {
	cacheKey := "tracing_billing_mode:" + orgID

	if rdb != nil {
		if cached, err := rdb.Get(ctx, cacheKey).Result(); err == nil && cached != "" {
			return cached
		}
	}

	if pg == nil {
		return "storage"
	}

	const q = `SELECT tracing_billing_mode FROM usage_organizationsubscription
		WHERE organization_id = $1 AND deleted = false LIMIT 1`

	mode := "storage"
	var got string
	if err := pg.QueryRow(ctx, q, orgID).Scan(&got); err != nil {
		if err != pgx.ErrNoRows {
			log.Warn("tracing_billing_mode lookup failed", "err", err, "org", orgID)
		}
	} else if got != "" {
		mode = got
	}

	if rdb != nil {
		_ = rdb.SetEx(ctx, cacheKey, mode, tracingBillingModeTTL).Err()
	}

	return mode
}
