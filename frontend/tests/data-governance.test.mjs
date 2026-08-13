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

test("Google disconnect is owner-confirmed, comprehensive, and preserves saved results", () => {
  assert.match(settingsPage, /Google access and saved results/);
  assert.match(settingsPage, /Review disconnect/);
  assert.match(settingsPage, /This affects all Google access for this workspace/);
  assert.match(settingsPage, /These updates will stop/);
  assert.match(settingsPage, /This information will stay/);
  assert.match(settingsPage, /googleDisconnectConfirmation !== googleDisconnectPreview\.confirmation_text/);
  assert.match(settingsPage, /data-governance\/provider-disconnects/);
  assert.match(settingsPage, /the local authorization was deleted, and your saved results remain available/);
});

test("disconnect history makes incomplete outside revocation visible", () => {
  assert.match(settingsPage, /Most recent change/);
  assert.match(settingsPage, /external_revocation_status === "not_confirmed"/);
  assert.match(settingsPage, /Review third-party access in your Google Account/);
  assert.match(settingsPage, /Google confirmed the authorization was revoked/);
});

test("workspace closure is recoverable, owner-confirmed, and honest about deletion", () => {
  assert.match(settingsPage, /Close this workspace safely/);
  assert.match(settingsPage, /read-only for \{closurePreview\.recovery_days\} days/);
  assert.match(settingsPage, /closureConfirmation !== closurePreview\.confirmation_text/);
  assert.match(settingsPage, /data-governance\/closures/);
  assert.match(settingsPage, /Keep workspace open/);
  assert.match(settingsPage, /Primary business data is not claimed deleted/);
});

test("closure screen explains holds, exports, and irreversible security actions", () => {
  assert.match(settingsPage, /Create and download an account export first/);
  assert.match(settingsPage, /revokes public report links and cancels queued work immediately/);
  assert.match(settingsPage, /retention hold is active/);
  assert.match(settingsPage, /old public report links and canceled jobs were not reopened/);
});
