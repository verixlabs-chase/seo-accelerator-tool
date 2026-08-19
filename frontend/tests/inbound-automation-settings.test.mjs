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

test("Settings offers one-location read-only n8n report access", () => {
  assert.match(settings, /Give n8n read-only access to saved reports/);
  assert.match(settings, /Create one short-lived workflow key for one location/);
  assert.match(settings, /cannot start paid checks, approve work, publish content/);
  assert.match(settings, /location_id: automationCommandLocationId/);
  assert.match(settings, /expires_in_days: 30/);
  assert.match(settings, /Create report access/);
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
