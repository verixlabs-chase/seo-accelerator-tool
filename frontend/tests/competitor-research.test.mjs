import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/competitors/page.tsx", import.meta.url)),
  "utf8",
);

test("competitor research requires an owner decision before comparison", () => {
  assert.match(page, /\/competitors\/discover/);
  assert.match(page, /Yes, this is a competitor/);
  assert.match(page, /Not a competitor/);
  assert.match(page, /decision: "dismissed"/);
});

test("competitor gaps show exact evidence instead of an invented score", () => {
  assert.match(page, /\/competitors\/research/);
  assert.match(page, /competitor_position/);
  assert.match(page, /owner_position/);
  assert.match(page, /competitor_url/);
  assert.match(page, /source_updated_at/);
  assert.match(page, /No made-up gap score is used/);
  assert.doesNotMatch(page, /gap_score/);
});

test("a reviewed gap can move into rankings or governed next steps", () => {
  assert.match(page, /\/keyword-research\/track/);
  assert.match(page, /Track this search/);
  assert.match(page, /\/keyword-research\/create-action/);
  assert.match(page, /Add to Next Steps/);
});

test("competitor movement uses comparable saved positions", () => {
  assert.match(page, /previous_competitor_position/);
  assert.match(page, /movement_direction/);
  assert.match(page, /Competitor movement alerts/);
  assert.match(page, /Earlier check/);
  assert.match(page, /at least three places/);
});

test("competitor customer copy does not expose the internal market supplier", () => {
  assert.doesNotMatch(page, /dataforseo/i);
});
