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
  assert.match(source, /correction_access/);
  assert.match(source, /Managed corrections require/);
  assert.match(source, /Your plan is eligible, but live corrections are not available yet/);
  assert.match(source, /make the correction directly with that directory/);
  assert.match(source, /No directory was contacted or changed/);
  assert.match(source, /plan_check_unavailable/);
  assert.match(source, /Managed correction access could not be confirmed/);
  assert.match(source, /This saved record says the listing was live/);
  assert.doesNotMatch(source, /\/citations\/submissions/);
  assert.doesNotMatch(source, /Start listing request/);
  assert.doesNotMatch(source, /pull the latest updates from each directory/);
});

test("directory listing customers do not see the internal data supplier", () => {
  assert.doesNotMatch(source, /dataforseo/i);
});
