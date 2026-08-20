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
  assert.match(page, /Download PDF/);
  assert.match(page, /pdf_available/);
  assert.match(page, /\/enterprise\/client-reports\/.*\/download/);
  assert.match(page, /platformApiFile/);
  assert.match(page, /application\/pdf/);
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
  assert.match(page, /PDF download not available/);
  assert.match(page, /ask the workspace owner/i);
  assert.doesNotMatch(page, /artifact|tenant|campaign_id|organization_id|provider|HTTP/i);
});

test("clients can narrow a large report library by location and saved date", () => {
  const page = source("../app/client-reports/page.tsx");

  assert.match(page, /All assigned locations/);
  assert.match(page, /Saved in the last 31 days/);
  assert.match(page, /Older saved reports/);
  assert.match(page, /visibleReports\.map/);
  assert.match(page, /Showing \{visibleReports\.length\} of \{data\.items\.length\} assigned reports/);
  assert.match(page, /No reports match these choices/);
  assert.match(page, /Show all assigned reports/);
  assert.doesNotMatch(page, /query builder|database filter|artifact type|tenant scope/i);
});

test("current customer-safe report identity brands the isolated client portal", () => {
  const page = source("../app/client-reports/page.tsx");
  const layout = source("../app/client-reports/layout.tsx");
  const identity = source("../app/clientPortalIdentity.ts");

  for (const field of [
    "display_name",
    "portal_title",
    "accent_color",
    "logo_data_url",
    "platform_attribution_visible",
  ]) {
    assert.match(`${page}\n${identity}`, new RegExp(field));
  }
  assert.match(identity, /data:image\/png;base64,/);
  assert.match(page, /identity\.logo_data_url/);
  assert.match(page, /identity\.display_name/);
  assert.match(page, /identity\.portal_title/);
  assert.match(page, /style=\{\{ backgroundColor: identity\.accent_color \}\}/);
  assert.match(page, /identity\.platform_attribution_visible/);
  assert.match(page, /Private report access provided through InsightOS/);
  assert.match(page, /data\s*\? safeClientPortalIdentity\(data\.identity\)\s*:\s*LOADING_CLIENT_PORTAL_IDENTITY/);
  assert.doesNotMatch(page, /identity\.(organization_id|branding_version|logo_sha256|logo_width|logo_height|storage_key)/);
  assert.doesNotMatch(layout, /\| InsightOS/);
});
