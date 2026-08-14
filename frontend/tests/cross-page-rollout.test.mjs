import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

const remainingRoutes = [
  "rankings",
  "keyword-research",
  "local-visibility",
  "site-health",
  "citations",
  "competitors",
  "organic-value",
  "ai-visibility",
  "locations",
  "reports",
  "settings",
];

test("cross-page rollout keeps useful results close to every page heading", () => {
  for (const route of remainingRoutes) {
    const pageSource = source(`../app/(product)/${route}/page.tsx`);
    const intro = pageSource.match(/<ProductPageIntro[\s\S]{0,700}?\/>/)?.[0] || "";

    assert.match(intro, /\bcompact\b/, `${route} does not use the compact first screen`);
    assert.equal(
      pageSource.match(/<TruthNotice\b/g)?.length || 0,
      1,
      `${route} should keep one dismissible guide`,
    );
  }
});

test("the weaker routes now lead with a current result and a real next action", () => {
  for (const route of [
    "site-health",
    "citations",
    "competitors",
    "organic-value",
    "ai-visibility",
    "locations",
    "reports",
    "settings",
  ]) {
    assert.match(
      source(`../app/(product)/${route}/page.tsx`),
      /<OwnerDecisionPanel/,
      `${route} is missing the shared owner decision panel`,
    );
  }

  const componentSource = source(
    "../app/(product)/components/OwnerDecisionPanel.tsx",
  );
  assert.match(componentSource, /Current result and next action/);
  assert.match(componentSource, /Do this next/);
  assert.match(componentSource, /role="progressbar"/);
  assert.match(componentSource, /aria-valuenow/);
  assert.match(componentSource, /<ProductIcon/);
});

test("each data-heavy route has a truthful decision visual", () => {
  assert.match(source("../app/(product)/rankings/page.tsx"), /Location comparison/);
  assert.match(source("../app/(product)/keyword-research/page.tsx"), /What customers search most/);
  assert.match(source("../app/(product)/local-visibility/page.tsx"), /<MapCard/);
  assert.match(source("../app/(product)/local-visibility/page.tsx"), /rankings appear after a map check/);
  assert.match(source("../app/(product)/local-visibility/page.tsx"), /typeof mapPackPosition === "number"/);
  assert.match(source("../app/(product)/local-visibility/page.tsx"), /value=\{hasHealthResult \? `\$\{healthScore\}\/100` : "Not checked"\}/);
  assert.match(source("../app/(product)/site-health/page.tsx"), /Core Web Vital/);
  assert.match(source("../app/(product)/site-health/page.tsx"), /Fix this first/);
  assert.match(source("../app/(product)/citations/page.tsx"), /Confirmed listing progress/);
  assert.match(source("../app/(product)/competitors/page.tsx"), /Exact searches and competing pages/);
  assert.match(source("../app/(product)/competitors/page.tsx"), /No made-up gap score/);
  assert.match(source("../app/(product)/organic-value/page.tsx"), /Estimated search value by scenario/);
  assert.match(source("../app/(product)/ai-visibility/page.tsx"), /Saved AI search facts/);
  assert.match(source("../app/(product)/ai-visibility/page.tsx"), /Missing services are not counted as zero/);
  assert.match(source("../app/(product)/locations/page.tsx"), /Locations with individual search tracking/);
  assert.match(source("../app/(product)/reports/page.tsx"), /Reports confirmed as delivered/);
  assert.match(source("../app/(product)/settings/page.tsx"), /Connected sources working normally/);
});

test("setup and duplicate console summaries no longer compete with priority data", () => {
  const locationsSource = source("../app/(product)/locations/page.tsx");
  const reportsSource = source("../app/(product)/reports/page.tsx");
  const healthSource = source("../app/(product)/site-health/page.tsx");

  assert.match(locationsSource, /<details[\s\S]*id="location-setup"/);
  assert.doesNotMatch(reportsSource, /What you can share/);
  assert.doesNotMatch(healthSource, />\s*Recommended action\s*</);
  assert.match(reportsSource, /<details[\s\S]*Report progress/);
});
