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
  const workflowIndex = dashboardSource.indexOf('eyebrow="Workflow status"');

  assert.notEqual(performanceIndex, -1);
  assert.notEqual(workflowIndex, -1);
  assert.ok(performanceIndex < workflowIndex);
});

test("overview does not render large generic good-to-know panels", () => {
  assert.doesNotMatch(dashboardSource, /<TruthNotice/);
  assert.doesNotMatch(dashboardSource, /Good to know/i);
  assert.doesNotMatch(dashboardSource, /Some checks take time to finish/i);
});

test("overview removes duplicate legacy summaries and placeholder trend charts", () => {
  assert.doesNotMatch(dashboardSource, /eyebrow="At a glance"/);
  assert.doesNotMatch(dashboardSource, /eyebrow="Highlights"/);
  assert.doesNotMatch(dashboardSource, /VisibilityTrendChart/);
  assert.doesNotMatch(dashboardSource, /RankingTrendChart/);
});
