"""end_user_dict_reader — batch ``user_id`` label lookups from the CH
``end_users_dict`` (DESIGN §4.3, the EndUser reads cutover).

Why this exists
---------------
Before the CH-derived-dimensions migration, callers resolved an EndUser's
external ``user_id`` label by traversing the PG ``ObservationSpan.end_user`` FK
into ``tracer_enduser`` (``end_user__user_id``). Once EndUser moves to CH, the PG
``tracer_enduser`` table is gone, so the label now lives in the CH
``end_users_dict`` keyed by ``end_user_id`` (the span's OWN soft-id column).

A CH ``dictGet`` cannot run inside a PG queryset, so the read paths that used a
correlated ``Subquery``/``OuterRef`` must RESTRUCTURE: resolve the per-entity
``end_user_id`` in PG (a plain column read, no FK join), then call this module to
batch-resolve the ``{end_user_id -> user_id}`` labels from CH, and merge in
Python. This module is the CH half of that restructure.

Faithfulness to the old FK semantics (the parity contract)
----------------------------------------------------------
The old ``Subquery(...values("end_user__user_id"))`` yields **NULL** in three
cases: the span's ``end_user_id`` is NULL, the FK points at a row that does not
exist (``db_constraint=False`` allows orphans), or the joined ``user_id`` is
NULL. We reproduce exactly:

  • Callers never pass a NULL ``end_user_id`` here (they map it to ``None``
    label without calling this module), covering the first case.
  • For a present ``end_user_id`` we use ``dictGetOrNull`` — a MISSING dict key
    returns NULL (NOT the column's ``''`` default that plain ``dictGet`` would
    give), so an orphan id resolves to ``None`` exactly like the FK miss did.

This module is read-only and best-effort-free: a failure here is a real read
error (unlike the ingest dual-write, parity reads must surface problems), so it
does NOT swallow exceptions.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

import structlog

from tracer.services.clickhouse.v2 import get_v2_config

log = structlog.get_logger("ch25.end_user_dict_reader")

# Dictionary + attribute the label is read from. Unqualified dict name: the
# query runs against the connection's configured database (CH25_DATABASE), so
# the SAME code resolves ``end_users_dict`` in dev / test (ch_test) / prod —
# never hard-codes ``default`` (the schema/apply_schema DB-switch rule).
_DICT_NAME = "end_users_dict"
_LABEL_ATTR = "user_id"

_client = None
_client_lock = threading.Lock()


def _get_client():
    """Lazily build + cache a clickhouse-connect client (mirrors
    ``curated_writer._get_client``; kept separate so a reset here can't disturb
    the writer's cached handle)."""
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


def resolve_user_ids(end_user_ids: Iterable[object]) -> dict[str, str | None]:
    """Batch-resolve ``{end_user_id (str) -> user_id label}`` from the CH
    ``end_users_dict``.

    • Input ids are coerced to ``str`` and de-duplicated; ``None``/empty are
      dropped (the caller maps those to a ``None`` label without a lookup).
    • A key MISSING from the dict maps to ``None`` (faithful to the old FK-miss
      → NULL), via ``dictGetOrNull``.
    • Returns ``{}`` for empty input (no CH round-trip).

    The returned dict only contains keys that were looked up; callers must treat
    an absent key the same as a ``None`` value (both mean "no label").
    """
    ids = {str(e) for e in end_user_ids if e}
    if not ids:
        return {}

    client = _get_client()
    try:
        # arrayJoin over the literal id list resolves the whole batch in ONE
        # round-trip. dictGetOrNull keeps the missing-key → NULL semantics.
        result = client.query(
            (
                f"SELECT toString(eid), "
                f"dictGetOrNull('{_DICT_NAME}', '{_LABEL_ATTR}', eid) "
                f"FROM (SELECT arrayJoin(%(ids)s::Array(UUID)) AS eid)"
            ),
            parameters={"ids": list(ids)},
        )
    except Exception:
        # A read error is real (parity must not silently degrade). Reset the
        # cached handle so a transient CH blip doesn't wedge it, then re-raise.
        _reset_client()
        raise

    out: dict[str, str | None] = {}
    for row in result.result_rows:
        out[row[0]] = row[1]
    return out
