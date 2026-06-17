"""
Single rewrite boundary for the v2 query builders.

Every v2 builder subclasses its v1 counterpart and must translate the v1-compiled
SQL (legacy column/dict names, String-JSON access) to the CH 25.3 schema — and
append the v2 SETTINGS — before the SQL leaves the builder. Historically each
builder did this by hand-overriding every SQL-emitting method to call
`rewrite_and_apply_v2_settings()`. That override list drifted out of sync with
the v1 base class: any newly-inherited v1 method shipped raw v1 SQL and 500'd on a
v2-only (`CH_DATABASE=futureagi`) box — `enduser_dict` / `tracer_enduser` /
`_peerdb_is_deleted` against objects that don't exist there (TH-5911, TH-5964).

`V2RewriteMixin` moves the rewrite to ONE boundary. `__init_subclass__` wraps every
`build*` method on the subclass — inherited from the v1 base or defined locally —
so its emitted SQL is always routed through the rewriter. A new inherited v1 method
cannot ship un-rewritten SQL; nobody has to remember to add an override.

Mix it in FIRST so the wrapper resolves ahead of the v1 base in the MRO:

    class TraceListQueryBuilderV2(V2RewriteMixin, TraceListQueryBuilder): ...

`rewrite_and_apply_v2_settings` is idempotent on already-v2 SQL (v1 token patterns
don't match; the SETTINGS append merges rather than duplicates), so wrapping a
method that already emits v2-native SQL (e.g. the trace-list rollup fast-path) is a
harmless no-op.

NOTE: the filter builder (`ClickHouseFilterBuilderV2`) deliberately does NOT use
this mixin — its `translate` / `translate_sort` emit WHERE/ORDER *fragments* that
must not carry a trailing SETTINGS clause (would be a syntax error).
"""

from __future__ import annotations

import functools
from collections.abc import Callable

from tracer.services.clickhouse.v2.query_builders.filters import (
    rewrite_and_apply_v2_settings,
)

# Marks a method as already wrapped, so re-subclassing never double-wraps it.
_WRAPPED_ATTR = "_v2_rewrite_wrapped"


def _rewrite_sql_in(result: object) -> object:
    """Apply the v1→v2 rewrite to whatever SQL a builder method returned.

    Shape-aware — covers the three real return shapes across the v1 builders:
      • ``(sql, params)``              → rewrite ``sql``, keep ``params``
      • ``[(sql, params, meta), ...]`` → rewrite each element's ``sql``
        (only ``dashboard.build_all_queries``)
      • anything else                  → returned unchanged (defensive)

    A falsey ``sql`` is returned untouched so the empty-input contract
    (e.g. ``build_user_id_query([]) -> ("", {})``) is preserved.
    """
    # (sql, params) tuple — the common case for every build_* method.
    if (
        isinstance(result, tuple)
        and len(result) == 2
        and isinstance(result[0], str)
        and isinstance(result[1], dict)
    ):
        sql, params = result
        if not sql:
            return result
        return rewrite_and_apply_v2_settings(sql), params

    # [(sql, params, meta), ...] — dashboard.build_all_queries.
    if (
        isinstance(result, list)
        and result
        and all(
            isinstance(el, tuple) and len(el) >= 1 and isinstance(el[0], str)
            for el in result
        )
    ):
        rewritten = []
        for el in result:
            sql = el[0]
            new_sql = sql if not sql else rewrite_and_apply_v2_settings(sql)
            rewritten.append((new_sql, *el[1:]))
        return rewritten

    return result


def _wrap(method: Callable[..., object]) -> Callable[..., object]:
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        return _rewrite_sql_in(method(self, *args, **kwargs))

    setattr(wrapper, _WRAPPED_ATTR, True)
    return wrapper


class V2RewriteMixin:
    """Route every ``build*`` method's SQL output through the v2 rewriter.

    Wrapping happens at subclass-creation time, so it covers methods inherited
    from the v1 base as well as any the subclass defines itself. The default —
    "wrap everything" — is the safe one because almost every builder method
    targets the migrated `spans` schema.

    A method is skipped only if its name is in ``_v2_rewrite_exclude``. The sole
    legitimate exclusions are methods whose SQL targets tables that are NOT part
    of the CH 25.3 migration and therefore still carry the legacy column names
    (e.g. `build_eval_query` / `build_annotation_query`, which read the legacy
    `tracer_eval_logger` / `model_hub_score` tables that keep
    `_peerdb_is_deleted`). Rewriting those would break them. Keep the exclude set
    small and document each entry at the subclass.
    """

    # Subclasses override with the set of `build*` method names that must NOT be
    # rewritten (they target non-migrated legacy tables). See class docstring.
    _v2_rewrite_exclude: frozenset[str] = frozenset()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        exclude = cls._v2_rewrite_exclude
        for name in dir(cls):
            if not name.startswith("build") or name in exclude:
                continue
            method = getattr(cls, name, None)
            if not callable(method) or getattr(method, _WRAPPED_ATTR, False):
                continue
            setattr(cls, name, _wrap(method))


__all__ = ["V2RewriteMixin"]
