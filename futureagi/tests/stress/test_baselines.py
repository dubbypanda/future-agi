"""Red baseline budgets (S4, S6, S7, S10, S12): each asserts the post-fix
Phase-A/B budget against CURRENT code and must fail today — strict xfail.
The fix packet that lands each TH-6642 fix removes its xfail marker.
"""

from __future__ import annotations

import tracemalloc

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from tests.stress.budgets import (
    DRAIN_BATCH_MAX_CH_QUERIES,
    DRAIN_PER_ENTRY_MAX_PG_QUERIES,
    RECONCILE_REQUEUE_MAX_PG_UPDATES,
    ROOT_LOOKUP_MAX_MEMORY,
    ROOT_LOOKUP_MAX_READ_ROWS_FACTOR,
    SESSION_RESOLVE_MAX_READ_ROWS_FACTOR,
    TRACE_LOAD_MAX_PY_PEAK,
)
from tests.stress.ch_asserts import _client, ch_query_budget
from tracer.models.eval_task import RowType
from tracer.models.observation_span import EvalEntryStatus, EvalLogger
from tracer.services.clickhouse.v2 import get_reader
from tracer.services.eval_tasks.entries import claim_pending_batch
from tracer.services.eval_tasks.reconciler import reconcile
from tracer.services.eval_tasks.run_entry import run_entry

pytestmark = pytest.mark.stress


@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason="fixed by TH-6642 A1")
def test_s4_root_lookup_prunes_to_project(stress_dataset, eval_task_factory):
    manifest = stress_dataset.target
    eval_task_factory(manifest.project_id, row_type=RowType.TRACES)
    with ch_query_budget("stress:A1:root-lookup") as b:
        with get_reader() as reader:
            reader.list_root_spans_by_trace_ids(
                manifest.trace_ids[:1000], include_heavy=False
            )
    assert (
        b.total("read_rows") <= manifest.span_count * ROOT_LOOKUP_MAX_READ_ROWS_FACTOR
    )
    assert b.max("memory_usage") <= ROOT_LOOKUP_MAX_MEMORY


@pytest.mark.xfail(strict=True, reason="fixed by TH-6642 A4")
def test_s6_trace_load_python_peak_bounded(stress_dataset):
    from tracer.services.clickhouse.v2.eval_loader import (
        eval_read_source,
        filter_observation_spans_by_trace,
    )

    manifest = stress_dataset.voice
    trace_id = manifest.trace_ids[0]
    with eval_read_source("clickhouse"):
        tracemalloc.start()
        try:
            spans = filter_observation_spans_by_trace(
                trace_id, project_id=manifest.project_id
            )
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    assert len(spans) > 0
    # Ceiling independent of payload fatness: below one 1.2 MiB transcript.
    assert peak <= TRACE_LOAD_MAX_PY_PEAK


@pytest.mark.xfail(strict=True, reason="fixed by TH-6642 A5")
def test_s7_session_resolve_prunes_to_project(stress_dataset):
    from tracer.services.clickhouse.v2.trace_session_dict_reader import (
        resolve_session_fields,
    )

    manifest = stress_dataset.target
    client = _client()
    try:
        session_uuids = [
            r[0]
            for r in client.query(
                "SELECT toString(trace_session_id) FROM trace_sessions FINAL "
                "WHERE project_id = %(p)s AND is_deleted = 0",
                parameters={"p": manifest.project_id},
            ).result_rows
        ]
    finally:
        client.close()
    assert len(session_uuids) == len(manifest.session_ids)

    with ch_query_budget("stress:A5:session-resolve") as b:
        resolved = resolve_session_fields(session_uuids)
    assert len(resolved) == len(session_uuids)
    assert (
        b.total("read_rows")
        <= len(session_uuids) * SESSION_RESOLVE_MAX_READ_ROWS_FACTOR
    )


@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason="fixed by TH-6642 A7")
def test_s10_reconcile_requeue_update_fanout(stress_dataset, eval_task_factory):
    m = stress_dataset.target
    task = eval_task_factory(m.project_id, RowType.SPANS, spans_limit=60, n_evals=3)
    reconcile(task)
    EvalLogger.objects.filter(eval_task_id=str(task.id)).update(
        status=EvalEntryStatus.COMPLETED
    )
    # Edit every config: hash changes make all completed entries stale.
    for cfg in task.evals.all():
        cfg.config = {"threshold": 0.9}
        cfg.save()

    with CaptureQueriesContext(connection) as ctx:
        result = reconcile(task)

    assert result.requeued == 180  # parity: every stale entry requeued
    table = EvalLogger._meta.db_table
    updates = [
        q
        for q in ctx.captured_queries
        if q["sql"].strip().upper().startswith("UPDATE") and table in q["sql"]
    ]
    assert len(updates) <= RECONCILE_REQUEUE_MAX_PG_UPDATES


@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason="fixed by TH-6642 B1/B2/B3")
def test_s12_drain_batch_query_counts(
    stress_dataset, eval_task_factory, stub_run_eval, stub_cost_log
):
    m = stress_dataset.target
    batch_size = 500
    task = eval_task_factory(m.project_id, RowType.SPANS, spans_limit=batch_size)
    reconcile(task)
    entries = claim_pending_batch(task, batch_size)
    assert len(entries) == batch_size

    with (
        CaptureQueriesContext(connection) as ctx,
        ch_query_budget("stress:B:drain-batch") as b,
    ):
        for entry in entries:
            run_entry(entry)

    assert b.count <= DRAIN_BATCH_MAX_CH_QUERIES
    assert len(ctx.captured_queries) <= batch_size * DRAIN_PER_ENTRY_MAX_PG_QUERIES
