"""ClickHouse span reads for the cluster RCA agent.

Scope (current): read a trace's spans, and read one span — the hot path
(trace summarizer bundle + read(trace) skeleton + read(span)). CH ``spans``
is the source of truth for tracing telemetry; the 656 GB PG table is the
legacy mirror.

Reads are project-scoped, dedup the ReplacingMergeTree via ``LIMIT 1 BY id``,
and filter ``_peerdb_is_deleted = 0`` — mirroring the prod span_list builder.
Returns are column-keyed dicts (the natural DB-row shape); the agent reshapes
them into LLM-facing payloads with aliases.

Cluster-wide span reads (list/search/aggregate across a trace set) still run
on PG and migrate here when needed.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from tracer.services.clickhouse.client import (
    ClickHouseClient,
    is_clickhouse_enabled,
)

logger = structlog.get_logger(__name__)


# Columns cluster_rca needs off a span. Aliased to the agent's vocabulary.
# Includes the trace-level fields denormalized onto every span row
# (trace_name / trace_session_id / trace_external_id / trace_tags) so the
# agent can derive trace context without a separate PG Trace read.
_SPAN_COLS = (
    "toString(id) AS span_id",
    "toString(trace_id) AS trace_id",
    "parent_span_id",
    "name",
    "observation_type",
    "operation_name",
    "status",
    "status_message",
    "latency_ms",
    "toString(start_time) AS start_time",
    "toString(end_time) AS end_time",
    "input",
    "output",
    "model",
    "provider",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost",
    "tags",
    "trace_name",
    "toString(trace_session_id) AS trace_session_id",
    "trace_external_id",
    "trace_tags",
)


def _rows_to_dicts(rows: list, cols: tuple) -> list[dict[str, Any]]:
    keys = [c.split(" AS ")[-1].strip() for c in cols]
    return [dict(zip(keys, row)) for row in rows]


def _ids_list(trace_ids: Iterable[str]) -> list[str]:
    return [str(t) for t in trace_ids if t]


def _run(query: str, params: dict) -> list:
    try:
        client = ClickHouseClient()
        rows, _types, _ms = client.execute_read(query, params)
        return rows
    except Exception as e:
        logger.warning("cluster_rca_ch_span_read_failed", error=str(e))
        return []


def spans_for_trace(project_id: str, trace_id: str) -> list[dict[str, Any]]:
    """All spans of one trace, ordered by start_time (full columns).

    Powers the trace summarizer's top-down bundle and read(trace)'s span
    skeleton. Empty list when CH is unavailable.
    """
    if not trace_id or not is_clickhouse_enabled():
        return []
    cols = ", ".join(_SPAN_COLS)
    query = f"""
        SELECT {cols}
        FROM spans
        WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0
          AND toString(trace_id) = %(tid)s
        ORDER BY start_time
        LIMIT 1 BY id
    """
    return _rows_to_dicts(
        _run(query, {"pid": str(project_id), "tid": str(trace_id)}), _SPAN_COLS
    )


def read_span(project_id: str, span_id: str) -> Optional[dict[str, Any]]:
    """One span by id (full columns), or None if absent / CH unavailable."""
    if not span_id or not is_clickhouse_enabled():
        return None
    cols = ", ".join(_SPAN_COLS)
    query = f"""
        SELECT {cols}
        FROM spans
        WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0
          AND toString(id) = %(sid)s
        LIMIT 1 BY id
        LIMIT 1
    """
    dicts = _rows_to_dicts(
        _run(query, {"pid": str(project_id), "sid": str(span_id)}), _SPAN_COLS
    )
    return dicts[0] if dicts else None


def list_spans_in_traces(
    project_id: str,
    trace_ids: Iterable[str],
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated span list across a trace set. Returns (page, total_distinct)."""
    ids = _ids_list(trace_ids)
    if not ids or not is_clickhouse_enabled():
        return [], 0
    cols = ", ".join(_SPAN_COLS)
    base = (
        "FROM spans WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0 "
        "AND toString(trace_id) IN %(tids)s"
    )
    params = {"pid": str(project_id), "tids": ids, "limit": limit, "offset": offset}
    page = _rows_to_dicts(
        _run(
            f"SELECT {cols} {base} ORDER BY trace_id, start_time "
            "LIMIT 1 BY id LIMIT %(limit)s OFFSET %(offset)s",
            params,
        ),
        _SPAN_COLS,
    )
    total_rows = _run(f"SELECT uniqExact(id) {base}", params)
    return page, (int(total_rows[0][0]) if total_rows else 0)


