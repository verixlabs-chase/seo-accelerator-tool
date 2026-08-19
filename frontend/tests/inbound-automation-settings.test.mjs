import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
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

test("command history uses plain results instead of internal request details", () => {
  assert.match(settings, /Recent report requests/);
  assert.match(settings, /Saved report returned/);
  assert.match(settings, /Request safely declined/);
  assert.doesNotMatch(settings, /receipt\.request_hash|receipt\.artifact_hash|receipt\.reason/);
});

