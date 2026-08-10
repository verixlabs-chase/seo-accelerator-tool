import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/reviews/page.tsx", import.meta.url)),
  "utf8",
);

test("customer review inbox is location scoped, filterable, and governed", () => {
  assert.match(page, /useLocationContext/);
  assert.match(page, /reviews\/inventory/);
  assert.match(page, /reviews\/sync/);
  assert.match(page, /Needs a reply/);
  assert.match(page, /3 stars or lower/);
  assert.match(page, /Answered/);
  assert.match(page, /reviews\/response-policy/);
  assert.match(page, /reviews\/drafts/);
  assert.match(page, /Draft a reply/);
  assert.match(page, /Approve this wording/);
  assert.match(page, /Discard draft/);
  assert.match(page, /A person should handle this reply/);
  assert.match(page, /No AI action or credit was used/);
  assert.match(page, /textarea/);
  assert.match(page, /reviews\/posting-status/);
  assert.match(page, /confirm_publish_to_google: true/);
  assert.match(page, /Post approved reply to Google/);
  assert.match(page, /Automatic replies are off/);
  assert.match(page, /Pause posting/);
  assert.match(page, /Posting history stays attached/);
  assert.doesNotMatch(page, /Post reply/);
  assert.doesNotMatch(page, /chat/i);
});
