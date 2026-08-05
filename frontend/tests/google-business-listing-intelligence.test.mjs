import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("business listings are connected separately and stay location scoped", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /scope_target=\$\{scopeTarget\}/);
  assert.match(settings, /google-business-profile\/mappings/);
  assert.match(settings, /One listing can belong to only one location/);
  assert.match(settings, /will not edit the listing automatically/);
  assert.match(settings, /Match and run first check/);
});

test("local search visualizes real listing results in owner language", () => {
  const page = source("../app/(product)/local-visibility/page.tsx");
  const panel = source(
    "../app/(product)/local-visibility/GoogleBusinessListingPanel.tsx",
  );

  assert.match(page, /google-business-profile\/intelligence/);
  assert.match(page, /<GoogleBusinessListingPanel/);
  for (const label of [
    "Google appearances",
    "Website visits",
    "Call clicks",
    "Direction requests",
    "Searches that led to this listing",
    "What changed on the listing",
  ]) {
    assert.match(panel, new RegExp(label));
  }
  assert.match(panel, /Daily appearances/);
  assert.match(panel, /Fix these listing details first/);
  assert.doesNotMatch(panel, /\bGBP\b/);
  assert.doesNotMatch(panel, /deterministic|provider metric|API response/i);
});
