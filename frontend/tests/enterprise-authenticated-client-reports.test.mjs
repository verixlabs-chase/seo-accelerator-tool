import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("client sign-ins receive one private read-only report workspace", () => {
  const page = source("../app/client-reports/page.tsx");
  const login = source("../app/login/page.jsx");
  const guard = source("../app/(product)/components/ProductRoleGuard.tsx");

  assert.match(login, /org_client.*client-reports/);
  assert.match(guard, /user\?\.org_role === "org_client"/);
  assert.match(guard, /router\.replace\("\/client-reports"\)/);
  assert.match(page, /\/enterprise\/client-reports/);
  assert.match(page, /assigned to you/);
  assert.match(page, /cannot change the business, billing, settings, or tracked work/);
  assert.doesNotMatch(page, /buildProductNav|AppShell|LocationProvider|\/billing\/|\/settings\/|method: "POST"|method: "PATCH"|method: "DELETE"/);
});

test("authenticated report HTML remains script and origin isolated", () => {
  const page = source("../app/client-reports/page.tsx");
  const api = source("../app/platform/api.js");
  const layout = source("../app/client-reports/layout.tsx");

  assert.match(api, /export async function platformApiText/);
  assert.match(page, /srcDoc=\{reportHtml\}/);
  assert.match(page, /sandbox=""/);
  assert.match(page, /referrerPolicy="no-referrer"/);
  assert.doesNotMatch(page, /dangerouslySetInnerHTML|allow-scripts|allow-same-origin/);
  assert.match(layout, /index: false, follow: false, nocache: true/);
});

test("client report states explain saved dates and empty access plainly", () => {
  const page = source("../app/client-reports/page.tsx");

  assert.match(page, /No reports have been shared here yet/);
  assert.match(page, /Older saved report/);
  assert.match(page, /Saved date unavailable/);
  assert.match(page, /ask the workspace owner/i);
  assert.doesNotMatch(page, /artifact|tenant|campaign_id|organization_id|provider|HTTP/i);
});
