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
