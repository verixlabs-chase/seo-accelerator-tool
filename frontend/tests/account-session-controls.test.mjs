import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);

test("settings loads server-backed active sign-ins without exposing credentials", () => {
  assert.match(settings, /platformApi\("\/auth\/sessions",/);
  assert.match(settings, /Where you&apos;re signed in/);
  assert.match(settings, /This browser/);
  assert.match(settings, /Another signed-in browser/);
  assert.match(settings, /Passwords and login tokens are never shown here/);

  const sessionTypeStart = settings.indexOf("type AuthSessionSummary");
  const sessionTypeEnd = settings.indexOf("};", sessionTypeStart);
  const sessionType = settings.slice(sessionTypeStart, sessionTypeEnd);
  assert.doesNotMatch(sessionType, /access_token|refresh_token|password|secret/i);
});

test("session controls preserve the current browser", () => {
  assert.match(settings, /platformApi\(`\/auth\/sessions\/\$\{sessionId\}`,[\s\S]{0,80}method: "DELETE"/);
  assert.match(settings, /platformApi\("\/auth\/sessions\/others",[\s\S]{0,80}method: "DELETE"/);
  assert.match(settings, /session\.current \? "This browser"/);
  assert.match(settings, /!session\.current \? \(/);
  assert.match(settings, /This browser stayed signed in/);
  assert.doesNotMatch(settings, /platformApi\(`\/auth\/sessions\/\$\{session\.id\}`/);
});

test("a session-list failure is honest and does not imply a sign-out", () => {
  assert.match(settings, /Active sign-ins could not be checked/);
  assert.match(settings, /Your current session was not changed/);
  assert.match(settings, /Check again/);
  assert.match(settings, /loadAuthSessions\(\)\.catch\(\(\) => null\)/);
});
