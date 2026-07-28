import test from "node:test";
import assert from "node:assert/strict";

import {
  flattenBusinessLocations,
  getHierarchyTruth,
} from "../app/(product)/truth/hierarchyTruth.mjs";

test("hierarchy truth marks unassigned locations as incomplete", () => {
  const truth = getHierarchyTruth({
    totals: {
      subaccounts: 1,
      business_locations: 2,
      unassigned_business_locations: 1,
      integrity_issues: 0,
    },
  });

  assert.equal(truth.label, "Setup incomplete");
  assert.equal(truth.tone, "warning");
  assert.match(truth.summary, /account group/i);
});

test("hierarchy truth reports a fully structured portfolio", () => {
  const truth = getHierarchyTruth({
    totals: {
      subaccounts: 2,
      business_locations: 5,
      unassigned_business_locations: 0,
      integrity_issues: 0,
    },
  });

  assert.equal(truth.label, "Structured");
  assert.equal(truth.tone, "success");
  assert.match(truth.summary, /5 locations/i);
});

test("business location flattening preserves its account group label", () => {
  const rows = flattenBusinessLocations({
    subaccounts: [
      {
        id: "sub-1",
        name: "North Region",
        business_locations: [{ id: "loc-1", name: "Dallas" }],
      },
    ],
    unassigned: {
      business_locations: [{ id: "loc-2", name: "Legacy" }],
    },
  });

  assert.deepEqual(
    rows.map((row) => [row.id, row.subaccount_name]),
    [
      ["loc-1", "North Region"],
      ["loc-2", "Unassigned"],
    ],
  );
});
