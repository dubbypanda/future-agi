"""Trace-detail dispatch handler — V1 (PostgreSQL).

`GET /tracer/trace/{id}/` is routed through the v1↔v2 query dispatch
(`get_query_builder_class("TRACE_DETAIL")`) like the list queries. Under a V1
routing mode the dispatch returns THIS class, which serves the trace detail from
PostgreSQL exactly as the endpoint did before the CH migration (stability: an
existing deployment behaves identically until the operator flips TRACE_DETAIL to
V2). Under V2 the dispatch returns ``TraceDetailHandlerV2`` (ClickHouse).

The handler is constructed with the ``view`` so it can reuse the view's small,
already-tested helpers (the tenant queryset, the serializer, and
``_compute_summary_and_graph``); the trace-detail data assembly itself lives
here. Both v1 and v2 return the identical response dict
``{"trace", "observation_spans", "summary", "graph"}`` which the view wraps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from rest_framework.request import Request

    from tracer.services.clickhouse.query_service import AnalyticsQueryService
    from tracer.views.trace import TraceView


class TraceDetail(TypedDict):
    """The response envelope both handlers return; the view wraps it verbatim."""

    trace: dict[str, Any]
    observation_spans: list[dict[str, Any]]
    summary: dict[str, Any]
    graph: dict[str, Any]


class TraceDetailHandler:
    """V1 / PostgreSQL trace-detail handler (the pre-migration behavior)."""

    def __init__(
        self,
        *,
        view: TraceView,
        request: Request,
        pk: str,
        analytics: AnalyticsQueryService | None = None,
    ) -> None:
        self.view = view
        self.request = request
        self.pk = pk
        self.analytics = analytics

    def fetch(self) -> TraceDetail:
        """Assemble the trace detail from PostgreSQL.

        Cross-store tenant gate = the org/workspace-scoped queryset; the span
        tree comes from PG via ``get_observation_spans``; summary/graph are
        computed from that tree.
        """
        from tracer.models.trace import Trace
        from tracer.views.observation_span import get_observation_spans

        view = self.view
        accessible_trace = view.get_queryset().filter(id=self.pk).first()
        if not accessible_trace:
            raise Trace.DoesNotExist

        trace_data = view.get_serializer(accessible_trace).data
        observation_spans_response = get_observation_spans(
            {
                "project_id": str(accessible_trace.project_id),
                "project_version_id": (
                    str(accessible_trace.project_version_id)
                    if accessible_trace.project_version_id
                    else None
                ),
                "trace_id": str(accessible_trace.id),
            }
        )
        summary, graph = view._compute_summary_and_graph(observation_spans_response)
        return {
            "trace": trace_data,
            "observation_spans": observation_spans_response,
            "summary": summary,
            "graph": graph,
        }
