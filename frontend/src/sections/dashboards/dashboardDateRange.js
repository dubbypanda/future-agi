// Date-range helpers for the dashboard's global date filter.
// `reference` is injectable so the logic is deterministic under test.

export function getDateRange(preset, reference = new Date()) {
  const now = new Date(reference);
  const start = new Date(reference);
  switch (preset) {
    case "today":
      start.setHours(0, 0, 0, 0);
      break;
    case "yesterday":
      start.setDate(start.getDate() - 1);
      start.setHours(0, 0, 0, 0);
      now.setDate(now.getDate() - 1);
      now.setHours(23, 59, 59, 999);
      break;
    case "7D":
      start.setDate(start.getDate() - 7);
      break;
    case "30D":
      start.setDate(start.getDate() - 30);
      break;
    case "3M":
      start.setMonth(start.getMonth() - 3);
      break;
    case "6M":
      start.setMonth(start.getMonth() - 6);
      break;
    case "12M":
      start.setMonth(start.getMonth() - 12);
      break;
    default:
      return null;
  }
  return { start: start.toISOString(), end: now.toISOString() };
}

// Resolve the global date override applied to every widget query:
// a custom [start, end] pair when the user picked one, otherwise the preset
// range, or null ("Default" — each widget keeps its own stored time range).
export function resolveGlobalDateRange(
  datePreset,
  customDateRange,
  reference = new Date(),
) {
  if (datePreset === "custom") {
    if (!customDateRange?.[0] || !customDateRange?.[1]) return null;
    return {
      start: customDateRange[0].toISOString(),
      end: customDateRange[1].toISOString(),
    };
  }
  return datePreset ? getDateRange(datePreset, reference) : null;
}
