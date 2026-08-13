import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const settingsPage = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);
const rankingsPage = readFileSync(
  fileURLToPath(new URL("../app/(product)/rankings/page.tsx", import.meta.url)),
  "utf8",
);
const citationsPage = readFileSync(
  fileURLToPath(new URL("../app/(product)/citations/page.tsx", import.meta.url)),
  "utf8",
);
const reportsPage = readFileSync(
  fileURLToPath(new URL("../app/(product)/reports/page.tsx", import.meta.url)),
  "utf8",
);

test("migration setup starts with a non-destructive CSV review", () => {
  assert.match(settingsPage, /Bring over your setup and useful history/);
  assert.match(settingsPage, /Download CSV template/);
  assert.match(settingsPage, /migration-imports\/dry-run/);
  assert.match(settingsPage, /Nothing has been imported yet/);
  assert.match(settingsPage, /no changes are made during review/);
  assert.match(settingsPage, /Needs attention/);
});

test("migration review accepts the supported switching sources", () => {
  assert.match(settingsPage, /Another spreadsheet/);
  assert.match(settingsPage, /Semrush/);
  assert.match(settingsPage, /BrightLocal/);
  assert.match(settingsPage, /source_system: migrationSource/);
  assert.match(settingsPage, /migrationReview\.adapter/);
  assert.match(settingsPage, /familiar headings/);
});

test("reviewed migration requires confirmation and preserves a reversible history", () => {
  assert.match(settingsPage, /migrationReview\.review_hash/);
  assert.match(settingsPage, /I reviewed this file/);
  assert.match(settingsPage, /Import reviewed rows/);
  assert.match(settingsPage, /migration-imports\/apply/);
  assert.match(settingsPage, /Undo this import/);
  assert.match(settingsPage, /Recent imports/);
  assert.match(settingsPage, /Newer attached work will be protected/);
});

test("large migration files upload in resumable verified parts", () => {
  assert.match(settingsPage, /migration-imports\/uploads/);
  assert.match(settingsPage, /received_chunk_indexes/);
  assert.match(settingsPage, /chunk_sha256: await sha256Text/);
  assert.match(settingsPage, /expected_sha256: expectedSha256/);
  assert.match(settingsPage, /insightos:migration-upload/);
  assert.match(settingsPage, /Uploaded parts are saved for seven days/);
  assert.match(settingsPage, /Review more rows/);
  assert.doesNotMatch(settingsPage, /localStorage\.setItem\([^)]*migrationCsv/s);
});

test("historical rankings and unsupported columns remain visibly qualified", () => {
  assert.match(settingsPage, /Past rankings/);
  assert.match(settingsPage, /not being imported/);
  assert.match(settingsPage, /nothing is silently treated as an InsightOS measurement/);
  assert.match(settingsPage, /ranking_history_created/);
  assert.match(rankingsPage, /imported historical point/);
  assert.match(rankingsPage, /do not count as a fresh live check/);
});

test("imported listing history stays separate from fresh public checks", () => {
  assert.match(settingsPage, /Past listings/);
  assert.match(settingsPage, /listing_history_created/);
  assert.match(settingsPage, /Switching checklist/);
  assert.match(settingsPage, /They never count as a new InsightOS check/);
  assert.match(citationsPage, /Imported history/);
  assert.match(citationsPage, /do not count as a fresh online check/);
  assert.match(citationsPage, /Run a public listing check before treating it as current/);
});

test("imported report recipients remain off until an owner reviews them", () => {
  assert.match(settingsPage, /Report recipients/);
  assert.match(settingsPage, /report_recipients_created/);
  assert.match(settingsPage, /Imported recipients are off until reviewed/);
  assert.match(reportsPage, /Imported recipients start turned off/);
  assert.match(reportsPage, /Imported · Off until reviewed/);
  assert.match(reportsPage, /Review and turn on/);
});
