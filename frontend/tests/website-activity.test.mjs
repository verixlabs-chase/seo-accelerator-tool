import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const dashboard = readFileSync(
  new URL("../app/(product)/dashboard/page.tsx", import.meta.url),
  "utf8",
);
const settings = readFileSync(
  new URL("../app/(product)/settings/page.tsx", import.meta.url),
  "utf8",
);

test("dashboard presents location website activity and verified inquiries", () => {
  assert.match(dashboard, /What visitors did after reaching your website/);
  assert.match(dashboard, /Verified inquiries/);
  assert.match(dashboard, /Pages people entered on/);
  assert.match(dashboard, /Where visits came from/);
  assert.match(dashboard, /google-analytics\/metrics/);
});

test("settings exposes a one-time private form connection without customer lead fields", () => {
  assert.match(settings, /Create form connection/);
  assert.match(settings, /private key will not be shown again/);
  assert.match(settings, /website-events\/key/);
  assert.doesNotMatch(settings, /Collect form contents/);
});
