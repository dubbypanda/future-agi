package auth

import (
	"context"
	"errors"
	"net/http"
)

// HTTPMiddleware wraps an http.Handler with API key authentication.
func (a *Authenticator) HTTPMiddleware(next http.Handler) http.Handler {
	if a == nil {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		apiKey := r.Header.Get("X-Api-Key")
		secretKey := r.Header.Get("X-Secret-Key")
		if apiKey == "" || secretKey == "" {
			http.Error(w, `{"error":"missing X-Api-Key or X-Secret-Key"}`, http.StatusUnauthorized)
			return
		}

		result, err := a.Authenticate(r.Context(), apiKey, secretKey)
		if err != nil {
			if errors.Is(err, ErrUnauthenticated) || errors.Is(err, ErrKeyDisabled) {
				a.log.Warn("http auth failed", "err", err)
				http.Error(w, `{"error":"authentication failed"}`, http.StatusUnauthorized)
				return
			}
			a.log.Error("http auth infrastructure error", "err", err)
			http.Error(w, `{"error":"service temporarily unavailable"}`, http.StatusServiceUnavailable)
			return
		}

		ctx := context.WithValue(r.Context(), contextKey{}, result)
		ctx = context.WithValue(ctx, apiKeyCtxKey{}, apiKey)
		ctx = context.WithValue(ctx, cacheKeyCtxKey{}, CacheKey(apiKey, secretKey))
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
