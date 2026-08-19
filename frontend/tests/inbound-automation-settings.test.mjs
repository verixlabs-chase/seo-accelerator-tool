import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);
const opportunities = readFileSync(
  fileURLToPath(new URL("../app/(product)/opportunities/page.tsx", import.meta.url)),
  "utf8",
);
const content = readFileSync(
  fileURLToPath(new URL("../app/(product)/content/page.tsx", import.meta.url)),
  "utf8",
);

test("Settings offers one-location read-only n8n report access", () => {
  assert.match(settings, /Give n8n read-only access to saved reports/);
  assert.match(settings, /Create one short-lived workflow key for one location/);
  assert.match(settings, /cannot start paid checks, approve work, publish content/);
  assert.match(settings, /location_id: automationCommandLocationId/);
  assert.match(settings, /expires_in_days: 30/);
  assert.match(settings, /Create report access/);
});

test("owners explicitly scope multi-location report access without broad workflow authority", () => {
  assert.match(settings, /Add report access for other locations/);
  assert.match(settings, /additional_location_ids: automationCommandAdditionalLocationIds/);
  assert.match(settings, /Additional locations allow saved-report retrieval only/);
  assert.match(settings, /Paid checks, refreshes, recommendations, drafts, review requests, approvals, and publishing remain limited to the primary location/);
  assert.match(settings, /Saved-report locations/);
  assert.match(settings, /additional_location_ids: additionalLocationIds/);
  assert.match(settings, /Every change replaces the workflow key/);
  assert.match(settings, /Removing a location blocks future reads immediately but preserves its reports and prior request history/);
});

