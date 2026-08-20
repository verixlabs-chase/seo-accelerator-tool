import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const page = fs.readFileSync(path.join(root, "app/platform/readiness/page.jsx"), "utf8");
const home = fs.readFileSync(path.join(root, "app/platform/page.jsx"), "utf8");
const shell = fs.readFileSync(path.join(root, "app/(product)/components/AppShell.tsx"), "utf8");
const statusBanner = fs.readFileSync(
  path.join(root, "app/(product)/components/CustomerStatusBanner.tsx"),
  "utf8",
);
const capabilities = fs.readFileSync(
  path.join(root, "app/platform/capabilities/page.jsx"),
  "utf8",
);
const experience = fs.readFileSync(
  path.join(root, "app/platform/experience/page.jsx"),
  "utf8",
);

test("platform launch readiness keeps blocking and proof states distinct", () => {
  assert.match(page, /\/system\/launch-readiness/);
  assert.match(page, /needs_live_proof: "Needs live proof"/);
  assert.match(page, /blocker: "Blocking"/);
  assert.match(page, /Current decision:/);
  assert.match(page, /What this board does not prove/);
  assert.match(page, /\/system\/launch-readiness\/proofs/);
  assert.match(page, /Record current production proof/);
  assert.match(page, /never paste a URL, credential, webhook address, or provider response/);
  assert.match(page, /Latest operator proof/);
  assert.match(page, /\/system\/launch-readiness\/decisions/);
  assert.match(page, /Ready for owner decision/);
  assert.match(page, /A passing board is only ready for a decision/);
  assert.match(page, /Superseded by newer evidence/);
  assert.doesNotMatch(page, /readiness percentage/i);
});

test("platform control center links to the launch decision board", () => {
  assert.match(home, /href="\/platform\/readiness"/);
  assert.match(home, /Paid Launch Readiness/);
});

test("platform owners publish plain-language customer status updates from the readiness board", () => {
  assert.match(page, /\/system\/customer-status/);
  assert.match(page, /Customer service updates/);
  assert.match(page, /Do not include supplier\s+names, raw errors, customer identifiers, links, or credentials/);
  assert.match(page, /Platform administrators can review history/);
  assert.match(page, /Permanent update history/);
  assert.match(page, /visible_to_customers/);
});

test("the product shell shows only active saved customer incidents", () => {
  assert.match(shell, /<CustomerStatusBanner \/>/);
  assert.match(statusBanner, /\/status\/summary/);
  assert.match(statusBanner, /InsightOS service updates/);
  assert.match(statusBanner, /Affects/);
  assert.match(statusBanner, /Starts/);
  assert.match(statusBanner, /Updated/);
  assert.doesNotMatch(statusBanner, /provider_name|content_digest|created_by_user_id/);
});

test("production capability claims separate plan inclusion from current proof", () => {
  assert.match(capabilities, /\/system\/production-capabilities/);
  assert.match(capabilities, /Plan inclusion shows what a customer may buy/);
  assert.match(capabilities, /current production proof shows what sales, demos, Help, and support may describe as available/);
  assert.match(capabilities, /Production proven/);
  assert.match(capabilities, /Available with a customer limitation/);
  assert.match(capabilities, /Not currently available/);
  assert.match(capabilities, /Needs production proof/);
  assert.match(capabilities, /Do not describe this capability as live/);
  assert.doesNotMatch(capabilities, /readiness percentage/i);
});

test("the capability matrix is reachable from launch readiness and the platform home", () => {
  assert.match(home, /href="\/platform\/capabilities"/);
  assert.match(page, /href="\/platform\/capabilities"/);
});

test("whole-product experience proof requires every route, both viewports, and five participants", () => {
  assert.match(experience, /\/system\/launch-experience/);
  assert.match(experience, /Desktop and mobile route matrix/);
  assert.match(experience, /loading, empty, error, recovery/);
  assert.match(experience, /Non-technical participants/);
  assert.match(experience, /at least five non-technical people/);
  assert.match(experience, /connect a search account/);
  assert.match(experience, /optional analytics/);
  assert.match(experience, /opaque participant alias/i);
  assert.match(experience, /never names, emails, recordings/i);
  assert.match(experience, /Automated tests do not count/);
  assert.doesNotMatch(experience, /readiness percentage/i);
});

test("experience proof is reachable from platform home and launch readiness", () => {
  assert.match(home, /href="\/platform\/experience"/);
  assert.match(page, /href="\/platform\/experience"/);
});
