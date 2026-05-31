"""trace_session_dict_reader — batch ``external_session_id`` lookups from the CH
``trace_sessions_dict`` (DESIGN §5.2, the Session-name reads cutover).

Why this exists
---------------
Before the CH-derived-dimensions migration the session list/detail builders
emitted ``session_name=None`` and the view back-filled it from PG
``TraceSession.name``. Once TraceSession's *external identity* moves to CH
(``trace_sessions`` RMT / ``trace_sessions_dict``), the session's external id —
the OTel ``session.id`` string the user passed — lives in the dict keyed by
``trace_session_id`` (the span's OWN soft-id column), NOT in PG.

The session display name is then
``COALESCE(overlay.display_name, trace_sessions_dict.external_session_id)``
(DESIGN §5.2): this module resolves the CH half (``external_session_id``); the
PG ``TraceSessionOverlay.display_name`` override is layered on top by the caller.

A CH ``dictGet`` cannot run inside a PG queryset, so the read path resolves the
per-session ``trace_session_id`` in PG/CH-spans first (a plain column read, no FK
join), then calls this module to batch-resolve the
``{trace_session_id -> external_session_id}`` labels from CH and merges in Python.
This module is the CH half of that restructure — a sibling of
``end_user_dict_reader`` for the Session dimension.

Faithfulness to the old back-fill semantics (the parity contract)
-----------------------------------------------------------------
The old back-fill produced ``None`` whenever no PG ``TraceSession`` row matched
the span's ``trace_session_id``. We reproduce it with ``dictGetOrNull``: a key
MISSING from the dict returns NULL (NOT the column's ``''`` default that a plain
``dictGet`` would give), so a session id with no curated row resolves to ``None``
exactly like the old PG miss did.

NOTE on the empty-string coercion: ``trace_sessions.external_session_id`` is a
non-null String (schema 018) populated from PG ``TraceSession.name`` (which is
``null=True``); the backfill/collector coerce PG NULL → ``''``. So a session
whose PG ``name`` was NULL surfaces ``''`` here, whereas the old back-fill (which
read ``name`` straight off the row) would surface ``None``. We normalize ``''`` →
``None`` so a name-less session renders identically OLD vs NEW. (A genuine
empty-string external id — none observed on the box — would also collapse to
``None``; accepted, the column is a display label.)

This module is read-only: a failure here is a real read error (parity reads must
surface problems, unlike the best-effort ingest dual-write), so it does NOT
swallow exceptions.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

import structlog

from tracer.services.clickhouse.v2 import get_v2_config

log = structlog.get_logger("ch25.trace_session_dict_reader")

# Dictionary + attribute the external session id is read from. Unqualified dict
# name: the query runs against the connection's configured database
# (CH25_DATABASE), so the SAME code resolves ``trace_sessions_dict`` in dev /
# test (ch_test) / prod — never hard-codes ``default`` (the apply_schema
# DB-switch rule, mirrored from ``end_user_dict_reader``).
_DICT_NAME = "trace_sessions_dict"
_LABEL_ATTR = "external_session_id"

_client = None
_client_lock = threading.Lock()


def _get_client():
    """Lazily build + cache a clickhouse-connect client (mirrors
    ``end_user_dict_reader._get_client``; kept separate so a reset here can't
    disturb the enduser reader's or writer's cached handle)."""
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


def resolve_external_session_ids(
    trace_session_ids: Iterable[object],
) -> dict[str, str | None]:
    """Batch-resolve ``{trace_session_id (str) -> external_session_id}`` from the
    CH ``trace_sessions_dict``.

    • Input ids are coerced to ``str`` and de-duplicated; ``None``/empty are
      dropped (the caller maps those to a ``None`` label without a lookup).
    • A key MISSING from the dict maps to ``None`` (faithful to the old
      PG-name-miss → NULL), via ``dictGetOrNull``.
    • A present-but-empty ``external_session_id`` (PG NULL ``name`` coerced to
      ``''`` on write) is normalized back to ``None`` so a name-less session
      renders identically OLD vs NEW.
    • Returns ``{}`` for empty input (no CH round-trip).

    The returned dict only contains keys that were looked up; callers must treat
    an absent key the same as a ``None`` value (both mean "no external id").
    """
    ids = {str(s) for s in trace_session_ids if s}
    if not ids:
        return {}

    client = _get_client()
    try:
        # arrayJoin over the literal id list resolves the whole batch in ONE
        # round-trip. dictGetOrNull keeps the missing-key → NULL semantics.
        result = client.query(
            (
                f"SELECT toString(sid), "
                f"dictGetOrNull('{_DICT_NAME}', '{_LABEL_ATTR}', sid) "
                f"FROM (SELECT arrayJoin(%(ids)s::Array(UUID)) AS sid)"
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
        # Normalize the non-null-String '' (PG NULL name coerced on write) back
        # to None — matches the old back-fill that read NULL straight off PG.
        out[row[0]] = row[1] or None
    return out