test("workflow key lifecycle is owner-controlled and shown only from create or rotate", () => {
  assert.match(settings, /platformApi\("\/automation\/service-accounts"/);
  assert.match(settings, /\/automation\/service-accounts\/\$\{serviceAccountId\}\/rotate/);
  assert.match(settings, /method: "DELETE"/);
  assert.match(settings, /Copy this workflow key now/);
  assert.match(settings, /will not show the key again/);
  assert.match(settings, /Ask the workspace owner to create or replace the n8n report key/);
  assert.doesNotMatch(settings, /setAutomationCommandToken\(activeAutomationServiceAccount/);
});

test("advanced n8n instructions use the fixed command contract", () => {
  const start = settings.indexOf("n8n setup details (advanced)");
  const contract = settings.slice(start, start + 5000);
  assert.ok(start >= 0);
  assert.match(contract, /\/api\/v1\/automation\/commands/);
  assert.match(contract, /Bearer YOUR_WORKFLOW_KEY/);
  assert.match(contract, /insightos\.automation\.command\.v1/);
  assert.match(contract, /command_type: "report\.retrieve"/);
  assert.match(contract, /target: \{ report_id: "REPLACE-WITH-REPORT-ID" \}/);
  assert.match(contract, /Reusing the same idempotency key safely returns the first result/);
  assert.doesNotMatch(contract, /arbitrary_prompt|database\.query|wordpress\.publish|business_profile\.update/);
});

test("owners can download a safe inactive n8n starter instead of hand-building it", () => {
  assert.match(settings, /Download n8n starter/);
  assert.match(
    settings,
    /\/automation\/starter-workflows\/n8n\/report-ready\?service_account_id=/,
  );
  assert.match(settings, /choose Import from File in n8n/);
  assert.match(settings, /select a Bearer Auth credential containing the one-time workflow key/);
  assert.match(settings, /copy its Production URL/);
  assert.match(settings, /select only “Report ready”/);
  assert.match(settings, /The download is inactive and never contains your workflow key/);
  assert.match(settings, /It ignores updates for other locations and creates no paid work/);
});

test("command history uses plain results instead of internal request details", () => {
  assert.match(settings, /Recent report requests/);
  assert.match(settings, /Saved report returned/);
  assert.match(settings, /Request safely declined/);
  assert.doesNotMatch(settings, /receipt\.request_hash|receipt\.artifact_hash|receipt\.reason/);
});

test("owners explicitly opt into saved-data report creation with a replacement key", () => {
  assert.match(settings, /Let n8n create private reports from saved results/);
  assert.match(settings, /report\.generate_saved/);
  assert.match(settings, /cannot start a crawl or paid check, send the report, publish content/);
  assert.match(settings, /\.\.\.\(enabled \? \["report\.generate_saved"\] : \[\]\)/);
  assert.match(settings, /"report\.retrieve"/);
  assert.match(settings, /old key stops working immediately/);
  assert.match(settings, /Private report created/);
});

test("owners can download an inactive monthly private-report workflow", () => {
  assert.match(settings, /Download monthly report workflow/);
  assert.match(settings, /first day of each month/);
  assert.match(settings, /review its day, time, and timezone before publishing/);
  assert.match(
    settings,
    /\/automation\/starter-workflows\/n8n\/saved-report-schedule\?service_account_id=/,
  );
  assert.match(settings, /activeAutomationCampaign\.id/);
  assert.match(settings, /inactive monthly-report workflow was downloaded/);
});

test("owners explicitly enable saved recommendation review routing", () => {
  assert.match(settings, /Let n8n route saved recommendations for owner review/);
  assert.match(settings, /recommendation\.retrieve/);
  assert.match(settings, /recommendation\.request_review/);
  assert.match(settings, /cannot approve, schedule, execute, or publish anything/);
  assert.match(settings, /Allow owner-review routing/);
  assert.match(settings, /Download recommendation workflow/);
  assert.match(
    settings,
    /\/automation\/starter-workflows\/n8n\/recommendation-ready\?service_account_id=/,
  );
  assert.match(settings, /Recommendation ready updates/);
  assert.match(settings, /Saved recommendation returned/);
  assert.match(settings, /Owner review requested/);
  assert.match(settings, /target: \{ recommendation_id: "REPLACE-WITH-RECOMMENDATION-ID" \}/);
  assert.match(opportunities, /A connected workflow asked you to review this/);
  assert.match(opportunities, /did not approve, schedule, or run this recommendation/);
});

test("owners explicitly enable bounded connected-data refresh", () => {
  assert.match(settings, /Let n8n refresh connected data/);
  assert.match(settings, /connection\.refresh_saved/);
  assert.match(settings, /Allow connected-data refresh/);
  assert.match(settings, /REPLACE-WITH-CONNECTION-ID/);
  assert.match(settings, /returns a safe job ID and current queued, running, completed, or failed status/);
  assert.match(settings, /cannot connect a new account, change settings, publish, or run an unrelated action/i);
  assert.match(settings, /Connected data refresh accepted/);
});

test("owners explicitly enable the first allowance-priced workflow check", () => {
  assert.match(settings, /Let n8n check public business listings/);
  assert.match(settings, /listing\.check_public/);
  assert.match(settings, /Allow public listing checks/);
  assert.match(settings, /uses the same Insight Credit balance, daily plan limit, price setup/);
  assert.match(settings, /first workflow action that can consume Insight Credits/);
  assert.match(settings, /REPLACE-WITH-CAMPAIGN-ID/);
  assert.match(settings, /cannot reserve credits twice/);
  assert.match(settings, /Public listing check accepted/);
});

test("owners explicitly enable private drafts from accepted briefs", () => {
  assert.match(settings, /Let n8n start accepted working drafts/);
  assert.match(settings, /content\.create_working_draft/);
  assert.match(settings, /Allow accepted draft creation/);
  assert.match(settings, /REPLACE-WITH-ACCEPTED-BRIEF-ID/);
  assert.match(settings, /private editable outline and place an exact draft beside the owner for review/i);
  assert.match(settings, /cannot generate AI copy, approve, schedule, publish, or change your website/i);
  assert.match(settings, /Private working draft created/);
  assert.match(settings, /content\.request_draft_review/);
  assert.match(settings, /REPLACE-WITH-WORKING-DRAFT-ID/);
  assert.match(settings, /Private draft review requested/);
  assert.match(content, /Review requested by a connected workflow/);
  assert.match(content, /did not approve, schedule, publish, or change your website/);
  assert.match(settings, /Download private-draft workflow/);
  assert.match(settings, /\/automation\/starter-workflows\/n8n\/content-draft-review\?service_account_id=/);
  assert.match(settings, /download starts inactive, contains no workflow key/i);
});

test("owners can route minimized saved review facts without outside reply authority", () => {
  assert.match(settings, /Let n8n route saved review facts/);
  assert.match(settings, /review\.retrieve/);
  assert.match(settings, /review\.create_response_draft/);
  assert.match(settings, /Allow private reply drafts/);
  assert.match(settings, /A person must still review and approve it/);
  assert.match(settings, /review-response-draft/);
  assert.match(settings, /Download private reply-draft workflow/);
  assert.match(settings, /inactive private reply-draft workflow/);
  assert.match(settings, /Allow saved-review routing/);
  assert.match(settings, /Reviewer names and comment text stay in InsightOS/);
  assert.match(settings, /cannot create, approve, or post a reply or change your Business Profile/i);
  assert.match(settings, /Saved review facts returned/);
  assert.match(settings, /Download saved-review workflow/);
  assert.match(settings, /\/automation\/starter-workflows\/n8n\/saved-review-routing\?service_account_id=/);
  assert.match(settings, /inactive saved-review workflow was downloaded/i);
  assert.match(settings, /Production URL to Review saved updates/);
  assert.match(settings, /Every change replaces the workflow key|This replaces the workflow key/);
});
