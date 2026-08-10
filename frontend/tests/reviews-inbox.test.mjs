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
  assert.match(page, /reviews\/intelligence/);
  assert.match(page, /reviews\/portfolio/);
  assert.match(page, /This location/);
  assert.match(page, /All locations/);
  assert.match(page, /How customer feedback is changing/);
  assert.match(page, /Actions tied to your reviews/);
  assert.match(page, /See the customer feedback behind this/);
  assert.match(page, /Reviews by location chart/);
  assert.match(page, /Locations ordered by attention needed/);
  assert.match(page, /reviews\/request-readiness/);
  assert.match(page, /reviews\/request-campaigns/);
  assert.match(page, /Get more honest reviews/);
  assert.match(page, /Ask every eligible customer the same way/);
  assert.match(page, /No review gating/);
  assert.match(page, /Create review link/);
  assert.match(page, /result_summary\.note/);
  assert.doesNotMatch(page, /sentiment|velocity|taxonomy|deterministic summary/i);
  assert.doesNotMatch(page, /only happy customers|only satisfied customers|positive customers/i);
  assert.doesNotMatch(page, /Post reply/);
  assert.doesNotMatch(page, /chat/i);
});
