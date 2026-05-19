"""Shared input-validation rules for eval execution.

A single source of truth for "what counts as empty" and "when does an eval
refuse to run vs. attach a warning". Called from every entry point that
runs an eval (dataset, playground, tracing eval tasks, simulation, SDK)
so behavior stays consistent regardless of how the eval was invoked.

The rules:
  - System evals (``config.custom_eval`` false): per-key strict — any
    required/optional key whose value is empty raises a per-key error.
  - User-built custom evals (``config.custom_eval`` true): at least one
    mapped variable must have a non-empty value. If none do, raise. If
    some mapped variables are empty but at least one has a value, return
    a partial_input warning payload that callers attach to the eval
    result so the operator can spot rows whose result may be unreliable.

See ``docs/superpowers/specs/2026-05-18-eval-optional-inputs-design.md``.
"""

from __future__ import annotations

import json
from typing import Any


def is_empty_value(value: Any) -> bool:
    """Return True when ``value`` is effectively empty for eval purposes."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            return False
        if parsed == value:
            return False
        return is_empty_value(parsed)
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0 or all(is_empty_value(item) for item in value)
    if isinstance(value, dict):
        return len(value) == 0 or all(is_empty_value(item) for item in value.values())
    return False


def _normalize_key_set(keys: Any) -> set[str]:
    if not keys:
        return set()
    if isinstance(keys, str):
        return {keys}
    try:
        return {str(key) for key in keys if key is not None}
    except TypeError:
        return {str(keys)}


def _declared_keys(config: dict[str, Any]) -> set[str]:
    return _normalize_key_set(config.get("required_keys")) | _normalize_key_set(
        config.get("optional_keys")
    )


def validate_eval_inputs(
    eval_template, values: dict[str, Any], mapped_keys: Any | None = None
) -> tuple[dict | None, dict[str, Any]]:
    """Apply the partial-input rules and normalize the input kwargs.

    ``mapped_keys`` is the set of declared eval variables that are actually
    wired for this run. Dataset/tracing callers should pass it so unmapped
    template variables do not create spurious warnings or all-empty errors.
    Direct callers without mapping metadata keep the historical fallback:
    every declared variable is considered expected.
    """
    config = getattr(eval_template, "config", None) or {}
    declared_keys = _declared_keys(config)
    if not declared_keys:
        return None, values

    if mapped_keys is None:
        keys_to_check = declared_keys
    else:
        keys_to_check = declared_keys & _normalize_key_set(mapped_keys)

    if not keys_to_check:
        return None, values

    is_custom_eval = bool(config.get("custom_eval", False))

    if is_custom_eval:
        empty = sorted(
            k for k in keys_to_check
            if k not in values or is_empty_value(values.get(k))
        )
        nonempty = sorted(
            k for k in keys_to_check
            if k in values and not is_empty_value(values.get(k))
        )

        if not nonempty:
            keys_label = ", ".join(f"'{k}'" for k in sorted(keys_to_check))
            raise ValueError(
                f"No input received for any of {keys_label}. "
                "Please check your inputs."
            )

        normalized = dict(values)
        for k in declared_keys:
            if k not in normalized:
                normalized[k] = ""

        warning = None
        if empty:
            warning = {
                "type": "partial_input",
                "empty_keys": empty,
                "filled_keys": nonempty,
                "message": (
                    "Eval ran with some inputs empty. "
                    "Result may be less reliable. "
                    "Ignore if this is intentional."
                ),
            }
        return warning, normalized

    for key in sorted(k for k in keys_to_check if k in values):
        if is_empty_value(values[key]):
            raise ValueError(
                f"No input received for '{key}'. Please check your input."
            )
    return None, values
