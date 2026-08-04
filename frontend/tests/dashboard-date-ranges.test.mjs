import assert from "node:assert/strict";
import test from "node:test";

import {
  alignSearchComparisonPoints,
  buildSearchMetricsQuery,
} from "../app/(product)/truth/dashboardDateRanges.mjs";

test("dashboard date range builds a long previous-period comparison", () => {
  const query = new URLSearchParams(
    buildSearchMetricsQuery({
      rangePreset: "180",
      comparisonMode: "previous_period",
    }),
  );

  assert.equal(query.get("days"), "180");
  assert.equal(query.get("comparison_mode"), "previous_period");
  assert.equal(query.has("date_from"), false);
});

test("dashboard date range supports two independently chosen periods", () => {
  const query = new URLSearchParams(
    buildSearchMetricsQuery({
      rangePreset: "custom",
      dateFrom: "2026-04-01",
      dateTo: "2026-06-30",
      comparisonMode: "custom",
      comparisonDateFrom: "2025-04-01",
      comparisonDateTo: "2025-06-30",
    }),
  );

  assert.equal(query.get("date_from"), "2026-04-01");
  assert.equal(query.get("date_to"), "2026-06-30");
  assert.equal(query.get("comparison_mode"), "custom");
  assert.equal(query.get("comparison_date_from"), "2025-04-01");
  assert.equal(query.get("comparison_date_to"), "2025-06-30");
});

test("dashboard date range rejects reversed or oversized periods", () => {
  assert.throws(
    () =>
      buildSearchMetricsQuery({
        rangePreset: "custom",
        dateFrom: "2026-07-01",
        dateTo: "2026-06-01",
        comparisonMode: "none",
      }),
    /end date must be after/i,
  );
  assert.throws(
    () =>
      buildSearchMetricsQuery({
        rangePreset: "custom",
        dateFrom: "2024-01-01",
        dateTo: "2026-01-01",
        comparisonMode: "none",
      }),
    /cannot exceed 480 days/i,
  );
});

test("dashboard rejects comparisons with a different number of days", () => {
  assert.throws(
    () =>
      buildSearchMetricsQuery({
        rangePreset: "custom",
        dateFrom: "2026-07-01",
        dateTo: "2026-07-28",
        comparisonMode: "custom",
        comparisonDateFrom: "2026-06-01",
        comparisonDateTo: "2026-06-14",
      }),
    /same number of days/i,
  );
});

test("comparison chart aligns independently dated periods by day number", () => {
  const aligned = alignSearchComparisonPoints(
    [
      {
        date: "2026-07-01",
        clicks: 8,
        impressions: 200,
        avg_position: 9,
      },
      {
        date: "2026-07-02",
        clicks: 10,
        impressions: 240,
        avg_position: 8,
      },
    ],
    [
      {
        date: "2026-06-01",
        clicks: 4,
        impressions: 120,
        avg_position: 12,
      },
    ],
  );

  assert.deepEqual(aligned[0], {
    periodDay: 1,
    date: "2026-07-01",
    comparisonDate: "2026-06-01",
    clicks: 8,
    impressions: 200,
    avgPosition: 9,
    comparisonClicks: 4,
    comparisonImpressions: 120,
    comparisonAvgPosition: 12,
  });
  assert.equal(aligned[1].comparisonClicks, null);
});

test("comparison chart preserves missing calendar days instead of shifting later data", () => {
  const aligned = alignSearchComparisonPoints(
    [
      { date: "2026-07-01", clicks: 8, impressions: 200, avg_position: 9 },
      { date: "2026-07-03", clicks: 10, impressions: 240, avg_position: 8 },
    ],
    [
      { date: "2026-06-01", clicks: 4, impressions: 120, avg_position: 12 },
      { date: "2026-06-02", clicks: 5, impressions: 130, avg_position: 11 },
      { date: "2026-06-03", clicks: 6, impressions: 140, avg_position: 10 },
    ],
    {
      primaryDateFrom: "2026-07-01",
      comparisonDateFrom: "2026-06-01",
      primaryPeriodDays: 3,
      comparisonPeriodDays: 3,
    },
  );

  assert.equal(aligned[1].date, null);
  assert.equal(aligned[1].clicks, null);
  assert.equal(aligned[1].comparisonDate, "2026-06-02");
  assert.equal(aligned[2].date, "2026-07-03");
  assert.equal(aligned[2].comparisonDate, "2026-06-03");
});
