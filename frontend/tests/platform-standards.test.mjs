import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pagePath = path.join(here, "..", "app", "platform", "standards", "page.jsx");
const page = fs.readFileSync(pagePath, "utf8");

test("standards workspace exposes evidence, owner decisions, rollout, and rollback", () => {
  assert.match(page, /Exact definition difference/);
  assert.match(page, /What decisions could change/);
  assert.match(page, /Fixed replay results/);
  assert.match(page, /Approve replay/);
  assert.match(page, /Reject replay/);
  assert.match(page, /Schedule rollout/);
  assert.match(page, /Restore previous version/);
  assert.match(page, /Unusual shared movement/);
  assert.match(page, /at least five separate organizations/);
  assert.match(page, /cannot prove an algorithm update/);
});

test("standards workspace calls only governed standards endpoints", () => {
  assert.match(page, /reference-library\/standards\/status/);
  assert.match(page, /standards\/replays\/\$\{report\.id\}\/decision/);
  assert.match(page, /standards\/approvals\/\$\{approval\.id\}\/rollouts/);
  assert.match(page, /standards\/rollouts\/\$\{rollout\.id\}\/rollback/);
  assert.match(page, /Automatic activation is off/);
  assert.match(page, /standards\/drift\/check/);
  assert.match(page, /standards\/drift\/events\/\$\{event\.id\}\/review/);
});
