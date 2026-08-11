import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  fileURLToPath(new URL("../app/(product)/locations/page.tsx", import.meta.url)),
  "utf8",
);

test("location groups are reusable and editable without exposing internal execution terms", () => {
  assert.match(source, /\/location-groups/);
  assert.match(source, /Save a location group/);
  assert.match(source, /Plan with saved group/);
  assert.match(source, /Edit which locations are permanently in this group/);
  assert.match(source, /expected_version: selectedTargetGroup\.version/);
  assert.doesNotMatch(source, /fleet job/i);
});

test("target previews show the exact ready and blocked locations before work can run", () => {
  assert.match(source, /\/target-snapshots/);
  assert.match(source, /Save exact target list/);
  assert.match(source, /Nothing runs from this screen/);
  assert.match(source, /Most recent frozen target list/);
  assert.match(source, /Left out or needs setup/);
  assert.match(source, /visibleTargetSnapshot\.targets\.map/);
  assert.match(source, /visibleTargetSnapshot\.exceptions\.map/);
  assert.match(source, /Locked record/);
});

test("one-time target changes stay separate from permanent group membership", () => {
  assert.match(source, /targetLocationIds/);
  assert.match(source, /groupMemberDraftIds/);
  assert.match(source, /included_location_ids/);
  assert.match(source, /excluded_location_ids/);
  assert.match(source, /Any older target previews remain unchanged/);
});

test("bulk location work requires readiness review and explicit approval", () => {
  assert.match(source, /\/portfolio-fleet-runs/);
  assert.match(source, /Check readiness and credits/);
  assert.match(source, /Approve and start/);
  assert.match(source, /Progress by location/);
  assert.match(source, /Retry failed locations/);
  assert.match(source, /No Google profile or website\s+changes are enabled in this run/);
  assert.match(source, /The frozen list cannot grow after approval/);
  assert.doesNotMatch(source, /provider mutation/i);
});

test("bulk location work can pause undispatched locations and safely resume", () => {
  assert.match(source, /portfolio-fleet-runs\/\$\{run\.id\}\/pause/);
  assert.match(source, /portfolio-fleet-runs\/\$\{run\.id\}\/resume/);
  assert.match(source, /Pause waiting locations/);
  assert.match(source, /Resume waiting locations/);
  assert.match(source, /Completed results were kept/);
});
