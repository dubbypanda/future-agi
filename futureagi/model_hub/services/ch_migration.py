"""Shared utilities for the legacy-to-replicated ClickHouse migration commands.

Both ``migrate_legacy_vectors_to_replicated`` and
``migrate_legacy_default_tables_to_replicated`` need the same primitives:
identifier validation, per-replica row counts read through
``clusterAllReplicas(system.tables)`` (so empty replicas are still counted),
a topology-aware convergence poll, and a source/target column intersection
for name-aligned copies. This module owns the single implementation each
command imports.
"""
from __future__ import annotations

import re
import time

import structlog
from django.core.management.base import CommandError

logger = structlog.get_logger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def require_identifier(value: str, flag: str) -> str:
    """Reject anything that could smuggle SQL through a CLI flag."""
    if not _IDENTIFIER_RE.fullmatch(value):
        raise CommandError(
            f"{flag} {value!r} is not a valid ClickHouse identifier. "
            "Allowed: letters, digits, underscores; must not start with a digit."
        )
    return value


def expected_replica_count(client, cluster: str) -> int:
    """Number of hosts the cluster spans.

    Used to gate ``per_replica_counts`` results: a complete parity check
    must return one row per expected replica, else a still-registering or
    down replica silently reads as ``converged``.
    """
    rows = client.execute(
        "SELECT count() FROM system.clusters WHERE cluster = %(c)s",
        {"c": cluster},
    )
    return rows[0][0] if rows else 0


def per_replica_counts(
    client,
    database: str,
    table: str,
    cluster: str,
) -> dict[str, int]:
    """Per-replica row count via ``system.tables.total_rows``.

    Reads through ``clusterAllReplicas(system.tables)`` rather than
    ``count() ... GROUP BY hostName()`` on the target table itself: the
    latter drops any replica whose local copy is empty, so a freshly
    created (all-empty) target reads as "zero replicas present" and a
    still-lagging follower disappears from the result entirely. Reading
    ``system.tables`` yields one row per replica that holds the table,
    including the empty ones, which is exactly the signal the parity
    gate needs.
    """
    rows = client.execute(
        f"SELECT hostName(), total_rows FROM clusterAllReplicas("
        f"'{cluster}', system.tables) "
        f"WHERE database = %(d)s AND name = %(t)s",
        {"d": database, "t": table},
    )
    return {host: int(cnt or 0) for host, cnt in rows}


def poll_replica_parity(
    client,
    *,
    database: str,
    table: str,
    cluster: str,
    expected: int,
    expected_replicas: int,
    max_wait_sec: float = 30.0,
    poll_interval: float = 2.0,
) -> tuple[dict[str, int], bool]:
    """Poll until every expected replica reports ``>= expected`` rows.

    Convergence requires the full replica set to be present in the
    ``per_replica_counts`` result AND each entry to be at or above the
    expected count. A replica still registering (absent from the result)
    counts as not-yet-converged, never as ``done``.
    """
    deadline = time.monotonic() + max_wait_sec
    counts: dict[str, int] = {}
    while True:
        counts = per_replica_counts(client, database, table, cluster)
        converged = (
            len(counts) >= expected_replicas
            and bool(counts)
            and all(c >= expected for c in counts.values())
        )
        if converged:
            return counts, True
        if time.monotonic() >= deadline:
            logger.warning(
                "migrate_parity_wait_timed_out",
                target=f"{database}.{table}",
                expected=expected,
                expected_replicas=expected_replicas,
                per_replica_counts=counts,
                max_wait_sec=max_wait_sec,
            )
            return counts, False
        time.sleep(poll_interval)


def shared_columns(
    client,
    source_db: str,
    target_db: str,
    table: str,
) -> tuple[list[str], list[str]]:
    """Columns present in both source and target, in target order.

    Returns ``(shared, source_only)``. Callers use ``shared`` to build an
    explicit column list for the copy (name-aligned, not
    positional-``SELECT *``) and log ``source_only`` for visibility when
    the legacy source has drifted columns that the target doesn't carry.
    """
    def cols(db: str) -> list[str]:
        return [
            r[0]
            for r in client.execute(
                "SELECT name FROM system.columns "
                "WHERE database = %(d)s AND table = %(t)s ORDER BY position",
                {"d": db, "t": table},
            )
        ]
    src = cols(source_db)
    tgt = cols(target_db)
    src_set, tgt_set = set(src), set(tgt)
    shared = [c for c in tgt if c in src_set]
    source_only = [c for c in src if c not in tgt_set]
    return shared, source_only
