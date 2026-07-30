export const SEARCH_DATE_RANGE_OPTIONS = [
  { value: "28", label: "Last 28 days" },
  { value: "90", label: "Last 3 months" },
  { value: "180", label: "Last 6 months" },
  { value: "365", label: "Last 12 months" },
  { value: "custom", label: "Choose dates" },
];

export const SEARCH_COMPARISON_OPTIONS = [
  { value: "previous_period", label: "Previous period" },
  { value: "previous_year", label: "Same dates last year" },
  { value: "custom", label: "Choose comparison dates" },
  { value: "none", label: "No comparison" },
];

const ALLOWED_PRESETS = new Set(["28", "90", "180", "365"]);
const ALLOWED_COMPARISONS = new Set([
  "previous_period",
  "previous_year",
  "custom",
  "none",
]);
const MAX_RANGE_DAYS = 480;

function parseDate(value, label) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) {
    throw new Error(`Choose a valid ${label}.`);
  }
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error(`Choose a valid ${label}.`);
  }
  return parsed;
}

function validateDatePair(dateFrom, dateTo, label) {
  const start = parseDate(dateFrom, `${label} start date`);
  const end = parseDate(dateTo, `${label} end date`);
  if (end < start) {
    throw new Error(`The ${label} end date must be after its start date.`);
  }
  const days = Math.floor((end.getTime() - start.getTime()) / 86400000) + 1;
  if (days > MAX_RANGE_DAYS) {
    throw new Error(`The ${label} date range cannot exceed ${MAX_RANGE_DAYS} days.`);
  }
}

export function buildSearchMetricsQuery(selection) {
  const preset = String(selection?.rangePreset || "90");
  const comparisonMode = String(selection?.comparisonMode || "previous_period");
  if (preset !== "custom" && !ALLOWED_PRESETS.has(preset)) {
    throw new Error("Choose a supported date range.");
  }
  if (!ALLOWED_COMPARISONS.has(comparisonMode)) {
    throw new Error("Choose a supported comparison.");
  }

  const params = new URLSearchParams();
  if (preset === "custom") {
    validateDatePair(selection?.dateFrom, selection?.dateTo, "selected");
    params.set("date_from", selection.dateFrom);
    params.set("date_to", selection.dateTo);
  } else {
    params.set("days", preset);
  }
  params.set("comparison_mode", comparisonMode);
  if (comparisonMode === "custom") {
    validateDatePair(
      selection?.comparisonDateFrom,
      selection?.comparisonDateTo,
      "comparison",
    );
    params.set("comparison_date_from", selection.comparisonDateFrom);
    params.set("comparison_date_to", selection.comparisonDateTo);
  }
  return params.toString();
}

export function alignSearchComparisonPoints(points = [], comparisonPoints = []) {
  const pointCount = Math.max(points.length, comparisonPoints.length);
  return Array.from({ length: pointCount }, (_, index) => {
    const current = points[index] || null;
    const comparison = comparisonPoints[index] || null;
    return {
      periodDay: index + 1,
      date: current?.date || null,
      comparisonDate: comparison?.date || null,
      clicks: current === null ? null : Number(current.clicks || 0),
      impressions: current === null ? null : Number(current.impressions || 0),
      avgPosition:
        current?.avg_position === null || current?.avg_position === undefined
          ? null
          : Number(current.avg_position),
      comparisonClicks:
        comparison === null ? null : Number(comparison.clicks || 0),
      comparisonImpressions:
        comparison === null ? null : Number(comparison.impressions || 0),
      comparisonAvgPosition:
        comparison?.avg_position === null ||
        comparison?.avg_position === undefined
          ? null
          : Number(comparison.avg_position),
    };
  });
}
