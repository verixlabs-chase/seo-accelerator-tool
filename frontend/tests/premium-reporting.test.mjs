import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function read(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

const reportsPage = read("../app/(product)/reports/page.tsx");
const platformApi = read("../app/platform/api.js");

test("premium reports lead with a plain-language progress story and visual comparisons", () => {
  assert.match(reportsPage, /Your results at a glance/);
  assert.match(reportsPage, /What improved/);
  assert.match(reportsPage, /What needs attention/);
  assert.match(reportsPage, /What to do next/);
  assert.match(reportsPage, /from the earlier period/);
  assert.match(reportsPage, /text-emerald-400/);
  assert.match(reportsPage, /text-rose-400/);
  assert.match(reportsPage, /Performance over time/);
  assert.match(reportsPage, /reportTrendChart/);
  assert.match(reportsPage, /Orange: current/);
});

test("premium reports expose metric provenance and do not hide missing coverage", () => {
  assert.match(reportsPage, /Where the numbers came from/);
  assert.match(reportsPage, /Missing or partial data is shown plainly instead of being treated as zero/);
  assert.match(reportsPage, /metric\.source\?\.label/);
  assert.match(reportsPage, /coverage\?\.observed/);
});

test("multi-location reports compare frozen location facts without blending totals", () => {
  assert.match(reportsPage, /\/reports\/portfolio-comparison/);
  assert.match(reportsPage, /Compare location reports/);
  assert.match(reportsPage, /Numbers are never blended across locations/);
  assert.match(reportsPage, /only made when at least two locations use the same report dates/);
  assert.match(reportsPage, /portfolioComparison\.locations\.map/);
});

test("premium reports deduplicate and fully explain next actions", () => {
  assert.match(reportsPage, /uniqueStories/);
  assert.match(reportsPage, /canonical_action_id/);
  assert.match(reportsPage, /How we will check it/);
  assert.match(reportsPage, /item\.steps/);
  assert.match(reportsPage, /measurement\?\.check_after_days/);
});

test("premium reports keep completed work separate from measured results", () => {
  assert.match(reportsPage, /Work completed and results/);
  assert.match(reportsPage, /never claims? that an action helped before the follow-up data exists/);
  assert.match(reportsPage, /measured_outcomes/);
  assert.match(reportsPage, /completed_actions/);
});

test("saved report facts can rebuild files without silently changing the report", () => {
  assert.match(reportsPage, /\/reports\/\$\{reportId\}\/regenerate/);
  assert.match(reportsPage, /Rebuild selected report files/);
  assert.match(reportsPage, /same saved facts without changing the report numbers/);
});

test("reports expose durable files, saved recipients, and expiring private links", () => {
  assert.match(reportsPage, /Save recipient/);
  assert.match(reportsPage, /Each business keeps its own list/);
  assert.match(reportsPage, /Private sharing/);
  assert.match(reportsPage, /Create 7-day link/);
  assert.match(reportsPage, /Turn off link/);
  assert.match(reportsPage, /\/artifacts\/\$\{artifact\.id\}/);
});

test("report files use the authenticated request flow instead of raw links", () => {
  assert.match(reportsPage, /platformApiFile/);
  assert.match(reportsPage, /openReportArtifact\(artifact\)/);
  assert.match(reportsPage, /URL\.createObjectURL/);
  assert.match(reportsPage, /The report opened in a new tab/);
  assert.doesNotMatch(reportsPage, /href=\{`\/api\/v1\/reports/);
  assert.match(platformApi, /export async function platformApiFile/);
  assert.match(platformApi, /authenticatedRequest\(path, options\)/);
  assert.match(platformApi, /credentials: "include"/);
  assert.match(platformApi, /response\.blob\(\)/);
});

test("reports replace raw network failures and keep optional tools from blocking the page", () => {
  assert.match(reportsPage, /We could not create the report right now/);
  assert.match(reportsPage, /Reports could not be loaded right now/);
  assert.match(reportsPage, /Promise\.allSettled/);
  assert.match(reportsPage, /Try again/);
  assert.doesNotMatch(reportsPage, /setError\(err instanceof Error \? err\.message/);
});
