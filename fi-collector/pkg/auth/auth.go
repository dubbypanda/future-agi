// Package auth provides API key authentication, project resolution,
// rate limiting, and usage metering for the fi-collector.
//
// All state is in-process (sync.Map cache + singleflight). PG is queried
// directly — no Django dependency.
package auth

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/sync/singleflight"
)

var (
	ErrUnauthenticated = errors.New("invalid or missing API key")
	ErrKeyDisabled     = errors.New("API key is disabled")
	ErrNoProject       = errors.New("project could not be resolved")
)

// Stats exposes auth metrics for the /metrics endpoint.
type Stats struct {
	CacheHits   int64
	CacheMisses int64
	StaleServes int64
	Denied      int64
	PGErrors    int64
	CacheSize   int
}

// Authenticator is the top-level auth facade. Safe for concurrent use.
type Authenticator struct {
	cfg      Config
	pg       *PGResolver
	cache    *cache
	sfKey    singleflight.Group // dedup concurrent key lookups
	sfProj   singleflight.Group // dedup concurrent project lookups
	log      *slog.Logger
	stats    Stats
}

// New creates an Authenticator. If cfg.Enabled is false, returns nil
// (all interceptor/middleware checks become no-ops).
func New(ctx context.Context, cfg Config, log *slog.Logger) (*Authenticator, error) {
	if !cfg.IsEnabled() {
		return nil, nil
	}
	cfg.defaults()

	pg, err := NewPGResolver(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("auth pg resolver: %w", err)
	}

	return &Authenticator{
		cfg:   cfg,
		pg:    pg,
		cache: newCache(cfg.CacheTTL, cfg.WarmTTL),
		log:   log,
	}, nil
}

// PGRead returns the read connection pool for direct queries (e.g. metering).
func (a *Authenticator) PGRead() *pgxpool.Pool {
	if a == nil || a.pg == nil {
		return nil
	}
	return a.pg.ReadPool()
}

// Close releases PG pools.
func (a *Authenticator) Close() {
	if a != nil && a.pg != nil {
		a.pg.Close()
	}
}

// Snapshot returns a copy of current stats.
func (a *Authenticator) Snapshot() Stats {
	return Stats{
		CacheHits:   atomic.LoadInt64(&a.stats.CacheHits),
		CacheMisses: atomic.LoadInt64(&a.stats.CacheMisses),
		StaleServes: atomic.LoadInt64(&a.stats.StaleServes),
		Denied:      atomic.LoadInt64(&a.stats.Denied),
		PGErrors:    atomic.LoadInt64(&a.stats.PGErrors),
		CacheSize:   a.cache.Size(),
	}
}

// Authenticate validates an API key pair and returns the resolve result.
// On cache hit, returns immediately. On miss, queries PG (deduplicated
// by singleflight). Returns ErrUnauthenticated for invalid keys.
func (a *Authenticator) Authenticate(ctx context.Context, apiKey, secretKey string) (*ResolveResult, error) {
	if a == nil {
		return nil, nil // auth disabled
	}

	ck := CacheKey(apiKey, secretKey)

	entry, status := a.cache.get(ck)
	switch status {
	case "fresh":
		atomic.AddInt64(&a.stats.CacheHits, 1)
		return entry.result, nil

	case "warm":
		atomic.AddInt64(&a.stats.StaleServes, 1)
		// Singleflight dedup — 10K concurrent warm hits = 1 PG query, not 10K goroutines
		go a.sfKey.Do(ck+":refresh", func() (any, error) {
			a.refreshKey(context.Background(), apiKey, secretKey)
			return nil, nil
		})
		return entry.result, nil
	}

	// cache miss — resolve from PG
	atomic.AddInt64(&a.stats.CacheMisses, 1)
	val, err, _ := a.sfKey.Do(ck, func() (any, error) {
		sfCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		return a.pg.ValidateKey(sfCtx, apiKey, secretKey)
	})
	if err != nil {
		atomic.AddInt64(&a.stats.PGErrors, 1)
		return nil, fmt.Errorf("auth resolve: %w", err)
	}

	result, _ := val.(*ResolveResult)
	if result == nil {
		// Don't cache invalid keys — avoids unbounded memory from scanners.
		// Trade-off: invalid keys always hit PG, but singleflight deduplicates.
		atomic.AddInt64(&a.stats.Denied, 1)
		return nil, ErrUnauthenticated
	}

	a.cache.putPositive(ck, result)
	return result, nil
}

// ResolveProjectsForKey resolves project names for an already-authenticated key.
// cacheKey is the hashed key from CacheKey(). Uses the cached project map
// first, queries PG for unknown names, and auto-creates projects that don't exist.
func (a *Authenticator) ResolveProjectsForKey(ctx context.Context, cacheKey string, result *ResolveResult, names []string) error {
	if a == nil || result == nil {
		return nil
	}

	missing := result.MissingProjects(names)
	if len(missing) == 0 {
		return nil
	}

	// Batch resolve from PG read pool
	resolved, err := a.pg.ResolveProjects(ctx, result.OrgID, missing)
	if err != nil {
		atomic.AddInt64(&a.stats.PGErrors, 1)
		return fmt.Errorf("resolve projects: %w", err)
	}

	result.SetProjects(resolved)
	a.cache.addProjects(cacheKey, resolved)

	// Auto-create any still-missing projects via write pool
	for _, name := range missing {
		if _, ok := result.GetProject(name); ok {
			continue
		}
		sfKey := cacheKey + ":" + name
		val, err, _ := a.sfProj.Do(sfKey, func() (any, error) {
			return a.pg.GetOrCreateProject(ctx, result.OrgID, result.WorkspaceID, name, "observe")
		})
		if err != nil {
			a.log.Warn("project auto-create failed", "name", name, "org", result.OrgID, "err", err)
			continue
		}
		id := val.(string)
		result.SetProject(name, id)
		a.cache.addProjects(cacheKey, map[string]string{name: id})
	}

	return nil
}

// refreshKey re-validates a key in the background (warm stale refresh).
func (a *Authenticator) refreshKey(ctx context.Context, apiKey, secretKey string) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	ck := CacheKey(apiKey, secretKey)

	result, err := a.pg.ValidateKey(ctx, apiKey, secretKey)
	if err != nil {
		a.log.Debug("background key refresh failed", "err", err)
		return
	}
	if result == nil {
		// Key was disabled since last cache — evict it
		a.cache.m.Delete(ck)
		return
	}
	a.cache.putPositive(ck, result)
}
