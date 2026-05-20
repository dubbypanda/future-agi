import {
  COLUMN_TYPE_ALIASES,
  FIELD_TYPE_ALIASES,
  FILTER_TYPE_ALLOWED_OPS,
  LIST_FILTER_OPS,
  NO_VALUE_FILTER_OPS,
  RANGE_FILTER_OPS,
} from "./filter-contract.generated";

const LIST_OP_SET = new Set(LIST_FILTER_OPS);
const RANGE_OP_SET = new Set(RANGE_FILTER_OPS);
const NO_VALUE_OP_SET = new Set(NO_VALUE_FILTER_OPS);
const ARRAY_VALUE_OP_SET = new Set(["contains", "not_contains"]);
const MULTI_VALUE_TYPES = new Set([
  "text",
  "categorical",
  "thumbs",
  "annotator",
]);
const API_FILTER_ITEM_KEYS = new Set([
  "column_id",
  "display_name",
  "source",
  "output_type",
  "filter_config",
]);
const UI_FILTER_ITEM_KEYS = new Set(["id", "_meta", "col_type"]);
const API_FILTER_CONFIG_KEYS = new Set([
  "filter_type",
  "filter_op",
  "filter_value",
  "col_type",
]);

export const normalizeFilterType = (rawType) => {
  if (!rawType) return "text";
  const type = String(rawType).toLowerCase();
  return FIELD_TYPE_ALIASES[type] || type;
};

export const normalizeColumnType = (rawColType) => {
  if (!rawColType) return undefined;
  return COLUMN_TYPE_ALIASES[String(rawColType).toLowerCase()] || rawColType;
};

const isMultiValueCandidate = (filterType, value) =>
  Array.isArray(value) && value.length > 1 && MULTI_VALUE_TYPES.has(filterType);

export const normalizeFilterOperator = (
  operator,
  { filterType, value } = {},
) => {
  const canonicalType = normalizeFilterType(filterType);
  let op = operator || "equals";

  if (
    isMultiValueCandidate(canonicalType, value) &&
    (op === "equals" || op === "not_equals")
  ) {
    op = op === "equals" ? "in" : "not_in";
  }

  return op;
};

export const isAllowedFilterOperator = (filterType, operator) => {
  const canonicalType = normalizeFilterType(filterType);
  return Boolean(FILTER_TYPE_ALLOWED_OPS[canonicalType]?.includes(operator));
};

export const coerceFilterValue = (value, filterOp, filterType) => {
  const canonicalType = normalizeFilterType(filterType);
  if (NO_VALUE_OP_SET.has(filterOp)) return null;

  if (canonicalType === "array" && ARRAY_VALUE_OP_SET.has(filterOp)) {
    const values = Array.isArray(value) ? value : [value];
    return values.filter(
      (item) => item !== "" && item !== null && item !== undefined,
    );
  }

  if (LIST_OP_SET.has(filterOp)) {
    const values = Array.isArray(value) ? value : [value];
    return values.filter(
      (item) => item !== "" && item !== null && item !== undefined,
    );
  }

  if (RANGE_OP_SET.has(filterOp)) {
    const values = Array.isArray(value) ? value : [value];
    return values.slice(0, 2).map((item) => {
      if (canonicalType !== "number" || item === "" || item === null)
        return item;
      const numeric = Number(item);
      return Number.isNaN(numeric) ? item : numeric;
    });
  }

  let scalar = Array.isArray(value) ? value[0] : value;
  if (
    canonicalType === "number" &&
    scalar !== "" &&
    scalar !== null &&
    scalar !== undefined
  ) {
    const numeric = Number(scalar);
    if (!Number.isNaN(numeric)) scalar = numeric;
  }
  if (canonicalType === "boolean") {
    if (scalar === "true") return true;
    if (scalar === "false") return false;
  }
  return scalar;
};

export const buildApiFilterFromPanelRow = (row) => {
  const filterType = normalizeFilterType(row?.fieldType);
  const filterOp = normalizeFilterOperator(row?.operator, {
    filterType,
    value: row?.value,
  });
  const filterValue = coerceFilterValue(row?.value, filterOp, filterType);
  const apiColType = normalizeColumnType(row?.apiColType || row?.fieldCategory);

  if (!isAllowedFilterOperator(filterType, filterOp)) {
    throw new Error(
      `Unsupported filter operator "${filterOp}" for type "${filterType}".`,
    );
  }

  return {
    column_id: row?.field,
    ...(row?.fieldName && { display_name: row.fieldName }),
    filter_config: {
      filter_type: filterType,
      filter_op: filterOp,
      filter_value: filterValue,
      ...(apiColType && { col_type: apiColType }),
    },
  };
};

const isEmptyFilterDraft = (filter) => {
  const config = filter?.filter_config || {};
  return (
    !filter?.column_id &&
    !config.filter_type &&
    !config.filter_op &&
    (config.filter_value === "" ||
      config.filter_value === undefined ||
      config.filter_value === null)
  );
};

export const serializeFilterForApi = (filter) => {
  if (!filter || typeof filter !== "object") {
    throw new Error("API filters must be objects.");
  }

  const unknownItemKeys = Object.keys(filter).filter(
    (key) => !API_FILTER_ITEM_KEYS.has(key) && !UI_FILTER_ITEM_KEYS.has(key),
  );
  if (unknownItemKeys.length) {
    throw new Error(`Unknown API filter keys: ${unknownItemKeys.join(", ")}`);
  }

  const columnId = filter.column_id;
  const config = filter.filter_config;
  if (!columnId || !config || typeof config !== "object") {
    throw new Error("API filters require column_id and filter_config.");
  }

  const unknownConfigKeys = Object.keys(config).filter(
    (key) => !API_FILTER_CONFIG_KEYS.has(key),
  );
  if (unknownConfigKeys.length) {
    throw new Error(
      `Unknown API filter_config keys: ${unknownConfigKeys.join(", ")}`,
    );
  }

  const filterType = normalizeFilterType(config.filter_type);
  const filterOp = normalizeFilterOperator(config.filter_op, {
    filterType,
    value: config.filter_value,
  });
  if (!isAllowedFilterOperator(filterType, filterOp)) {
    throw new Error(
      `Unsupported filter operator "${filterOp}" for type "${filterType}".`,
    );
  }

  const filterValue = coerceFilterValue(
    config.filter_value,
    filterOp,
    filterType,
  );
  if (
    filterOp !== "is_null" &&
    filterOp !== "is_not_null" &&
    (filterValue === "" ||
      filterValue === undefined ||
      (Array.isArray(filterValue) && filterValue.length === 0))
  ) {
    throw new Error(
      `Filter "${columnId}" requires a value for operator "${filterOp}".`,
    );
  }

  return {
    column_id: columnId,
    ...(filter.display_name && { display_name: filter.display_name }),
    ...(filter.source && { source: filter.source }),
    ...(filter.output_type && { output_type: filter.output_type }),
    filter_config: {
      filter_type: filterType,
      filter_op: filterOp,
      filter_value: filterValue,
      ...(config.col_type && { col_type: normalizeColumnType(config.col_type) }),
    },
  };
};

export const serializeFilterListForApi = (filters = []) =>
  filters.filter((filter) => !isEmptyFilterDraft(filter)).map(serializeFilterForApi);