def search_spans_in_traces(
    project_id: str,
    trace_ids: Iterable[str],
    query_text: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search over span input/output/name/
    status_message within a trace set."""
    ids = _ids_list(trace_ids)
    if not ids or not query_text or not is_clickhouse_enabled():
        return []
    cols = ", ".join(_SPAN_COLS)
    text_pred = (
        "(positionCaseInsensitive(input, %(q)s) > 0 "
        "OR positionCaseInsensitive(output, %(q)s) > 0 "
        "OR positionCaseInsensitive(name, %(q)s) > 0 "
        "OR positionCaseInsensitive(ifNull(status_message, ''), %(q)s) > 0)"
    )
    query = f"""
        SELECT {cols}
        FROM spans
        WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0
          AND toString(trace_id) IN %(tids)s
          AND {text_pred}
        ORDER BY trace_id, start_time
        LIMIT 1 BY id
        LIMIT %(limit)s
    """
    params = {"pid": str(project_id), "tids": ids, "q": query_text, "limit": limit}
    return _rows_to_dicts(_run(query, params), _SPAN_COLS)


# group_by token → (CH column, extra predicate) for span_count aggregation.
_SPAN_AGG_FIELDS: dict[str, tuple[str, Optional[str]]] = {
    "span_tool_name": ("name", "observation_type = 'tool'"),
    "span_status": ("status", None),
    "span_type": ("observation_type", None),
}


def aggregate_span_field(
    project_id: str,
    trace_ids: Iterable[str],
    group_by: str,
) -> Optional[tuple[list[dict[str, Any]], int]]:
    """span_count grouped by a whitelisted field (deduped via LIMIT 1 BY id).
    Returns (buckets, total) or None if group_by isn't whitelisted."""
    if group_by not in _SPAN_AGG_FIELDS:
        return None
    ids = _ids_list(trace_ids)
    if not ids or not is_clickhouse_enabled():
        return [], 0
    field, extra = _SPAN_AGG_FIELDS[group_by]
    extra_pred = f"AND {extra}" if extra else ""
    query = f"""
        SELECT {field} AS k, count() AS c
        FROM (
            SELECT id, {field}
            FROM spans
            WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0
              AND toString(trace_id) IN %(tids)s
              {extra_pred}
            LIMIT 1 BY id
        )
        GROUP BY k ORDER BY c DESC
    """
    rows = _run(query, {"pid": str(project_id), "tids": ids})
    buckets = [{"key": r[0] or "(none)", "count": r[1]} for r in rows]
    return buckets, sum(b["count"] for b in buckets)


def error_messages_in_traces(
    project_id: str,
    trace_ids: Iterable[str],
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Distinct ERROR-status span status_messages with counts. Returns
    (page_items, total_distinct)."""
    ids = _ids_list(trace_ids)
    if not ids or not is_clickhouse_enabled():
        return [], 0
    query = """
        SELECT status_message AS k, count() AS c
        FROM (
            SELECT id, status_message
            FROM spans
            WHERE project_id = %(pid)s AND _peerdb_is_deleted = 0
              AND toString(trace_id) IN %(tids)s
              AND status = 'ERROR'
              AND notEmpty(ifNull(status_message, ''))
            LIMIT 1 BY id
        )
        GROUP BY k ORDER BY c DESC
    """
    rows = _run(query, {"pid": str(project_id), "tids": ids})
    total = len(rows)
    page = rows[offset:offset + limit]
    return [{"key": r[0], "count": r[1]} for r in page], total
