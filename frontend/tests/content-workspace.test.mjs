import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/content/page.tsx", import.meta.url)),
  "utf8",
);
const nav = readFileSync(
  fileURLToPath(new URL("../app/(product)/nav.config.ts", import.meta.url)),
  "utf8",
);

test("content workspace is location-scoped and read-only", () => {
  assert.match(page, /\/content\/workspace\?campaign_id=/);
  assert.match(page, /selectedCampaignId/);
  assert.match(page, /Nothing on this page can publish to your website/);
  assert.match(page, /not proof that a page change will improve rankings/);
  assert.doesNotMatch(page, /method:\s*"POST"/);
  assert.doesNotMatch(page, /method:\s*"PATCH"/);
});

test("saved pages and evidence-backed briefs have plain next steps", () => {
  assert.match(page, /Content briefs ready for review/);
  assert.match(page, /Saved website pages/);
  assert.match(page, /Confirmed competitor/);
  assert.match(page, /Customer search/);
  assert.match(page, /Review the suggested page outline/);
  assert.match(page, /No clear issue in this saved check/);
  assert.match(page, /A page with no listed issue is not a promise/);
});

test("content workspace is reachable from product navigation", () => {
  assert.match(nav, /href: "\/content", label: "Content", icon: "content"/);
});
