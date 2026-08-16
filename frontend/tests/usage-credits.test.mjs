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

test("settings separates automation plan eligibility from a live gateway", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /usageAllowance\.external_automation\.plan_eligible/);
  assert.match(settings, /usageAllowance\.external_automation \? \(/);
  assert.match(settings, /External automation requires/);
  assert.match(settings, /Your plan is eligible, but external automation is not available yet/);
  assert.match(settings, /Planned as a vendor-neutral connection/);
  assert.match(settings, /No tool can connect, receive events, or run actions yet/);
  assert.doesNotMatch(settings, />Connect n8n</);
  assert.doesNotMatch(settings, /\/automation\/connections/);
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
