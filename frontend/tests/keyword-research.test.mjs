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
  assert.match(page, /Best matches/);
  assert.match(page, /Needs your review/);
  assert.match(page, /Hidden as unrelated/);
  assert.match(page, /Google already finds you/);
  assert.match(page, /See the supporting data/);
  assert.match(page, /Demand is an estimate, not a promise of new jobs/);
  assert.doesNotMatch(page, /deterministic summary/i);
});

test("keyword research confirms real services before presenting strong matches", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /\/business-services\/discover/);
  assert.match(page, /Find services on your website/);
  assert.match(page, /What work should these searches match/);
  assert.match(page, /We offer this/);
  assert.match(page, /Not a service/);
  assert.match(page, /Matches \{item\.matched_service_name\}/);
});

test("keyword research confirms real service areas and keeps exclusions visible", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /\/business-service-areas\/suggest/);
  assert.match(page, /Where do you want these customers to come from/);
  assert.match(page, /Places this location serves/);
  assert.match(page, /Places this location does not serve/);
  assert.match(page, /We serve this area/);
  assert.match(page, /We do not serve here/);
  assert.match(page, /Outside area:/);
  assert.match(page, /\/business-service-areas\/nearby/);
  assert.match(page, /Find towns inside your work range/);
  assert.match(page, /Service area map/);
  assert.match(page, /Map suggestions never count as service areas until you approve them/);
  assert.match(page, /\/business-service-areas\/boundary/);
  assert.match(page, /Draw a custom work area/);
  assert.match(page, /Click at least 3 corners around the places your crew serves/);
  assert.match(page, /Save this work area/);
});

test("keyword research groups related customer needs and shows the likely website page", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /Plan related searches together/);
  assert.match(page, /service, customer need, and place/);
  assert.match(page, /Page to improve:/);
  assert.match(page, /Page opportunity:/);
  assert.match(page, /Review group/);
  assert.match(page, /Show every group/);
});

test("unclear-search AI review is a bounded action instead of a chatbot", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /\/keyword-research\/review-uncertain/);
  assert.match(page, /Use AI to sort unclear searches/);
  assert.match(page, /Checks up to 8 phrases against your confirmed services and service areas/);
  assert.match(page, /It cannot change your website/);
  assert.match(page, /AI checked/);
  assert.doesNotMatch(page, /placeholder="Ask AI/i);
  assert.doesNotMatch(page, /chatbot/i);
});

test("customer pages keep the market-data supplier private", () => {
  const keywordResearch = source("../app/(product)/keyword-research/page.tsx");
  const locations = source("../app/(product)/locations/page.tsx");
  const rankings = source("../app/(product)/rankings/page.tsx");

  assert.doesNotMatch(keywordResearch, /DataForSEO/);
  assert.doesNotMatch(locations, /DataForSEO/);
  assert.doesNotMatch(rankings, /DataForSEO/);
});
