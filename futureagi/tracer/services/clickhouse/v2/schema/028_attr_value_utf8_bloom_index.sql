-- 028 — Unicode-safe bloom index for string attribute equality/IN filters.
--
-- Public SPAN_ATTRIBUTE text equality is case-insensitive through lowerUTF8().
-- The older idx_attrs_str_values uses ASCII-only lower(), so using it as an
-- exhaustive graph/list witness could omit values such as the Kelvin sign.
-- Keep this expression byte-identical to latest_filter_predicates.py.
--
-- ADD INDEX is metadata-only. Materialize historical parts explicitly after
-- deploying this schema; never put the full-table mutation on boot/request:
--
--   ALTER TABLE spans MATERIALIZE INDEX idx_attrs_str_values_utf8;

ALTER TABLE spans
    ADD INDEX IF NOT EXISTS idx_attrs_str_values_utf8
    arrayMap(x -> lowerUTF8(x), mapValues(attrs_string))
    TYPE bloom_filter(0.01) GRANULARITY 1;
