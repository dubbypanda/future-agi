# Codex review: tracer/queries ORM → CHSpanReader migration

Run: 2026-05-26T08:45Z (UTC)
Commits reviewed:
  c3588dcdd refactor(ch25): migrate scan_clustering ORM → CHSpanReader
  08905b2aa refactor(ch25): migrate trace_scanner ORM → CHSpanReader
  1789c6a95 refactor(ch25): migrate error_analysis ORM → CHSpanReader
  50561eb5c refactor(ch25): migrate feed.py ORM → CHSpanReader (the big one)

Codex model: gpt-5.5  |  Effort: xhigh  |  Sandbox: read-only

Focus areas (per the migration playbook):
(1) Pagination + ordering semantics
(2) Subquery+OuterRef per-trace replacements (one-row-per-trace correctness, span pick)
(3) Aggregate correctness: Min/Max/Sum/Count
(4) N+1 patterns (get_reader() inside loops)
(5) Stale Django imports cleanup

---

## P0
None found.

## P1
- **feed.py:223 — `_fetch_users_affected_batch` undercounts when a trace
  belongs to multiple clusters.** The original code collapsed
  `trace_id -> cluster_id` to a single cluster, then counted each span's
  `end_user_id` only for that one cluster. A trace can belong to multiple
  feed clusters (separate ECT rows), so this undercounts all but
  whichever cluster overwrote the map entry. Codex suggested
  `trace_id -> set[cluster_id]` plus per-span fan-out to every cluster.

  STATUS: FIXED in follow-up commit. `trace_to_clusters` is now
  `dict[str, set]`, and the span loop adds the end_user_id to every
  cluster the trace belongs to.

## P2
- **feed.py:1130 — root-span selection changed.** The CH path kept the
  first parentless span from `list_by_trace_ids` (start_time ASC); the
  legacy ORM relied on `ObservationSpan.Meta.ordering = ["-start_time"]`
  so the old `.first()` returned the LATEST root. For multi-root
  traces, the new code picked the oldest root.

  STATUS: FIXED in follow-up commit. `_get_root_span` now walks
  `reversed(spans)`, and `_get_root_spans_batch` overwrites instead of
  first-wins so the last (newest) parentless span per trace is kept.
  Docstrings updated to call out the legacy default ordering as the
  source of truth.

- **feed.py:1179 — latency aggregation no longer preserves SQL `Sum()`
  null semantics.** Rollup initialized every seen trace to `[0, 0, 0]`,
  so traces whose latency was unknown became 0 and those zeros are
  included in p50/p95 at feed.py:1573.

  STATUS: PARTIALLY ADDRESSED. The rollup now initializes to
  `[None, None, None]` and only promotes to int when at least one span
  contributes a non-None value — matching legacy "all-NULL spans →
  None" semantics. A residual schema-level gap remains: the CH schema
  stores `latency_ms / prompt_tokens / completion_tokens` as
  non-nullable int (default 0), so spans PG would have flagged NULL
  now arrive as 0. Documented in the helper docstring; needs CH25
  regression-suite coverage to confirm p50/p95 stays within tolerance.

## P3
- **error_analysis.py:11 — `Avg` import stale.** Removed after the
  three CH-deferred aggregate methods stopped using it.

  STATUS: FIXED.

- **feed.py:29 — `TruncHour` imported but unused.** Removed.

  STATUS: FIXED.

## Negative findings (the good kind)
- No new `get_reader()`-inside-per-row-loop N+1 introduced. The two
  hot loops (`_fetch_trace_rows`, `_fetch_representative_traces`)
  both pre-batch every per-trace lookup (totals, scores, roots, scan
  results) into single round-trips.
- Feed list pagination/order preserved end-to-end: `ECT.created_at DESC`
  is the source-of-truth sort; the dedupe pass and the build loop both
  iterate in that order.

---

Full transcript with tool calls + diffs codex inspected is preserved
in the codex run log (~14k lines). This file is the distilled finding
set + status of each.
