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

test("content workspace is location-scoped and cannot automatically generate or publish", () => {
  assert.match(page, /\/content\/workspace\?campaign_id=/);
  assert.match(page, /selectedCampaignId/);
  assert.match(page, /Nothing on this page can publish to your website/);
  assert.match(page, /not proof that a page change will improve rankings/);
  assert.doesNotMatch(page, /method:\s*"PATCH"/);
  assert.doesNotMatch(page, /governed-ai|mistral|draft_action/);
});

test("accepted briefs become owner-editable working drafts only", () => {
  assert.match(page, /\/content\/briefs\/\$\{encodeURIComponent\(brief\.id\)\}\/draft/);
  assert.match(page, /Start empty working draft/);
  assert.match(page, /working_drafts_available === true/);
  assert.match(page, /temporarily unavailable while storage is updated/);
  assert.match(page, /Editable working draft/);
  assert.match(page, /Save working draft/);
  assert.match(page, /cannot contact WordPress or publish/);
  assert.match(page, /Not approved or published/);
  assert.doesNotMatch(page, /Approve and publish/i);
});

test("optional AI wording stays separate from the owner draft", () => {
  assert.match(page, /\/content\/drafts\/\$\{encodeURIComponent\(draft\.id\)\}\/ai-suggestion/);
  assert.match(page, /Suggest wording with AI/);
  assert.match(page, /does not read or overwrite your section text/);
  assert.match(page, /AI wording suggestion — review before using/);
  assert.match(page, /This suggestion has not changed your working draft/);
  assert.match(page, /Save your changes first/);
  assert.doesNotMatch(page, /Apply AI wording/i);
  assert.doesNotMatch(page, /Publish suggestion/i);
});

test("title and search-description recommendations compare saved evidence without publishing", () => {
  assert.match(page, /Title and search-description recommendations/);
  assert.match(page, /Compared with the latest exact page evidence/);
  assert.match(page, /Proposed wording/);
  assert.match(page, /Character checks are writing guidance, not Google ranking rules/);
  assert.match(page, /These recommendations have not changed the working draft or website/);
  assert.match(page, /\(draft\.metadata_recommendations \|\| \[\]\)/);
  assert.doesNotMatch(page, /Apply metadata/i);
  assert.doesNotMatch(page, /Update WordPress now/i);
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
