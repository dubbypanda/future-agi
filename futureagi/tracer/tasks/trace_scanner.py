"""
Trace scanner Temporal activities.

Activity 1: scan_traces_task — scan completed traces for issues
Activity 2: embed_trace_inputs_task — kevinify + embed root inputs for all scanned traces
Activity 3: cluster_scan_issues_task — cluster unclustered issues + match success traces
"""

import time
from datetime import timedelta
from typing import List

import structlog

from tfc.temporal.drop_in import temporal_activity
from tracer.models.trace_error_analysis import TraceErrorGroup
from tracer.models.trace_scan import TraceScanConfig
from tracer.queries.trace_scanner import filter_already_scanned
from tracer.services.clickhouse.v2 import get_reader
from tracer.utils.trace_scanner import (
    cluster_issues,
    embed_trace_inputs,
    match_success_traces,
    scan_and_write,
)

logger = structlog.get_logger(__name__)

SCAN_DELAY_SECONDS = 10

# ─── Periodic sweep policy (scan collector-ingested CH-only traces) ──────────
_SWEEP_GRACE_SECONDS = 60  # let straggler child spans settle before scanning
_SWEEP_COLD_START_SECONDS = 900  # first-sweep window when last_swept_at is NULL
_SWEEP_BATCH_SIZE = 15  # keep each scan task under its time_limit (cf. _trigger_trace_scanner)


@temporal_activity(time_limit=600, queue="agent_compass", max_retries=1)
def scan_traces_task(trace_ids: List[str], project_id: str):
    """
    Scan completed traces for issues.

    Triggered from OTLP ingestion after root span completion.
    Waits 10s for straggler child spans, then runs the full scan pipeline.
    Chain: scan → embed inputs → cluster + match success traces.
    """
    time.sleep(SCAN_DELAY_SECONDS)

    logger.info(
        "scan_traces_task_started",
        trace_count=len(trace_ids),
        project_id=project_id,
    )

    results = scan_and_write(trace_ids, project_id)

    issues_found = sum(len(r.issues) for r in results)
    logger.info(
        "scan_traces_task_completed",
        trace_count=len(results),
        issues_found=issues_found,
        project_id=project_id,
    )

    # Always embed root inputs (success + failure traces needed for KNN).
    # Embed triggers clustering if there are new issues.
    embed_trace_inputs_task.apply_async(
        args=(trace_ids, project_id, issues_found > 0),
    )


@temporal_activity(time_limit=300, queue="agent_compass", max_retries=1)
def embed_trace_inputs_task(
    trace_ids: List[str], project_id: str, trigger_clustering: bool
):
    """
    Kevinify + embed root span inputs for all scanned traces.

    Stores in ClickHouse for KNN success trace matching.
    Runs for ALL traces (success and failure) so KNN has both sides.
    Chains to clustering if new issues were found.
    """
    logger.info(
        "embed_trace_inputs_task_started",
        trace_count=len(trace_ids),
        project_id=project_id,
    )

    stored = embed_trace_inputs(trace_ids, project_id)

    logger.info(
        "embed_trace_inputs_task_completed",
        project_id=project_id,
        stored=stored,
    )

    if trigger_clustering:
        cluster_scan_issues_task.apply_async(args=(project_id,))


@temporal_activity(time_limit=300, queue="agent_compass", max_retries=1)
def cluster_scan_issues_task(project_id: str):
    """
    Cluster unclustered scanner issues + match success traces for updated clusters.

    Online incremental: each issue → embed → cosine match centroids → assign or create cluster.
    After clustering, KNN matches nearest success trace per updated cluster.
    """
    logger.info("cluster_scan_issues_task_started", project_id=project_id)

    summary = cluster_issues(project_id)

    logger.info(
        "cluster_scan_issues_task_completed",
        project_id=project_id,
        clustered=summary.clustered,
        new_clusters=summary.new_clusters,
        assigned=summary.assigned,
    )

    # Match success traces for all scanner clusters in this project
    if summary.clustered > 0:
        cluster_ids = list(
            TraceErrorGroup.objects.filter(
                project_id=project_id,
                source="scanner",
            ).values_list("cluster_id", flat=True)
        )

        matches = match_success_traces(project_id, cluster_ids)
        logger.info(
            "success_trace_matching_completed",
            project_id=project_id,
            clusters_checked=len(cluster_ids),
            matches_found=len(matches),
        )


@temporal_activity(time_limit=300, queue="agent_compass", max_retries=0)
def sweep_scannable_traces():
    """Trigger scans for completed, unscanned (collector-ingested) traces.

    The collector writes spans straight to CH and bypasses the inline scanner
    trigger, so this sweep is the only trigger for CH-only traces. Per observe
    project with scanning enabled and a non-zero rate: scan
    ``(last_swept_at, now-grace]`` of root ``created_at``, drop already-scanned,
    dispatch ``scan_traces_task`` (which chains embed -> cluster), advance the
    watermark.

    Sampling stays in ``scan_and_write``; the watermark (not the anti-join) is
    what stops a sampled-out trace — which has no result row — from being
    re-rolled every tick. ``max_retries=0``: the next tick recovers a failure.
    """
    configs = list(
        TraceScanConfig.objects.filter(
            enabled=True,
            sampling_rate__gt=0,
            project__trace_type="observe",
        ).values("project_id", "last_swept_at")
    )
    if not configs:
        return

    dispatched = 0
    with get_reader() as reader:
        now_ch = reader.ch_now()
        upper = now_ch - timedelta(seconds=_SWEEP_GRACE_SECONDS)
        cold_floor = now_ch - timedelta(seconds=_SWEEP_COLD_START_SECONDS)

        for cfg in configs:
            project_id = str(cfg["project_id"])
            try:
                lower = cfg["last_swept_at"] or cold_floor
                candidates = reader.root_trace_ids_between(project_id, lower, upper)
                fresh = filter_already_scanned(candidates) if candidates else []
                for i in range(0, len(fresh), _SWEEP_BATCH_SIZE):
                    scan_traces_task.apply_async(
                        args=(fresh[i : i + _SWEEP_BATCH_SIZE], project_id)
                    )
                    dispatched += 1
                # Advance even when nothing was due, so an idle project doesn't
                # re-scan its window. ``upper`` is a CH-clock timestamp.
                TraceScanConfig.objects.filter(project_id=cfg["project_id"]).update(
                    last_swept_at=upper
                )
            except Exception:
                # Fail-open: one project's error must not starve the tick.
                # Watermark not advanced, so the next tick retries this window.
                logger.warning(
                    "scan_sweep_project_failed", project_id=project_id, exc_info=True
                )

    logger.info(
        "scan_sweep_completed",
        projects=len(configs),
        tasks_dispatched=dispatched,
    )
