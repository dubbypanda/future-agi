# Codex review — tracer/utils ORM → CHSpanReader chunk

- Date: 2026-05-26T08:46Z
- Branch: feat/ch25-spans-migration (worktree `worktree-agent-aed3b24c7c0288608`)
- Scope: tracer/utils/{eval.py, eval_tasks.py, inline_evals.py, monitor.py, monitor_graphs.py, langfuse_upsert.py}
- Reviewed commits (in submission order):
  - `bf7607ac1` — refactor(ch25): migrate run_for_processed_spans ORM -> CHSpanReader
  - `b873c2c40` — refactor(ch25): migrate eval-runner context builders ORM -> CHSpanReader
  - `d8e1d2742` — refactor(ch25): migrate inline-eval span lookup ORM -> CHSpanReader [LATER REVERTED]
- Follow-up commits made in response to this review:
  - `12eb04d22` — fix(ch25): build_session_context — aggregate over full session, bucket only the page
  - `ecccb9283` — Revert "refactor(ch25): migrate inline-eval span lookup ORM -> CHSpanReader"

## Codex prompt

> Review my last 3 commits in tracer/utils/. Focus on:
> (1) Did I accidentally migrate eval_loader.py (which should stay as the hybrid bridge)?
> (2) Eval runner: are the migrated reads returning spans in the same order the eval-walking logic expects (start_time, id)?
> (3) Monitor aggregates: time-window + org scope correctness.
> (4) parsing_evaltask_filters - if I touched it, is the original Q-object path still valid for callers that haven't migrated yet?
> (5) langfuse_upsert: any FK-traversal patterns that broke?
> Return P0/P1/P2/P3 with file:line citations.

## Codex findings (verbatim)

**P0:** None.

**P1:** Inline evals now bypass the hybrid loader and can strand or falsely fail valid rows. The code selects processible rows via PG, marks them `PROCESSING`, then depends on CH-only `reader.list_by_ids`; a CH exception is uncaught after the status update, and a CH miss marks the inline eval `FAILED`. See [tracer/utils/inline_evals.py:74](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/inline_evals.py:74), [tracer/utils/inline_evals.py:90](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/inline_evals.py:90), [tracer/utils/inline_evals.py:103](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/inline_evals.py:103), [tracer/utils/inline_evals.py:107](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/inline_evals.py:107). This should probably fall back to PG/hybrid on CH miss or error.

**P2:** `build_session_context` no longer builds a full session aggregate for sessions over 100 traces. It caps `traces_page`, fetches CH spans only for those ids, then computes `sess_agg` from that subset while returning the full `trace_count`. See [tracer/utils/eval.py:267](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval.py:267), [tracer/utils/eval.py:281](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval.py:281), [tracer/utils/eval.py:333](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval.py:333), [tracer/utils/eval.py:385](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval.py:385). The session eval path still describes this as a full aggregate at [tracer/utils/eval.py:2638](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval.py:2638).

**P3:** `run_for_processed_spans` does not preserve `start_time, id` ordering. It calls `list_by_ids`, whose reader explicitly orders by `id`, not input order or chronological order. See [tracer/utils/eval_tasks.py:524](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/utils/eval_tasks.py:524), [tracer/services/clickhouse/v2/span_reader.py:267](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/services/clickhouse/v2/span_reader.py:267), [tracer/services/clickhouse/v2/span_reader.py:279](/Users/nikhilpareek/Documents/futureAGI/code/core/future-agi/.claude/worktrees/agent-aed3b24c7c0288608/futureagi/tracer/services/clickhouse/v2/span_reader.py:279). The trace/session context reads themselves are OK: `list_by_trace` and `list_by_trace_ids` order by `start_time, id` within each trace.

### Scoped checks

- `eval_loader.py` was not touched in the last three scoped commits, and it still documents/implements the hybrid CH-read + PG-fallback bridge.
- Monitor aggregate files were not changed by these three commits. Current monitor value paths are still project-scoped and time-windowed through the builder/PG fallback; codex did not find a new org-scope regression from this diff.
- `parsing_evaltask_filters` was not changed and still returns the original Django `Q` object path for non-migrated callers.
- `langfuse_upsert.py` was not touched. Its FK traversal/upsert pattern still passes Django FK objects for `trace` and `observation_span`.

## Actions taken

### P1 — accepted, reverted the inline_evals.py migration (`ecccb9283`)

The original `Exists(ObservationSpan.objects.filter(...))` subquery at line 38 confirms in PG that span rows exist before the InlineEval is flipped to `PROCESSING`. Recently-created spans may not have reached CH yet (async dual-write via `tracer/services/clickhouse/writer.py`), and the new code path's failure mode is strictly worse than the original:

- CH miss → InlineEval marked `FAILED` (unrecoverable, looks identical to "span deleted")
- CH exception → propagates after the `PROCESSING` write, stranding rows

