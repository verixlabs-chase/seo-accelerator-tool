import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dashboardPath = fileURLToPath(
  new URL("../app/(product)/dashboard/page.tsx", import.meta.url),
);
const dashboardSource = readFileSync(dashboardPath, "utf8");

test("overview shows real performance before workflow details", () => {
  const performanceIndex = dashboardSource.indexOf("<SearchPerformanceOverview");
  const workflowIndex = dashboardSource.indexOf('eyebrow="Progress"');

  assert.notEqual(performanceIndex, -1);
  assert.notEqual(workflowIndex, -1);
  assert.ok(performanceIndex < workflowIndex);
});

test("overview leads with one decision, compact results, and a meaningful chart", () => {
  const decisionIndex = dashboardSource.indexOf("<OwnerDecisionBrief");
  const performanceIndex = dashboardSource.indexOf("<SearchPerformanceOverview");
  const metricIndex = dashboardSource.indexOf("<MetricStrip");
  const chartIndex = dashboardSource.indexOf("<ChartCard");

  assert.notEqual(decisionIndex, -1);
  assert.notEqual(performanceIndex, -1);
  assert.notEqual(metricIndex, -1);
  assert.notEqual(chartIndex, -1);
  assert.ok(decisionIndex < performanceIndex);
  assert.ok(metricIndex < chartIndex);
  assert.match(dashboardSource, /Do this next/);
  assert.match(dashboardSource, /Visits from Google/);
  assert.match(dashboardSource, /Source and update details/);
  assert.match(dashboardSource, /Change dates and comparison/);
  assert.doesNotMatch(dashboardSource, /Updated through/);
  assert.match(dashboardSource, /Math\.abs\(value\) < 0\.05/);
  assert.match(dashboardSource, /No clear change/);
});

test("customer discovery separates visits and appearances into readable comparisons", () => {
  assert.match(dashboardSource, /aria-label="Website visits trend"/);
  assert.match(dashboardSource, /aria-label="Google appearances trend"/);
  assert.match(dashboardSource, /Visits — selected dates/);
  assert.match(dashboardSource, /Visits — comparison dates/);
  assert.match(dashboardSource, /Times shown — selected dates/);
  assert.match(dashboardSource, /Times shown — comparison dates/);
  assert.doesNotMatch(dashboardSource, /label: "Earlier dates"/);
  assert.doesNotMatch(dashboardSource, /yAxisId="(?:clicks|impressions)"/);
});

test("overview uses one compact daily guide without generic good-to-know panels", () => {
  assert.equal(dashboardSource.match(/<TruthNotice\b/g)?.length || 0, 1);
  assert.doesNotMatch(dashboardSource, /Good to know/i);
  assert.doesNotMatch(dashboardSource, /Some checks take time to finish/i);
  assert.doesNotMatch(dashboardSource, /<ActionDrawer/);
});

test("overview removes duplicate legacy summaries and placeholder trend charts", () => {
  assert.doesNotMatch(dashboardSource, /eyebrow="At a glance"/);
  assert.doesNotMatch(dashboardSource, /eyebrow="Highlights"/);
  assert.doesNotMatch(dashboardSource, /VisibilityTrendChart/);
  assert.doesNotMatch(dashboardSource, /RankingTrendChart/);
  assert.doesNotMatch(dashboardSource, /Live API data/);
  assert.match(dashboardSource, /Progress and data details/);
});
