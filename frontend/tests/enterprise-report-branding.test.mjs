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
  assert.match(reportsPage, /Client report logo/);
  assert.match(reportsPage, /one still PNG up to 64 KB/);
  assert.match(reportsPage, /removes embedded metadata/);
  assert.match(reportsPage, /\/reports\/branding\/logo/);
  assert.match(reportsPage, /Report accent/);
  assert.match(reportsPage, /Used only on the top edge of new reports/);
  assert.match(reportsPage, /accent_color: brandAccent/);
});

test("report identity is future-only and plan truthful", () => {
  assert.match(reportsPage, /Applied to new reports/);
  assert.match(reportsPage, /saved_for_recovery/);
  assert.match(reportsPage, /Review Enterprise options/);
  assert.match(reportsPage, /Remove the InsightOS attribution from new client reports/);
  assert.match(reportsPage, /Remove saved logo/);
  assert.match(reportsPage, /Result and warning colors stay fixed/);
});
