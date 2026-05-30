"""curated_writer — app-level dual-write of PG ``tracer_enduser`` /
``trace_session`` rows into the CH curated dimensions ``end_users`` /
``trace_sessions``.

Sibling of ``trace_writer`` and the EXACT same pattern, applied to the two
CURATED dimensions of the CH-derived-dimensions migration (DESIGN §4 / §5).
In the legacy world these reached ClickHouse via PeerDB CDC (``tracer_enduser``
/ ``trace_session`` landing tables → ``enduser_dict`` / ``trace_session_dict``);
v2 removes CDC, so the curated entity needs a CH-native feed. The one-time
history is loaded by ``ch25_backfill_curated_dimensions``; this module keeps it
fresh by mirroring every ingest-time PG ``get_or_create`` into the RMTs.

P3a IDENTITY — STRAIGHT MIRROR, NO RE-KEY. ``end_user_id`` / ``trace_session_id``
are the PG-minted ``id`` verbatim (the random uuid4 already denormalized onto
every span). The deterministic UUIDv5 re-keying (DESIGN §3 / §3.1) is P3b. This
module ONLY adds the dual-write; it does NOT touch the PG ``get_or_create`` (that
stays as the id source until P3b) and changes NO read path (P3c).

Design (mirrors ``trace_writer`` 1:1):
  • Post-commit. Callers schedule via ``transaction.on_commit`` so CH never
    sees an entity whose PG row rolled back (matches the old "CH after commit"
    CDC semantics). ``on_commit`` runs inline when there is no open transaction.
  • Best-effort. A CH hiccup must NEVER break — or slow — PG ingestion. Every
    failure (including the row mapping) is logged and swallowed; the periodic
    backfill re-run reconciles any gap. PG remains the system of record.
  • Idempotent + versioned. Both targets are ReplacingMergeTree(version) keyed
    on the entity id; ``version`` picks the merge winner. Callers pass the
    already-fetched/created PG objects (one row per identity), so no PG re-read
    is needed — curated entities are create-once within the ingest transaction,
    so the in-hand object IS the committed state (re-reading would re-add the
    very hot-path PG round-trip this migration is removing).
  • Flag-gated. Shares ``dual_write_enabled()`` with ``trace_writer`` — same
    migration gate (the CDC chain being dropped is what turns both on).

NOTE — ``version`` is a CH ``DateTime64(6,'UTC')`` (schema 017/018), NOT the
integer-ns ``_version`` of ``traces``. So unlike ``trace_writer`` we pass a
tz-aware ``datetime`` (never ``time.time_ns()``). Live writes use ``now()`` so a
later live mirror always out-versions an earlier one AND a backfill re-run (which
versions by ``updated_at``) can never clobber a fresher live update — the exact
latest-wins invariant ``trace_writer`` documents.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import structlog

from tracer.services.clickhouse.v2 import get_v2_config

# Reuse trace_writer's gate verbatim — same migration, same switch. Keeping a
# single definition means the curated dual-write turns on/off with the traces one.
from tracer.services.clickhouse.v2.trace_writer import dual_write_enabled

log = structlog.get_logger("ch25.curated_writer")

# Column order for the INSERTs — must match the schema (017 / 018). The backfill
# command imports these so the column/row contract is locked in ONE place.
_END_USER_COLUMNS: tuple[str, ...] = (
    "project_id",
    "end_user_id",
    "organization_id",
    "user_id",
    "user_id_type",
    "user_id_hash",
    "metadata",
    "first_seen",
    "version",
    "is_deleted",
)
_TRACE_SESSION_COLUMNS: tuple[str, ...] = (
    "project_id",
    "trace_session_id",
    "external_session_id",
    "first_seen",
    "version",
    "is_deleted",
)

_client = None
_client_lock = threading.Lock()


def _get_client():
    """Lazily build a cached clickhouse-connect client. Reset on error so a
    transient CH outage doesn't wedge the cached handle permanently. Mirrors
    ``trace_writer._get_client`` (kept separate so the two writers don't share
    mutable state across a reset)."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            import clickhouse_connect

            cfg = get_v2_config()
            _client = clickhouse_connect.get_client(
                host=cfg["host"],
                port=cfg["http_port"],
                username=cfg["user"],
                password=cfg["password"] or "",
                database=cfg["database"],
                send_receive_timeout=15,
            )
    return _client


def _reset_client() -> None:
    global _client
    with _client_lock:
        try:
            if _client is not None:
                _client.close()
        except Exception:
            pass
        _client = None


