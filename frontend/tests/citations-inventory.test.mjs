import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../app/(product)/citations/page.tsx", import.meta.url),
  "utf8",
);

test("directory listings lead with a governed public inventory check", () => {
  assert.match(source, /Check listings online/);
  assert.match(source, /citations\/discovery\/preview/);
  assert.match(source, /citations\/discovery\/runs/);
  assert.match(source, /citations\/inventory/);
  assert.match(source, /Saved:/);
  assert.match(source, /Found online:/);
  assert.match(source, /corrections are not available/i);
});

test("directory listing customers do not see the internal data supplier", () => {
  assert.doesNotMatch(source, /dataforseo/i);
});
