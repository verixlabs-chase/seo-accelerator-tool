import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/reviews/page.tsx", import.meta.url)),
  "utf8",
);

test("customer review inbox is location scoped, filterable, and read only", () => {
  assert.match(page, /useLocationContext/);
  assert.match(page, /reviews\/inventory/);
  assert.match(page, /reviews\/sync/);
  assert.match(page, /Needs a reply/);
  assert.match(page, /3 stars or lower/);
  assert.match(page, /Answered/);
  assert.match(page, /Review replies are not turned on yet/);
  assert.doesNotMatch(page, /textarea/);
  assert.doesNotMatch(page, /Post reply/);
});
