import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const panel = readFileSync(
  fileURLToPath(
    new URL("../app/(product)/local-visibility/LocalRankGridPanel.tsx", import.meta.url),
  ),
  "utf8",
);

test("local grid can switch between the owner and confirmed competitors", () => {
  assert.match(panel, /Show on the map/);
  assert.match(panel, /Your business/);
  assert.match(panel, /activeBusinessId/);
  assert.match(panel, /competitor_points/);
});

test("local grid explains exact overlap without a made-up score", () => {
  assert.match(panel, /Spots where you lead/);
  assert.match(panel, /Spots where they lead/);
  assert.match(panel, /Tied spots/);
  assert.match(panel, /competitor_overlap_summary/);
  assert.doesNotMatch(panel, /overlap_score/);
});

test("confirmed competitor capture reuses the approved map checks", () => {
  assert.match(panel, /It does not add more map checks/);
  assert.match(panel, /Confirm competitors on the Competitors page/);
  assert.doesNotMatch(panel, /dataforseo/i);
});
