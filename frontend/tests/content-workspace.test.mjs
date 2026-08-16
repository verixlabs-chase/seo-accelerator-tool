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

test("content workspace is location-scoped and cannot automatically publish", () => {
  assert.match(page, /\/content\/workspace\?campaign_id=/);
  assert.match(page, /selectedCampaignId/);
  assert.match(page, /Nothing on this page can publish a public website page/);
  assert.match(page, /Publishing it publicly remains outside this workflow/);
  assert.doesNotMatch(page, /method:\s*"PATCH"/);
  assert.doesNotMatch(page, /governed-ai|mistral|draft_action/);
});

test("publishing handoff separates preview, exact approval, and non-public draft creation", () => {
  assert.match(page, /WordPress draft handoff/);
  assert.match(page, /Prepare WordPress draft preview/);
  assert.match(page, /\/publishing-handoff\$\{suffix\}/);
  assert.match(page, /reviewed_exact_preview: true/);
  assert.match(page, /understands_wordpress_draft: true/);
  assert.match(page, /understands_not_public: true/);
  assert.match(page, /Approve this exact draft preview/);
  assert.match(page, /Create non-public WordPress draft/);
  assert.match(page, /approval_and_delivery_are_separate/);
  assert.match(page, /This workflow never requests a public page/);
  assert.match(page, /Existing-page replacement is not enabled yet/);
  assert.doesNotMatch(page, />Publish now</i);
  assert.doesNotMatch(page, />Approve and publish</i);
  assert.doesNotMatch(page, />Create public page</i);
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

test("structured page details stay evidence-backed and review-only", () => {
  assert.match(page, /Structured page details/);
  assert.match(page, /Checks saved behind-the-scenes page details against the accepted service brief/);
  assert.match(page, /Current page types/);
  assert.match(page, /Recommended detail type/);
  assert.match(page, /Owner confirmation needed/);
  assert.match(page, /This does not generate or publish website code/);
  assert.match(page, /do not guarantee a special search result/);
  assert.match(page, /draft\.structured_data_recommendation \?/);
  assert.doesNotMatch(page, /Apply schema/i);
  assert.doesNotMatch(page, /Generate JSON-LD/i);
  assert.doesNotMatch(page, /Publish structured data/i);
});

test("internal-link recommendations use exact saved pages and never insert links", () => {
  assert.match(page, /Helpful links between pages/);
  assert.match(page, /Uses exact saved page titles and accepted service wording/);
  assert.match(page, /Link from this saved page/);
  assert.match(page, /Link to this page/);
  assert.match(page, /Suggested link wording/);
  assert.match(page, /Link already found/);
  assert.match(page, /This does not insert links, create website code, or publish anything/);
  assert.match(page, /Internal links do not guarantee higher rankings or more traffic/);
  assert.match(page, /draft\.internal_link_recommendations \?/);
  assert.doesNotMatch(page, /Insert link now/i);
  assert.doesNotMatch(page, /Apply internal links/i);
  assert.doesNotMatch(page, /Publish links/i);
});

test("draft readiness validates saved owner copy without approving publication", () => {
  assert.match(page, /Draft readiness/);
  assert.match(page, /Ready for owner review/);
  assert.match(page, /Sections with wording/);
  assert.match(page, /Words saved/);
  assert.match(page, /A factual count, not a recommended target/);
  assert.match(page, /Confirm this claim/);
  assert.match(page, /Ready for owner review is not approval/);
  assert.match(page, /does not mean the page is ready to publish/);
  assert.match(page, /do not\s+grade writing quality or guarantee rankings/);
  assert.match(page, /draft\.content_readiness \?/);
  assert.doesNotMatch(page, /Approve for publication/i);
  assert.doesNotMatch(page, /Publish validated draft/i);
  assert.doesNotMatch(page, /Content score/i);
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
