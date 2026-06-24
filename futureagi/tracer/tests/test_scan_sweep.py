"""Unit tests for the periodic scan sweep (``sweep_scannable_traces``).

The sweep is the only scanner trigger for collector-ingested (CH-only) traces,
so these pin its contract: batched dispatch, the per-project watermark cursor
(cold-start floor vs ``last_swept_at``), the already-scanned anti-join, watermark
advance, and per-project fail-open. DB-free — every collaborator (CH reader,
config model, dispatch, anti-join) is mocked, so a regression fails here without
Postgres/ClickHouse/Temporal.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from tracer.tasks import trace_scanner as sweep

# Undecorated function: skip the activity wrapper's close_old_connections (DB).
_run = sweep.sweep_scannable_traces._original_func

_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
_UPPER = _NOW - timedelta(seconds=sweep._SWEEP_GRACE_SECONDS)
_COLD_FLOOR = _NOW - timedelta(seconds=sweep._SWEEP_COLD_START_SECONDS)


def _reader(root_ids=None, side_effect=None):
    reader = MagicMock()
    reader.ch_now.return_value = _NOW
    if side_effect is not None:
        reader.root_trace_ids_between.side_effect = side_effect
    else:
        reader.root_trace_ids_between.return_value = root_ids or []
    cm = MagicMock()
    cm.__enter__.return_value = reader
    cm.__exit__.return_value = False
    return cm, reader


def _config_model(rows):
    """Mock TraceScanConfig: ``.objects.filter(...).values(...)`` returns ``rows``
    (the project selection); ``.objects.filter(project_id=...).update(...)`` is the
    watermark write (same shared ``filter.return_value``)."""
    m = MagicMock()
    m.objects.filter.return_value.values.return_value = rows
    return m


def _patches(cm, cfg_model, already_scanned=None):
    return (
        patch.object(sweep, "get_reader", return_value=cm),
        patch.object(sweep, "TraceScanConfig", cfg_model),
        patch.object(
            sweep,
            "filter_already_scanned",
            side_effect=(lambda x: x) if already_scanned is None else (lambda x: already_scanned),
        ),
        patch.object(sweep, "scan_traces_task"),
    )


def test_dispatches_in_batches_and_advances_watermark_from_cold_floor():
    cm, reader = _reader([f"t{i}" for i in range(20)])
    cfg = _config_model([{"project_id": "p1", "last_swept_at": None}])
    p_reader, p_cfg, p_filter, p_task = _patches(cm, cfg)
    with p_reader, p_cfg, p_filter, p_task as mock_task:
        _run()

    # last_swept_at is None -> cold-start floor is the lower bound.
    reader.root_trace_ids_between.assert_called_once_with("p1", _COLD_FLOOR, _UPPER)
    # 20 ids -> batches of _SWEEP_BATCH_SIZE (15) -> 2 dispatches (15 + 5).
    assert mock_task.apply_async.call_count == 2
    batches = [c.kwargs["args"][0] for c in mock_task.apply_async.call_args_list]
    assert [len(b) for b in batches] == [sweep._SWEEP_BATCH_SIZE, 5]
    assert all(c.kwargs["args"][1] == "p1" for c in mock_task.apply_async.call_args_list)
    # Watermark advances to the CH-clock upper bound.
    cfg.objects.filter.return_value.update.assert_called_once_with(last_swept_at=_UPPER)


def test_uses_last_swept_at_as_lower_bound_when_set():
    swept = _NOW - timedelta(minutes=5)
    cm, reader = _reader(["t1"])
    cfg = _config_model([{"project_id": "p1", "last_swept_at": swept}])
    p_reader, p_cfg, p_filter, p_task = _patches(cm, cfg)
    with p_reader, p_cfg, p_filter, p_task:
        _run()

    reader.root_trace_ids_between.assert_called_once_with("p1", swept, _UPPER)


def test_already_scanned_traces_are_filtered_before_dispatch():
    cm, _ = _reader(["t1", "t2", "t3", "t4", "t5"])
    cfg = _config_model([{"project_id": "p1", "last_swept_at": None}])
    p_reader, p_cfg, p_filter, p_task = _patches(cm, cfg, already_scanned=["t2", "t4"])
    with p_reader, p_cfg, p_filter, p_task as mock_task:
        _run()

    assert mock_task.apply_async.call_count == 1
    assert mock_task.apply_async.call_args.kwargs["args"][0] == ["t2", "t4"]


def test_per_project_fail_open_isolates_a_failing_project():
    # p1's CH read raises; p2 succeeds. p1 must not abort the tick, and p1's
    # watermark must NOT advance (so the next tick retries its window).
    cm, reader = _reader(side_effect=[RuntimeError("ch down"), ["t1"]])
    cfg = _config_model(
        [
            {"project_id": "p1", "last_swept_at": None},
            {"project_id": "p2", "last_swept_at": None},
        ]
    )
    p_reader, p_cfg, p_filter, p_task = _patches(cm, cfg)
    with p_reader, p_cfg, p_filter, p_task as mock_task:
        _run()  # must not raise

    assert mock_task.apply_async.call_count == 1  # only p2 dispatched
    # Exactly one watermark advance (p2); p1's failure skipped its update.
    assert cfg.objects.filter.return_value.update.call_count == 1


def test_no_sampling_projects_short_circuits_before_clickhouse():
    cfg = _config_model([])
    with (
        patch.object(sweep, "get_reader") as mock_reader,
        patch.object(sweep, "TraceScanConfig", cfg),
    ):
        _run()

    mock_reader.assert_not_called()  # no CH round-trip when nothing samples
