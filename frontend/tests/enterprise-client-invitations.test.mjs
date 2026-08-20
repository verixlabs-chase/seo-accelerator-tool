import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("Enterprise owners create one-time client report invitations", () => {
  const page = source("../app/(product)/client-access/page.tsx");
  const nav = source("../app/(product)/nav.config.ts");

  assert.match(nav, /href: "\/client-access", label: "Client access", icon: "client-access"/);
  assert.match(page, /org_role/);
  assert.match(page, /org_owner/);
  assert.match(page, /\/enterprise\/client-invitations/);
  assert.match(page, /expires_in_days/);
  assert.match(page, /setup_url/);
  assert.match(page, /will not show this setup link again/);
  assert.match(page, /navigator\.clipboard\.writeText/);
  assert.match(page, /expected_version/);
  assert.match(page, /Remove report access/);
  assert.doesNotMatch(page, /temporary password|email password|admin password/i);
});

test("client activation is private, read-only, and signs in without exposing workspace details", () => {
  const page = source("../app/client-invite/[token]/page.tsx");
  const layout = source("../app/client-invite/[token]/layout.tsx");

  assert.match(layout, /index: false/);
  assert.match(layout, /referrer: "no-referrer"/);
  assert.match(page, /\/client-invitations\/\$\{encodeURIComponent\(token\)\}/);
  assert.match(page, /password_confirmation/);
  assert.match(page, /current InsightOS password/);
  assert.match(page, /credentials: "include"/);
  assert.match(page, /router\.replace\("\/client-reports"\)/);
  assert.match(page, /read reports assigned/);
  assert.doesNotMatch(page, /Workspace ID|Tenant ID|Access role|Internal group/i);
});

test("client invitation UI keeps security and plan truth in owner language", () => {
  const ownerPage = source("../app/(product)/client-access/page.tsx");
  const publicPage = source("../app/client-invite/[token]/page.tsx");

  assert.match(ownerPage, /available with Enterprise/);
  assert.match(ownerPage, /Clients see assigned reports, not your workspace tools or private settings/);
  assert.match(publicPage, /person who invited you cannot see it/);
  assert.match(publicPage, /Ask the person who invited you to create a new setup link/);
  assert.doesNotMatch(`${ownerPage}\n${publicPage}`, /token hash|AES|RLS|PBKDF|service account|provider/i);
});
