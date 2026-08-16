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
  assert.match(settings, /External automation requires/);
  assert.match(settings, /Send report and action updates to your workflow tool/);
  assert.match(settings, /\/automation\/connections/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/retry/);
  assert.match(settings, /\/automation\/deliveries\/\$\{deliveryId\}\/recover/);
  assert.match(settings, /\/automation\/connections\/\$\{connectionId\}\/\$\{action\}/);
  assert.match(settings, /Copy this signing secret now/);
  assert.match(settings, /Webhook URL — kept private/);
  assert.match(settings, /The saved webhook URL and signing secret are encrypted/);
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
