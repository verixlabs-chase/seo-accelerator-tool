import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reportsPage = readFileSync(
  new URL("../app/(product)/reports/page.tsx", import.meta.url),
  "utf8",
);

test("reports exposes a plain Enterprise identity workflow", () => {
  assert.match(reportsPage, /Enterprise report identity/);
  assert.match(reportsPage, /Put your organization&apos;s name on client reports/);
  assert.match(reportsPage, /\/reports\/branding/);
  assert.match(reportsPage, /existing reports were not changed/i);
  assert.match(reportsPage, /Logo uploads and custom chart colors are not available yet/);
});

test("report identity is future-only and plan truthful", () => {
  assert.match(reportsPage, /Applied to new reports/);
  assert.match(reportsPage, /saved_for_recovery/);
  assert.match(reportsPage, /Review Enterprise options/);
  assert.match(reportsPage, /Remove the InsightOS attribution from new client reports/);
  assert.doesNotMatch(reportsPage, /upload.*logo/i);
});
