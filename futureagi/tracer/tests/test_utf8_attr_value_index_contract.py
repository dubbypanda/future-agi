from __future__ import annotations

from pathlib import Path

from tracer.services.clickhouse.v2.apply_schema_rewriter import (
    rewrite_for_replicated,
    split_statements,
)

SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "services/clickhouse/v2/schema/028_attr_value_utf8_bloom_index.sql"
)


def test_utf8_value_index_matches_filter_companion_expression() -> None:
    raw = SCHEMA.read_text()
    statements = split_statements(raw)

    assert len(statements) == 1
    assert (
        "arrayMap(x -> lowerUTF8(x), mapValues(attrs_string))" in statements[0]
    )
    assert "TYPE bloom_filter(0.01) GRANULARITY 1" in statements[0]
    assert "MATERIALIZE INDEX idx_attrs_str_values_utf8" in raw
    assert "MATERIALIZE INDEX" not in statements[0]


def test_utf8_value_index_survives_replicated_rewrite() -> None:
    statement = split_statements(SCHEMA.read_text())[0]
    rewritten = rewrite_for_replicated(
        statement,
        table_name="spans",
        cluster="default",
        zk_prefix="/clickhouse/tables",
    )

    assert "ON CLUSTER 'default'" in rewritten
    assert "idx_attrs_str_values_utf8" in rewritten
