import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("all product tools stay visible in familiar navigation groups", () => {
  const nav = source("../app/(product)/nav.config.ts");
  const sidebar = source("../app/(product)/components/SidebarNav.tsx");

  for (const section of ["most-used", "performance", "improve", "workspace", "help"]) {
    assert.match(nav, new RegExp(`section: "${section}"`));
  }
  for (const label of [
    "Most used",
    "Measure performance",
    "Improve visibility",
    "Manage workspace",
    "Help",
  ]) {
    assert.match(sidebar, new RegExp(label));
  }
  assert.match(sidebar, /overflow-y-auto/);
  assert.doesNotMatch(sidebar, /More tools|<details|<summary/);
  assert.doesNotMatch(nav, /section: "more"/);
});

test("frequent work leads each category and workspace controls stay together", () => {
  const nav = source("../app/(product)/nav.config.ts");
  const expectedOrder = [
    "/dashboard",
    "/opportunities",
    "/reviews",
    "/reports",
    "/rankings",
    "/local-visibility",
    "/site-health",
    "/organic-value",
    "/ai-visibility",
    "/keyword-research",
    "/competitors",
    "/content",
    "/citations",
    "/profile-campaigns",
    "/locations",
    "/settings",
    "/client-access",
    "/activity",
    "/help",
  ];

  let previousIndex = -1;
  for (const path of expectedOrder) {
    const index = nav.indexOf(`href: "${path}"`);
    assert.ok(index > previousIndex, `${path} should follow the category and frequency order`);
    previousIndex = index;
  }
});
