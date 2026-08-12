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
  assert.match(page, /monthly search estimates/);
  assert.match(page, /Google search history/);
  assert.doesNotMatch(page, /DataForSEO/);
  assert.doesNotMatch(page, /run\.warnings\.map/);
  assert.match(page, /Some search estimates could not update/);
  assert.doesNotMatch(page, /seed keyword/i);
});

test("keyword research keeps business-owner language ahead of technical evidence", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /Close to the top/);
  assert.match(page, /Best matches/);
  assert.match(page, /Needs your review/);
  assert.match(page, /Hidden as unrelated/);
  assert.match(page, /Google already finds you/);
  assert.match(page, /Why this search is listed/);
  assert.match(page, /Search counts are estimates, not promised jobs/);
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
  assert.match(page, /\/business-service-areas\/drive-time/);
  assert.match(page, /By driving time/);
  assert.match(page, /Use driving time/);
  assert.match(page, /Uses the road network, not live traffic/);
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
  assert.match(page, /Review unclear searches/);
  assert.match(page, /Checks up to 8 phrases against your confirmed services and service areas/);
  assert.match(page, /It cannot change your website/);
  assert.match(page, /Reviewed/);
  assert.doesNotMatch(page, /placeholder="Ask AI/i);
  assert.doesNotMatch(page, /chatbot/i);
});

test("business owners can correct search relevance without opening a chatbot", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /\/keyword-research\/feedback/);
  assert.match(page, /Matches this service/);
  assert.match(page, /Not relevant/);
  assert.match(page, /Undo my choice/);
  assert.match(page, /Saved from your choice/);
});

test("saved competitors can reveal gaps without being confused with the owner's rank", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /Competitor opportunity/);
  assert.match(page, /Competitor search results/);
  assert.match(page, /Seen from/);
  assert.match(page, /competitor\.position/);
  assert.match(page, /href=\{competitor\.url\}/);
});

test("saved research dates show keyword movement without buying another comparison", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /What changed since the last research/);
  assert.match(page, /data\.history\.comparison/);
  assert.match(page, /Estimated searches\/month/);
  assert.match(page, /Helpful searches/);
  assert.match(page, /New searches found/);
  assert.match(page, /Searches moving up/);
  assert.match(page, /item\.trend\.label/);
  assert.match(page, /Search counts are estimates, not promised jobs/);
});

test("keyword intelligence measures owner checks and creates governed next steps", () => {
  const page = source("../app/(product)/keyword-research/page.tsx");

  assert.match(page, /Your saved choices/);
  assert.match(page, /matched your answer/);
  assert.match(page, /\/keyword-research\/create-action/);
  assert.match(page, /Add to Next Steps/);
  assert.match(page, /In Next Steps/);
  assert.match(page, /Check again after rankings or search estimates are available/);
  assert.doesNotMatch(page, /automatically change your website/i);
});

test("customer keyword sources use product labels instead of supplier identifiers", () => {
  const keywordResearch = source("../app/(product)/keyword-research/page.tsx");

  assert.match(keywordResearch, /live_rankings: "Live rankings"/);
  assert.match(keywordResearch, /related_searches: "Related searches"/);
  assert.match(keywordResearch, /local_demand: "Search estimates"/);
});
