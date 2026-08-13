import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/opportunities/page.tsx", import.meta.url)),
  "utf8",
);

test("WordPress live delivery requires a customer-triggered connection handshake", () => {
  assert.match(page, /\/provider-health\/wordpress-execution-setup/);
  assert.match(page, /\/provider-health\/wordpress-execution-check/);
  assert.match(page, /\/provider-health\/wordpress-pairing\/start/);
  assert.match(page, /\/provider-health\/wordpress-connection/);
  assert.match(page, /\/provider-health\/wordpress-content-sync/);
  assert.match(page, /\/provider-health\/wordpress-content-inventory/);
  assert.match(page, /Test connection/);
  assert.match(page, /Create pairing code/);
  assert.match(page, /Replace connection key/);
  assert.match(page, /Disconnect/);
  assert.match(page, /WordPress changes still require review and approval/);
  assert.match(page, /WordPress administrator password is never shared/i);
  assert.match(page, /Read website content/);
  assert.match(page, /Nothing on the website was changed|It does not change anything/);
  assert.match(page, /posts, pages, and other public website content/);
  assert.match(page, /future previews use the current version/);
  assert.match(page, /platformApiFile/);
  assert.match(page, /\/provider-health\/wordpress-plugin-download/);
  assert.match(page, /Download WordPress plugin/);
  assert.match(page, /Download latest plugin/);
  assert.match(page, /How to install and connect WordPress/);
  assert.match(page, /Do not unzip it/);
  assert.match(page, /Plugins, choose Add Plugin, then Upload Plugin/);
  assert.match(page, /Settings, choose InsightOS/);
  assert.match(page, /Package check/);
});

test("WordPress setup loading failures do not render live-only controls", () => {
  const guardedLiveModeBranches =
    page.match(/wordpressSetup && wordpressSetup\.mode !== "test"/g) || [];

  assert.equal(guardedLiveModeBranches.length, 2);
  assert.doesNotMatch(page, /wordpressSetup\?\.mode !== "test"/);
});

test("WordPress changes require a readable exact preview before approval", () => {
  assert.match(page, /Check website changes/);
  assert.match(page, /Website change preview/);
  assert.match(page, /Current/);
  assert.match(page, /Proposed/);
  assert.match(page, /Approve these changes/);
  assert.match(page, /preview_hash/);
  assert.match(page, /Nothing on the website was changed/);
  assert.match(page, /If you need to undo it/);
  assert.doesNotMatch(page, /Latest dry run preview/);
  assert.doesNotMatch(page, /JSON\.stringify\(dryRunPreview\.result, null, 2\)/);
});

test("WordPress results show public-page proof and a recovery path", () => {
  assert.match(page, /Public website check/);
  assert.match(page, /The live website matches the approved changes/);
  assert.match(page, /Open public page/);
  assert.match(page, /use Rollback to restore the saved values/);
  assert.match(page, /execution\.status === "failed" && execution\.result\?\.rollback_available/);
  assert.match(page, /execution\.status === "failed" && !execution\.result\?\.rollback_available/);
});

test("Interrupted WordPress actions can be finished without duplicating the approved change", () => {
  assert.match(page, /execution\.status === "running"/);
  assert.match(page, /Finish interrupted run/);
  assert.match(page, /same approved website change will not be duplicated/);
  assert.match(page, /resumed after the interrupted run/);
});

test("managed WordPress updates stay owner-scoped and fail closed", () => {
  assert.match(page, /\/wordpress-automation\/policy/);
  assert.match(page, /Managed website updates/);
  assert.match(page, /Allow managed updates/);
  assert.match(page, /Allowed website area/);
  assert.match(page, /Monthly update limit/);
  assert.match(page, /Highest risk allowed/);
  assert.match(page, /Ask me before each update/);
  assert.match(page, /Pause managed updates now/);
  assert.match(page, /preview, history, and rollback/);
});
