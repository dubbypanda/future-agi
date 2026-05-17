export const LEGACY_API_STATUSES = Object.freeze({
  ACTIVE_UNCONTRACTED: "active_uncontracted",
  DEPRECATED_DEAD_REFERENCE: "deprecated_dead_reference",
  EE_UNCONTRACTED: "ee_uncontracted",
});

// Central allowlist for pre-contract Management API paths. New frontend API
// calls should use apiPath(...) against the generated Swagger surface instead.
export const LEGACY_API_SURFACE = Object.freeze({
  "/model-hub/ai_models/create/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management create endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai_models/delete/{id}/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management delete endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai_models/update-baseline/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management baseline endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai-models/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management list/detail endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai-models/list/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management list endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai-models/performance": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management performance endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/ai-models/update-metric/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model-management metric endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/model-hub/data-points/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model data-point list endpoint is still used by dataset detail screens.",
    next: "Contract the old data-points API or migrate dataset detail screens to the newer dataset APIs.",
  },
  "/model-hub/data-points/column-config/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model data-point column config endpoint is still used by dataset detail screens.",
    next: "Contract the old data-points API or migrate dataset detail screens to the newer dataset APIs.",
  },
  "/model-hub/data-points/create/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model data-point create endpoint is still used by dataset detail screens.",
    next: "Contract the old data-points API or migrate dataset detail screens to the newer dataset APIs.",
  },
  "/model-hub/data-points/metrics/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model data-point metric endpoint is still used by dataset detail screens.",
    next: "Contract the old data-points API or migrate dataset detail screens to the newer dataset APIs.",
  },
  "/model-hub/dataset/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset list/detail endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/dataset/column-config/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset column config endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/dataset/create/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset create endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/dataset/options/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset options endpoint is still used by custom metric screens.",
    next: "Contract the old model dataset API or retire the legacy custom metric flow.",
  },
  "/model-hub/dataset/properties/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset properties endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/dataset/properties/{id}/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset property detail endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/dataset/summary": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Legacy model dataset summary endpoint is still used by old model dataset screens.",
    next: "Contract the old model dataset API or retire the legacy model dataset screens.",
  },
  "/model-hub/get-eval-feedback": {
    group: "evals",
    status: LEGACY_API_STATUSES.DEPRECATED_DEAD_REFERENCE,
    reason: "Old eval feedback route is no longer registered in backend URLs.",
    next: "Remove the old eval feedback call site or use the contracted feedback endpoints.",
  },
  "/model-hub/get-model-details/": {
    group: "model-management",
    status: LEGACY_API_STATUSES.ACTIVE_UNCONTRACTED,
    reason:
      "Old model detail endpoint is still referenced by the legacy Models UI.",
    next: "Contract the old model-management API or retire the legacy Models UI.",
  },
  "/usage/available-months/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage billing available-months endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/create-topup-session/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Top-up billing endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE billing endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/billing-overview/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 billing overview endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/budgets/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 budgets endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/budgets/{id}/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 budget detail endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/invoices/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 invoices endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/invoices/{id}/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 invoice detail endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/notifications/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 notifications endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/plans-and-addons/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 plans/addons endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/usage-overview/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 overview endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/usage-time-series/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 time-series endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
  "/usage/v2/usage-workspace-breakdown/": {
    group: "usage",
    status: LEGACY_API_STATUSES.EE_UNCONTRACTED,
    reason:
      "Usage V2 workspace breakdown endpoint is EE-backed and not fully exposed in Swagger.",
    next: "Expose the EE usage V2 endpoint in Swagger or hide this UI when the endpoint is unavailable.",
  },
});
