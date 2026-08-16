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

test("content workspace is location-scoped and cannot draft or publish", () => {
  assert.match(page, /\/content\/workspace\?campaign_id=/);
  assert.match(page, /selectedCampaignId/);
  assert.match(page, /Nothing on this page can publish to your website/);
  assert.match(page, /not proof that a page change will improve rankings/);
  assert.doesNotMatch(page, /method:\s*"POST"/);
  assert.doesNotMatch(page, /method:\s*"PATCH"/);
});

test("brief review saves one explicit owner decision without changing the website", () => {
  assert.match(page, /\/content\/briefs\/\$\{encodeURIComponent\(brief\.id\)\}\/review/);
  assert.match(page, /method: "PUT"/);
  assert.match(page, /Accept page target/);
  assert.match(page, /Accept new page target/);
  assert.match(page, /Decline brief/);
  assert.match(page, /does not write or publish content/);
  assert.doesNotMatch(page, /Generate (?:a )?draft/i);
  assert.doesNotMatch(page, /Publish now/i);
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