A try/except + PG fallback would re-invent the `eval_loader._hybrid_load_from_ch` pattern badly (no `filter_observation_spans_by_ids` analog exists on the loader, and we'd need an id-set difference check vs the input list to detect lag). The savings (one PG batch SELECT replaced by one CH batch SELECT) are not worth the risk. Reverted.

### P2 — accepted, fixed `build_session_context` in `12eb04d22`

The original `ObservationSpan.objects.filter(trace__in=trace_qs, deleted=False).aggregate(...)` aggregated over every span across every (non-soft-deleted) trace in the session, with no 100-trace cap. The first cut of the migration was using `list_by_trace_ids` against the capped page, so sessions with > 100 traces would report under-counts for `total_spans`, `error_count`, `total_tokens`, `total_cost`, and a truncated `start_time`/`end_time` bracket. Fix: switch to `CHSpanReader.list_by_session(session_id)` for the row set, then gate the per-trace bucket on a stringified `_page_trace_id_strs` set so `trace_summaries` keeps the same payload shape. The cascade of trace soft-delete to span soft-delete (`_soft_delete_trace_tree` in `tracer/views/trace.py:423`; `_soft_delete_project_version_tree` in `tracer/views/project_version.py:102`) means `is_deleted = 0` on the CH side preserves the `trace.deleted = False` filter semantics.

### P3 — defended, no change

`run_for_processed_spans` immediately dispatches each loaded span to `evaluate_observation_span_observe.delay(...)`. The downstream Temporal activities run concurrently on `tasks_s` and have no ordering contract with one another, so the row order of `list_by_ids` (id-ordered) vs the original ORM `filter(id__in=)` (DB-defined arbitrary order) is not observably different from the dispatch site. No regression.

### Scoped-check confirmations (all pass per codex + this run)

- **eval_loader.py untouched** — verified by `git diff --name-status feat/ch25-spans-migration~3..HEAD`: only `tracer/utils/{eval.py,eval_tasks.py,inline_evals.py}` are in the diff window (and `inline_evals.py` is now back at baseline after the revert).
- **parsing_evaltask_filters untouched** — Q-object path remains the source of truth for `tracer/views/eval_task.py:1275` (`total_spans = ObservationSpan.objects.filter(parsed_filters).count()`) and for the 3 in-file deferred sites (`eval_tasks.py:256/270/285`).
- **langfuse_upsert.py untouched** — see "Deferred files" below.
- **monitor.py / monitor_graphs.py untouched** — see "Deferred files" below.

## Deferred files

- **`tracer/utils/langfuse_upsert.py`** — all 3 ObservationSpan read sites (line 199 `Min/Max` aggregate, line 252 `.get(id=)`, line 263 `.filter(trace=).first()`) live inside the same `with transaction.atomic():` block as the span `update_or_create` writes (line 182). With the writer being async dual-write (`tracer/services/clickhouse/writer.py:1`), a read from CH inside the write block would not see just-inserted spans — defer until either the writer is sync or this code path is refactored to read after the atomic commits. No code touched.
- **`tracer/utils/monitor.py` (8 sites) and `tracer/utils/monitor_graphs.py` (6 sites)** — all sites are inside an explicit PG fallback that runs when `AnalyticsQueryService.should_use_clickhouse(QueryType.MONITOR_METRICS)` returns False or the CH path raises. Each site chains `.filter(parsing_evaltask_filters(monitor.filters))` — an arbitrary Django `Q` built from `span_attributes_filters / observation_type / session_id / date_range / created_at / project_id`. Translating that Q to CH SQL is exactly the `parsing_evaltask_filters_for_ch` companion the task description flagged as "wide-impact, defer." Migrating these without that companion would require either (a) a new reader method like `aggregate_by_project_window(project_id, since, until, *, where_sql, where_params)` or (b) bypassing CHSpanReader and going straight to clickhouse-connect — both Rule 1 violations.
- **`tracer/utils/eval.py:2200`** — `Subquery(ObservationSpan.objects.filter(trace_id=OuterRef('id'), parent_span_id__isnull=True).order_by('start_time').values('start_time')[:1])`. Correlated Django subquery used as an `annotate(_root_start=...)` ordering helper on the outer `trace_session.traces` queryset. CHSpanReader has no equivalent; marked with an inline `CH25-TODO(needs: root-span-per-trace fetch)` comment naming the candidate reader method.
- **`tracer/utils/inline_evals.py:38`** — `Exists(ObservationSpan.objects.filter(id=OuterRef('span_id'), deleted=False))` inside an `InlineEval.objects.filter(...)` chain. Correlated EXISTS subquery; no CHSpanReader equivalent.
- **`tracer/utils/eval_tasks.py:256/270/285`** — span-id materialization inside `Trace.objects.filter(id__in=ObservationSpan.objects.filter(filters).values('trace_id').distinct())` and `TraceSession.objects.filter(id__in=...)`. Same `parsing_evaltask_filters → Q` wall as monitor.py; needs the `_for_ch` companion before migration.

## Reader extension requests (for the migration owner)

Two methods are gating the remaining ~14 + 3 + 1 = 18 deferred sites in this chunk:

1. **`aggregate_by_project_window(project_id, since, until, *, where_sql=None, where_params=None) -> dict`** — used by every monitor.py / monitor_graphs.py site for time-window aggregates over a project. Should accept the additional CH `WHERE` clause + params that a future `parsing_evaltask_filters_for_ch` would emit, and return the same keys the existing Python-side aggregators read (`total_tokens`, `error_count`, `provider`, `observation_type`, etc.) plus time-bucketed variants for the graph path.
2. **`earliest_root_span_by_trace_ids(trace_ids: list[str]) -> dict[str, datetime]`** — used by `_resolve_session_path` (eval.py:2200) to order traces by their earliest root span's `start_time`. Today expressed as a correlated Django Subquery.

The `parsing_evaltask_filters_for_ch(filters) -> (where_sql, params)` companion to the existing Q-object builder is a prerequisite for (1); it is in this chunk's scope as the "easier option 3" route, but the refactor touches the 4 in-file callers + 14 monitor callers + the consumer in `views/eval_task.py:1275` and was deemed wide-impact. Building the companion separately and wiring it in via a follow-up chunk is the safer order.
