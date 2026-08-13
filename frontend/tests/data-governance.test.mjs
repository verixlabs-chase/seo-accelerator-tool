import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const settingsPage = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);

test("account owners can create and securely download a portable account export", () => {
  assert.match(settingsPage, /me\?\.org_role === "org_owner"/);
  assert.match(settingsPage, /Create account export/);
  assert.match(settingsPage, /data-governance\/exports/);
  assert.match(settingsPage, /client_request_id: crypto\.randomUUID/);
  assert.match(settingsPage, /platformApiFile/);
  assert.match(settingsPage, /Download JSON/);
});

test("the export screen explains its safety and retention limits in plain language", () => {
  assert.match(settingsPage, /Passwords, login sessions, connected-account credentials/);
  assert.match(settingsPage, /never placed in the file/);
  assert.match(settingsPage, /Available for seven days/);
  assert.match(settingsPage, /Only an account owner can create or download an export/);
  assert.match(settingsPage, /its audit record remains/);
  assert.doesNotMatch(settingsPage, /Delete (your )?(account|organization)/i);
});
