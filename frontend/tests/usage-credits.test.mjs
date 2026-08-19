import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8");

test("settings presents Insight Credits without exposing the internal dollar budget", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /Insight Credits available this month/);
  assert.match(settings, /credits left this month/);
  assert.match(settings, /Failed work returns unused credits automatically/);
  assert.doesNotMatch(settings, /Monthly data budget/);
  assert.doesNotMatch(settings, /usageAllowance\.allowance/);
  assert.doesNotMatch(
    settings,
    /\$\{usageAllowance\.credits\.(?:monthly|used|reserved|remaining)\.toFixed/,
  );
});

test("settings explains the current plan and the practical reason to upgrade", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /Your plan/);
  assert.match(settings, /included \{usageAllowance\.plan\.included_locations === 1/);
  assert.match(settings, /Upgrade securely/);
  assert.match(settings, /Manage billing/);
  assert.match(settings, /Payment needs attention/);
  assert.match(settings, /usageAllowance\.upgrade\.reasons/);
});

test("settings provides outbound-only signed workflow connections", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /usageAllowance\.external_automation \? \(/);
  assert.match(settings, /usageAllowance\.external_automation\.gateway_enabled/);
  assert.match(settings, /Workflow connections require/);
  assert.match(settings, /Send useful updates to Zapier, Make, Pipedream, or n8n/);
  assert.match(settings, /\/automation\/connections/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/retry/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/recover/);
  assert.match(settings, /\/automation\/connections\/\$\{connectionId\}\/\$\{action\}/);
  assert.match(settings, /Copy this signing secret now/);
  assert.match(settings, /Paste the webhook URL from your tool/);
  assert.match(settings, /n8n Cloud/);
  assert.match(settings, /copy the Webhook node&apos;s Production URL/);
  assert.match(settings, /temporary Test URL will not work here/);
  assert.match(settings, /Start with a safe event recipe/);
  assert.match(settings, /recipe_catalog_version/);
  assert.match(settings, /starter_recipes/);
  assert.match(settings, /Share new reports|recipe\.label/);
  assert.match(settings, /A recipe only chooses signed outbound notifications/);
  assert.match(settings, /it cannot approve or run InsightOS work/);
  assert.match(settings, /Use this recipe/);
  assert.match(settings, /Recipe selected/);
  assert.match(settings, /setAutomationSelectedRecipe\(""\)/);
  assert.match(settings, /provider_setup_version/);
  assert.match(settings, /provider_setup/);
  assert.match(settings, /Set up \{selectedAutomationProviderSetup\.webhook_source\}/);
  assert.match(settings, /Setup guide ready/);
  assert.match(settings, /Open the official \{selectedAutomationProviderSetup\.label\} setup guide/);
  assert.match(settings, /Technical verification details \(advanced\)/);
  assert.match(settings, /selectedAutomationProviderSetup\.payload_path/);
  assert.match(settings, /selectedAutomationProviderSetup\.headers_path/);
  assert.match(settings, /selectedAutomationProviderSetup\.route_field/);
  assert.match(settings, /selectedAutomationProviderSetup\.field_map/);
  assert.match(settings, /Verification contract:/);
  assert.match(settings, /\/automation\/conformance\/\$\{automationProvider\}/);
  assert.match(settings, /Download developer test file/);
  assert.match(settings, /Uses sample data only/);
  assert.match(settings, /receiver-conformance-v1\.json/);
  assert.match(settings, /URL\.revokeObjectURL/);
  assert.match(settings, /When your tool accepts it, the connection is ready/);
  assert.match(settings, /Connection check:/);
  assert.match(settings, /product_event_accepted/);
  assert.match(settings, /monthly_delivery_usage/);
  assert.match(settings, /Workflow activity this month/);
  assert.match(settings, /Each update is counted once; retries are shown separately/);
  assert.match(settings, /This is activity history, not an extra charge/);
  assert.match(settings, /connection\.monthly_delivery_usage\.product_events/);
  assert.match(settings, /Send test/);
  assert.match(settings, /Retry last test/);
  assert.match(settings, /Sending updates/);
  assert.match(settings, /Updates paused/);
  assert.match(settings, /Attempts exhausted/);
  assert.match(settings, /Recover event/);
  assert.match(settings, /Pause updates/);
  assert.match(settings, /Resume updates/);
  assert.match(settings, /Replace signing secret/);
  assert.match(settings, /Disconnect/);
  assert.match(settings, /me\?\.org_role === "org_owner"/);
  assert.match(settings, /See every update InsightOS can send/);
  assert.match(settings, /Reports, recommendations, and completed approved actions can be sent/);
  assert.match(settings, /outbound_contract\?\.supported_events\.length/);
  assert.match(settings, /event\.label/);
  assert.match(settings, /event\.summary/);
  assert.match(settings, /cannot approve recommendations, publish content, edit WordPress, or change a Google Business Profile/);
  assert.doesNotMatch(settings, /\/automation\/(?:approve|publish|execute|actions)/);
});

test("platform plan controls use the current 399 Solo packaging", () => {
  const organization = source("../app/platform/orgs/[id]/page.jsx");

  assert.match(organization, /Solo · \$399\/month/);
  assert.match(organization, /Growth · \$699\/month/);
  assert.doesNotMatch(organization, /Solo · \$299\/month/);
});

test("keyword research shows the paid refresh price before it runs", () => {
  const research = source("../app/(product)/keyword-research/page.tsx");

  assert.match(research, /Refreshing this location uses up to/);
  assert.match(research, /Unused credits are returned automatically/);
  assert.match(research, /item\.code === "keyword_relevance_review"/);
  assert.match(research, /Uses \{reviewCreditPrice\.credits\} Insight/);
});
