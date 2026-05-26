# Codex review — observation_span.py + trace.py ORM → CHSpanReader chunk

**Commits reviewed**: `62b8cf87e` (observation_span.py) + `0cdb5f9d3` (trace.py)
**Branch**: `feat/ch25-spans-migration`
**Reviewer prompt**: tenant scope preservation, silent missing-row drops on bulk reads,
D-027 deletion comment clarity, N+1 CH patterns, stale Django imports, voice_call_detail
+ agent_graph semantic preservation.

## No P0 found.

## P1

- **Workspace tenant scope not preserved on voice-call reads.** `list_voice_calls`
  gates with `Project.objects.get(id=..., organization=...)`, but does not use
  `_project_queryset_for_request`, so same-org/different-workspace projects can pass
  the gate before CH reads. See
  [trace.py:2746](futureagi/tracer/views/trace.py#L2746).
  `voice_call_detail` has the same issue: it checks only `project__organization_id`,
  not workspace. See
  [trace.py:2836](futureagi/tracer/views/trace.py#L2836).

  **Triage**: pre-existing pattern, not introduced by this chunk. Left as-is to
  keep the migration commit focused on D-027 deletions + reader migrations. Tracked
  separately as a workspace-scope hardening pass across the voice-call endpoints.

- **Attribute-list endpoints read arbitrary `project_id` without first proving the
  project is visible to the request tenant/workspace.** `get_span_attributes_list`
  passes the request project directly into `_get_span_attribute_keys`;
  `get_eval_attributes_list` then also uses it to derive trace/session path shapes.
  See [observation_span.py:1811](futureagi/tracer/views/observation_span.py#L1811),
  [observation_span.py:1846](futureagi/tracer/views/observation_span.py#L1846), and
  the CH/PG read at
  [observation_span.py:1913](futureagi/tracer/views/observation_span.py#L1913).

  **Triage**: pre-existing pattern, not introduced. The endpoint accepts a
  `project_id` from a serializer-validated payload; the tenant gate is the
  serializer + the project being visible. The codex-flagged risk is real but lives
  outside this commit's scope.

## P2

- **Silent missing-row pattern on bulk-by-id enrichment reads.** No direct
  `list_by_ids()` calls in these two files, but span/trace list content fetches
  build maps from requested IDs and default missing rows to empty input/output/attrs
  without a requested-vs-returned count check. See
  [observation_span.py:1347](futureagi/tracer/views/observation_span.py#L1347),
  [observation_span.py:1354](futureagi/tracer/views/observation_span.py#L1354),
  [observation_span.py:1613](futureagi/tracer/views/observation_span.py#L1613),
  [trace.py:3724](futureagi/tracer/views/trace.py#L3724),
  [trace.py:3738](futureagi/tracer/views/trace.py#L3738).

  **Triage**: this happens inside the CH content-query helpers (`build_content_query`)
  not in this migration. The shape was pre-existing — D-027 deletes did not introduce
  new bulk reads. Span/trace lists tolerate empty input/output gracefully because the
  page already has the row metadata; missing content is a CH lag symptom that the
  frontend already renders as "empty cell". Not a load-bearing write path. Tracked
  as a follow-up if missing content needs to surface as an explicit error.

## P3

- **D-027 deletion-comment clarity is uneven.**
  - `voice_call_detail` references `PLAN_V2_NO_CDC` rather than D-027 at
    [trace.py:2848](futureagi/tracer/views/trace.py#L2848).
  - `agent_graph` explains the removed fallback but does not reference D-027 at
    [trace.py:4417](futureagi/tracer/views/trace.py#L4417).
  - `_get_span_attribute_keys` says the PG fallback was removed, but the `else`
    branch still calls `SQL_query_handler`; the comment is misleading. See
    [observation_span.py:1910](futureagi/tracer/views/observation_span.py#L1910).

  **Triage**: the `voice_call_detail` and `agent_graph` comments are pre-existing,
  not added by this commit. The `_get_span_attribute_keys` comment was likewise
  pre-existing — I did not touch this helper. The comment ambiguity is real but
  fixing each one is a separate small commit.

- **Stale Django imports remain.** In `trace.py`, `TextField`, `Cast`, `Floor`,
  and `NullIf` appear unused at
  [trace.py:14](futureagi/tracer/views/trace.py#L14) and
  [trace.py:31](futureagi/tracer/views/trace.py#L31).
  In `observation_span.py`, `connection` appears unused at
  [observation_span.py:15](futureagi/tracer/views/observation_span.py#L15).

  **Triage**: all four (`TextField`, `Cast`, `Floor`, `NullIf`, `connection`) are
  pre-existing baseline F401s. I confirmed against `git stash` + ruff on the
  parent commit — these were flagged before this migration. I only removed imports
  this migration broke (`datetime.datetime` top-level, `Sum`,
  `ExtendedPageNumberPagination`, `get_annotation_graph_data`, `get_eval_graph_data`,
  `get_system_metric_data`, `generate_timestamps`, `Cast`, `Coalesce`,
  `KeyTextTransform`). Leaving the older baseline F401s for a separate
  housekeeping pass per the task rules ("`--no-verify` for ruff lint debt").

## Bulk CH patterns

No N+1 CH reads inside row loops. `voice_call_detail` and `agent_graph` are
semantically consistent with the prior CH-only path (neither was touched by this
chunk — they were already CH-only when D-027 was first applied).

## Migration summary

- 2 commits on `feat/ch25-spans-migration`
- `observation_span.py`: 1278 deletions / 246 insertions (net -1032 LOC). 4 PG
  fallback bodies deleted; 2 sites migrated (root_spans, _max_spans_per_trace);
  rest documented KEEP-PG with TODOs.
- `trace.py`: 1673 deletions / 198 insertions (net -1475 LOC). 5 PG fallback
  bodies deleted; defensive-fallback PG reads preserved with comments;
  compare_traces / get_trace_id_by_index / has_voice_traces / _export_voice_calls
  documented LEAVE-PG with TODOs.

No new CHSpanReader methods proposed — all migrations used existing surface.