def _metadata_to_text(v: Any) -> str:
    """PG ``EndUser.metadata`` is a JSONField (dict / list / str / None).

    The CH ``end_users.metadata`` column is a non-null String holding JSON, so
    coerce: None → '{}', dict/list → json.dumps, str → trust as-is. Shared with
    the backfill command so live + historical rows serialize identically.
    """
    if v is None:
        return "{}"
    if isinstance(v, str):
        return v
    return json.dumps(v, default=str, ensure_ascii=False)


def _version_value(obj, *, version_from_updated_at: bool) -> datetime:
    """Pick the ReplacingMergeTree merge winner as a tz-aware ``datetime``.

    Mirrors ``trace_writer._trace_to_row``'s flag, but the column is
    ``DateTime64(6,'UTC')`` (not integer-ns), so we return a ``datetime``:

    • Live dual-write (default): wall-clock ``now()`` UTC — a later live mirror
      always wins, and it is always >= any historical ``updated_at`` a backfill
      re-run would carry, so the backfill can never clobber a fresher live edit.
    • Backfill (``version_from_updated_at=True``): the row's own ``updated_at``
      (tz-coerced), so a re-run is an idempotent latest-wins no-op.
    """
    if version_from_updated_at:
        updated = obj.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        return updated
    return datetime.now(UTC)


def end_user_to_row(eu, *, version_from_updated_at: bool = False) -> list[Any]:
    """Map an ``EndUser`` model instance to a CH ``end_users`` row (column order
    above). P3a: ``end_user_id`` = PG ``id`` (no re-key). ``first_seen`` =
    ``created_at``; NULL ``user_id_hash``/``metadata`` coerce to '' / '{}'
    (non-null String columns); ``user_id_type`` stays None (the column / dict
    attr is Nullable).

    Reads ONLY local fields + the raw FK ids ``project_id`` / ``organization_id``
    — never ``eu.project.id`` / ``eu.organization.id`` (those would fire a PG
    SELECT per entity on the hot path, the exact round-trip this migration
    removes).
    """
    return [
        str(eu.project_id),
        str(eu.id),  # end_user_id = PG id (no re-key)
        str(eu.organization_id),
        eu.user_id or "",
        eu.user_id_type,  # Nullable — keep None as-is
        eu.user_id_hash or "",  # non-null String → '' on NULL
        _metadata_to_text(eu.metadata),
        eu.created_at,  # first_seen
        _version_value(eu, version_from_updated_at=version_from_updated_at),
        1 if getattr(eu, "deleted", False) else 0,
    ]


def trace_session_to_row(s, *, version_from_updated_at: bool = False) -> list[Any]:
    """Map a ``TraceSession`` model instance to a CH ``trace_sessions`` row
    (column order above). P3a: ``trace_session_id`` = PG ``id`` (no re-key);
    ``external_session_id`` = PG ``name``; ``first_seen`` = ``created_at``.

    Reads ONLY local fields + the raw FK id ``project_id`` — never
    ``s.project.id`` (avoids a per-entity PG round-trip on the hot path).
    """
    return [
        str(s.project_id),
        str(s.id),  # trace_session_id = PG id (no re-key)
        s.name or "",  # external_session_id = PG name
        s.created_at,  # first_seen
        _version_value(s, version_from_updated_at=version_from_updated_at),
        1 if getattr(s, "deleted", False) else 0,
    ]


def mirror_curated_dimensions_to_clickhouse(
    end_users: Iterable[Any] | None = None,
    sessions: Iterable[Any] | None = None,
) -> None:
    """Upsert the given PG ``EndUser`` / ``TraceSession`` objects into CH
    ``end_users`` / ``trace_sessions`` (one batched insert each).

    Best-effort: never raises and never blocks — wrap the whole body (mapping
    included) so a CH outage or a malformed row can NEVER break or slow PG
    ingestion. Call inside ``transaction.on_commit`` from the ingest creators,
    passing the objects already fetched/created by the existing PG
    ``get_or_create`` (P3a keeps that as the id source — do NOT remove it).
    """
    if not dual_write_enabled():
        return

    eu_list = [eu for eu in (end_users or []) if eu is not None]
    s_list = [s for s in (sessions or []) if s is not None]
    if not eu_list and not s_list:
        return

    try:
        client = _get_client()
        if eu_list:
            rows = [end_user_to_row(eu) for eu in eu_list]
            client.insert("end_users", rows, column_names=list(_END_USER_COLUMNS))
        if s_list:
            rows = [trace_session_to_row(s) for s in s_list]
            client.insert(
                "trace_sessions", rows, column_names=list(_TRACE_SESSION_COLUMNS)
            )
    except Exception as e:  # noqa: BLE001 — best-effort by design
        log.warning(
            "curated_dual_write_failed",
            err=str(e),
            n_end_users=len(eu_list),
            n_sessions=len(s_list),
        )
        _reset_client()
