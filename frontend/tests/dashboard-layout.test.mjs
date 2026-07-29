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

test("overview orders real graphs before the supporting metric cards", () => {
  const graphOrderClassIndex = dashboardSource.indexOf(
    'className="order-1 grid gap-5 xl:grid-cols-2"',
  );
  const metricOrderClassIndex = dashboardSource.indexOf(
    'className="order-2 grid gap-4 xl:grid-cols-4"',
  );
  const summaryOrderClassIndex = dashboardSource.indexOf(
    'className="order-3 border-l-2',
  );

  assert.notEqual(graphOrderClassIndex, -1);
  assert.notEqual(metricOrderClassIndex, -1);
  assert.notEqual(summaryOrderClassIndex, -1);
  assert.ok(graphOrderClassIndex > metricOrderClassIndex);
});

test("overview does not render large generic good-to-know panels", () => {
  assert.doesNotMatch(dashboardSource, /<TruthNotice/);
  assert.doesNotMatch(dashboardSource, /Good to know/i);
  assert.doesNotMatch(dashboardSource, /Some checks take time to finish/i);
  assert.doesNotMatch(dashboardSource, /<ActionDrawer/);
});

test("overview removes duplicate legacy summaries and placeholder trend charts", () => {
  assert.doesNotMatch(dashboardSource, /eyebrow="At a glance"/);
  assert.doesNotMatch(dashboardSource, /eyebrow="Highlights"/);
  assert.doesNotMatch(dashboardSource, /VisibilityTrendChart/);
  assert.doesNotMatch(dashboardSource, /RankingTrendChart/);
});
