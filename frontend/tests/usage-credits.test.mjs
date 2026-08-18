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

  assert.match(settings, /loadConnections\(currentUser\.organization_id\)\.catch/);
  assert.match(settings, /Billing and automation settings are still available/);
  assert.match(settings, /err\.message !== "Failed to fetch"/);
  assert.match(settings, /usageAllowance\.external_automation \? \(/);
  assert.match(settings, /usageAllowance\.external_automation\.gateway_enabled/);
  assert.match(settings, /External automation requires/);
  assert.match(settings, /Send report and action updates to your workflow tool/);
  assert.match(settings, /\/automation\/connections/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/retry/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/recover/);
  assert.match(settings, /\/automation\/connections\/\$\{connectionId\}\/\$\{action\}/);
  assert.match(settings, /Copy this signing secret now/);
  assert.match(settings, /Webhook URL — kept private/);
  assert.match(settings, /n8n Cloud/);
  assert.match(settings, /Production URL from a published n8n Cloud Webhook node/);
  assert.match(settings, /Temporary test URLs and self-hosted domains are not accepted/);
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
  assert.match(settings, /Connection kit ready/);
  assert.match(settings, /Open official \{selectedAutomationProviderSetup\.label\} webhook documentation/);
  assert.match(settings, /Wire the received event/);
  assert.match(settings, /selectedAutomationProviderSetup\.payload_path/);
  assert.match(settings, /selectedAutomationProviderSetup\.headers_path/);
  assert.match(settings, /selectedAutomationProviderSetup\.route_field/);
  assert.match(settings, /selectedAutomationProviderSetup\.field_map/);
  assert.match(settings, /Verification contract:/);
  assert.match(settings, /\/automation\/conformance\/\$\{automationProvider\}/);
  assert.match(settings, /Download receiver test contract/);
  assert.match(settings, /Synthetic only—contains no customer data or live credential/);
  assert.match(settings, /receiver-conformance-v1\.json/);
  assert.match(settings, /URL\.revokeObjectURL/);
  assert.match(settings, /The InsightOS side is wired/);
  assert.match(settings, /customer supplies the private webhook URL/);
  assert.match(settings, /Connection proof:/);
  assert.match(settings, /Real product event accepted|product_event_accepted/);
  assert.match(settings, /InsightOS proves delivery only after the signed test/);
  assert.match(settings, /The saved webhook URL and signing secret are encrypted/);
  assert.match(settings, /monthly_delivery_usage/);
  assert.match(settings, /Workflow delivery this month/);
  assert.match(settings, /Distinct events are counted once/);
  assert.match(settings, /Delivery attempts include bounded retries/);
  assert.match(settings, /This is observed activity, not a plan allowance or billable-usage counter/);
  assert.match(settings, /connection\.monthly_delivery_usage\.product_events/);
  assert.match(settings, /Send test/);
  assert.match(settings, /Retry last test/);
  assert.match(settings, /Automatic delivery on/);
  assert.match(settings, /Automatic delivery paused/);
  assert.match(settings, /Attempts exhausted/);
  assert.match(settings, /Recover event/);
  assert.match(settings, /Pause events/);
  assert.match(settings, /Resume events/);
  assert.match(settings, /Replace secret/);
  assert.match(settings, /Disconnect/);
  assert.match(settings, /me\?\.org_role === "org_owner"/);
  assert.match(settings, /Approved outbound event contract/);
  assert.match(settings, /Approval-requested remains reserved/);
  assert.match(settings, /Report, recommendation, and approved-action results deliver automatically/);
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
