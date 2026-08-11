import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/profile-campaigns/page.tsx", import.meta.url)),
  "utf8",
);
const nav = readFileSync(
  fileURLToPath(new URL("../app/(product)/nav.config.ts", import.meta.url)),
  "utf8",
);

test("profile campaigns freeze targets before building per-location previews", () => {
  assert.match(page, /\/target-snapshots/);
  assert.match(page, /\/profile-campaigns/);
  assert.match(page, /Build location previews/);
  assert.match(page, /Review every location/);
  assert.match(page, /A campaign cannot silently grow or change after approval/);
});

test("profile campaign approval is visibly non-publishing until validation", () => {
  assert.match(page, /Publishing is still locked/);
  assert.match(page, /Approve exact previews/);
  assert.match(page, /No Google listing changes are sent/);
  assert.doesNotMatch(page, /Publish now/);
});

test("profile campaigns have a dedicated icon and navigation destination", () => {
  assert.match(nav, /href: "\/profile-campaigns"/);
  assert.match(nav, /icon: "profile-campaigns"/);
});
