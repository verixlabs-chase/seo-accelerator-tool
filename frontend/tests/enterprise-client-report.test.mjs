import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("private report links open on a customer-readable no-login page", () => {
  const page = source("../app/shared-report/[token]/page.tsx");
  const layout = source("../app/shared-report/layout.tsx");

  assert.match(page, /reports\/shared\/\$\{encodeURIComponent\(token\)\}/);
  assert.match(page, /credentials: "omit"/);
  assert.match(page, /cache: "no-store"/);
  assert.match(page, /Private client report/);
  assert.match(layout, /index: false, follow: false, nocache: true/);
  assert.match(layout, /referrer: "no-referrer"/);
});

test("shared report HTML stays isolated from the application", () => {
  const page = source("../app/shared-report/[token]/page.tsx");

  assert.match(page, /srcDoc=\{reportHtml\}/);
  assert.match(page, /sandbox=""/);
  assert.match(page, /referrerPolicy="no-referrer"/);
  assert.doesNotMatch(page, /dangerouslySetInnerHTML/);
  assert.doesNotMatch(page, /allow-scripts|allow-same-origin/);
  assert.doesNotMatch(page, /localStorage|sessionStorage|Authorization/);
});

test("expired and invalid report links use plain recovery copy", () => {
  const page = source("../app/shared-report/[token]/page.tsx");
  const customerView = page.slice(page.indexOf("  return ("));

  assert.match(page, /This private report link is no longer active/);
  assert.match(page, /Ask the sender for a new private link/);
  assert.match(page, /This report is not available/);
  assert.match(page, /complete link was copied correctly/);
  assert.doesNotMatch(customerView, /token hash|artifact|HTTP|status code/i);
});
