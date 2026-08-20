import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("Enterprise activity is a dedicated owner-facing product page", () => {
  const page = source("../app/(product)/activity/page.tsx");
  const nav = source("../app/(product)/nav.config.ts");

  assert.match(nav, /href: "\/activity", label: "Team Activity", icon: "activity"/);
  assert.match(page, /\/enterprise\/activity/);
  assert.match(page, /See who changed what/);
  assert.match(page, /Only the workspace owner can view this history/);
  assert.match(page, /Organization activity is available with Enterprise/);
  assert.match(page, /settings#plan-and-billing/);
  assert.equal(page.match(/<TruthNotice\b/g)?.length, 1);
});

test("Enterprise activity supports safe categories and opaque pagination", () => {
  const page = source("../app/(product)/activity/page.tsx");

  assert.match(page, /All activity/);
  assert.match(page, /Load older activity/);
  assert.match(page, /next_cursor/);
  assert.match(page, /category_label/);
  assert.match(page, /item\.actor\.label/);
  assert.match(page, /item\.occurred_at/);
  assert.match(page, /No tracked activity in this view yet/);
  assert.doesNotMatch(page, /payload_json|event_type|provider_secret|organization_id|audit_log/i);
});

test("Enterprise activity explains its intentionally limited history", () => {
  const page = source("../app/(product)/activity/page.tsx");

  assert.match(page, /meaningful saved actions/i);
  assert.match(page, /Background checks and private provider details are not shown/);
  assert.match(page, /This does not mean nothing happened/);
  assert.match(page, /Your saved work was not changed/);
});
