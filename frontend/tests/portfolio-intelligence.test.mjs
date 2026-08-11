import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  fileURLToPath(new URL("../app/(product)/locations/page.tsx", import.meta.url)),
  "utf8",
);

test("multi-location portfolio puts the three locations needing help first", () => {
  assert.match(source, /\/portfolio-overview/);
  assert.match(source, /Start with these locations/);
  assert.match(source, /Showing up to 3 locations needing attention/);
  assert.match(source, /Priority \{index \+ 1\}/);
  assert.match(source, /There is no hidden portfolio score/);
});

test("portfolio comparison is sortable and opens the chosen location", () => {
  assert.match(source, /Compare all \{portfolio\.summary\.active_locations\} active locations/);
  assert.match(source, /Needs attention first/);
  assert.match(source, /Best Google position/);
  assert.match(source, /Best recent rating/);
  assert.match(source, /Most website problems/);
  assert.match(source, /setSelectedCampaignId\(campaignId\)/);
});

test("portfolio groups shared problems without hiding location evidence", () => {
  assert.match(source, /Problems affecting more than one location/);
  assert.match(source, /portfolio\.shared_issues/);
  assert.match(source, /issue\.locations\.map/);
  assert.match(source, /location\.evidence\.label/);
  assert.match(source, /location\.action_label/);
});

test("portfolio suggests measured examples without claiming causation", () => {
  assert.match(source, /Locations worth learning from/);
  assert.match(source, /portfolio\.repeatable_wins/);
  assert.match(source, /Example to inspect/);
  assert.match(source, /does not claim that one tactic caused the result/);
  assert.match(source, /win\.guardrail/);
});
