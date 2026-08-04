import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("keyword research is location-aware, automatic, and promotes searches into tracking", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");
  const nav = source("../app/(product)/nav.config.ts");

  assert.match(nav, /href: "\/keyword-research", label: "Find Searches"/);
  assert.match(page, /useLocationContext/);
  assert.match(page, /\/keyword-research\/discover/);
  assert.match(page, /\/keyword-research\/track/);
  assert.match(page, /Find real searches without building a list by hand/);
  assert.match(page, /What customers search most/);
  assert.match(page, /Track selected/);
  assert.match(page, /connected market research/);
  assert.match(page, /Google search history/);
  assert.doesNotMatch(page, /DataForSEO/);
  assert.doesNotMatch(page, /run\.warnings\.map/);
  assert.match(page, /Fresh market data needs another try/);
  assert.doesNotMatch(page, /seed keyword/i);
});

test("keyword research keeps business-owner language ahead of technical evidence", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /Close to the top/);
  assert.match(page, /New opportunities/);
  assert.match(page, /Google already finds you/);
  assert.match(page, /See the supporting data/);
  assert.match(page, /Demand is an estimate, not a promise of new jobs/);
  assert.doesNotMatch(page, /deterministic summary/i);
});

test("customer pages keep the market-data supplier private", () => {
  const keywordResearch = source("../app/(product)/keyword-research/page.tsx");
  const locations = source("../app/(product)/locations/page.tsx");
  const rankings = source("../app/(product)/rankings/page.tsx");

  assert.doesNotMatch(keywordResearch, /DataForSEO/);
  assert.doesNotMatch(locations, /DataForSEO/);
  assert.doesNotMatch(rankings, /DataForSEO/);
});
