import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

const dashboardSource = source("../app/(product)/dashboard/page.tsx");
const opportunitiesSource = source("../app/(product)/opportunities/page.tsx");

test("owner journey v2 is independently releasable and enabled by default", () => {
  const visualSystemSource = source("../app/(product)/components/visualSystem.ts");
  const vercelExample = source("../.env.vercel.example");

  assert.match(visualSystemSource, /OWNER_JOURNEY_V2_ENABLED/);
  assert.match(visualSystemSource, /NEXT_PUBLIC_OWNER_JOURNEY_V2_ENABLED/);
  assert.match(vercelExample, /NEXT_PUBLIC_OWNER_JOURNEY_V2_ENABLED=true/);
  assert.match(dashboardSource, /OWNER_JOURNEY_V2_ENABLED/);
  assert.match(opportunitiesSource, /OWNER_JOURNEY_V2_ENABLED/);
});

test("overview keeps the five-second decision path ahead of optional details", () => {
  const decisionIndex = dashboardSource.indexOf("<OwnerDecisionBrief");
  const resultsIndex = dashboardSource.indexOf("<SearchPerformanceOverview");
  const progressIndex = dashboardSource.indexOf("Progress and data details");
  const controlsIndex = dashboardSource.indexOf("Manual setup and refresh tools");

  assert.ok(decisionIndex >= 0);
  assert.ok(resultsIndex > decisionIndex);
  assert.ok(progressIndex > resultsIndex);
  assert.ok(controlsIndex > progressIndex);
  assert.match(dashboardSource, /lg:grid-cols-\[1\.15fr_0\.85fr_1fr\]/);
  assert.match(dashboardSource, /xl:grid-cols-\[1\.25fr_0\.75fr\]/);
  assert.match(dashboardSource, /Google performance results/);
});

test("next steps exposes one cadence board and one working checklist", () => {
  assert.match(opportunitiesSource, /!OWNER_JOURNEY_V2_ENABLED/);
  assert.match(opportunitiesSource, /Your daily, weekly, and monthly checklist/);
  assert.match(opportunitiesSource, /Current checklist/);
  assert.match(opportunitiesSource, /grid gap-3 xl:grid-cols-3/);
  assert.match(opportunitiesSource, /grid gap-2 lg:grid-cols-3/);
  assert.match(opportunitiesSource, /aria-labelledby="current-checklist-title"/);
  assert.match(opportunitiesSource, /aria-pressed=\{isDone\}/);
  assert.match(opportunitiesSource, /All actions and supporting details/);
});

test("primary owner journey keeps technical and source detail optional", () => {
  assert.match(dashboardSource, /<DetailsDisclosure[\s\S]*Change dates and comparison/);
  assert.match(dashboardSource, /<DetailsDisclosure label="Source and update details"/);
  assert.match(opportunitiesSource, /Open the plain-language explanation/);
  assert.match(opportunitiesSource, /Advanced workflow tools/);
});
