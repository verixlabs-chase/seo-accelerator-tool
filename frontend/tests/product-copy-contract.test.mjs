import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  customerCopyStats,
  findProhibitedPrimaryPhrases,
} from "../app/(product)/truth/customerLanguage.mjs";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

function customerPagePaths(directory) {
  const paths = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const fullPath = join(directory, entry.name);
    if (entry.isDirectory()) {
      paths.push(...customerPagePaths(fullPath));
    } else if (/^page\.(?:js|jsx|ts|tsx)$/.test(entry.name)) {
      paths.push(fullPath);
    }
  }
  return paths;
}

const PRODUCT_PAGES = [
  "dashboard",
  "rankings",
  "keyword-research",
  "local-visibility",
  "site-health",
  "opportunities",
  "reports",
  "settings",
  "locations",
  "organic-value",
  "ai-visibility",
  "competitors",
  "content",
  "citations",
  "reviews",
  "profile-campaigns",
  "activity",
  "help",
];

test("every product introduction uses short natural outcome-led copy", () => {
  for (const route of PRODUCT_PAGES) {
    const page = source(`../app/(product)/${route}/page.tsx`);
    const start = page.indexOf("<ProductPageIntro");
    const end = page.indexOf("/>", start);
    assert.notEqual(start, -1, `${route} needs ProductPageIntro`);
    assert.notEqual(end, -1, `${route} intro must close`);
    const intro = page.slice(start, end + 2);
    const title = intro.match(/title="([^"]+)"/)?.[1] || "";
    const summary = intro.match(/summary="([^"]+)"/)?.[1] || "";

    assert.ok(title, `${route} needs a visible purpose`);
    assert.ok(summary, `${route} needs a supporting outcome`);
    assert.ok(customerCopyStats(title).words <= 12, `${route} title is too long`);
    assert.ok(customerCopyStats(summary).words <= 30, `${route} summary is too long`);
    assert.deepEqual(findProhibitedPrimaryPhrases(intro), [], route);
    assert.doesNotMatch(
      intro,
      /explained in plain English|without digging through SEO tooling|\bAI-powered\b|\bactionable insights\b|\bless tech-savvy\b|\bnon-technical owner\b/i,
      route,
    );
  }
});

test("the shared first action stays concrete for every primary route", () => {
  const intro = source("../app/(product)/components/ProductPageIntro.tsx");
  for (const route of PRODUCT_PAGES) {
    assert.match(intro, new RegExp(`"/${route}"`), route);
  }
  assert.doesNotMatch(intro, /unlock|leverage|seamless|actionable insights/i);
});

test("no customer or platform page source names the internal search supplier", () => {
  const appDirectory = fileURLToPath(new URL("../app", import.meta.url));
  const supplierPattern = new RegExp(["data", "for", "seo"].join(""), "i");

  for (const pagePath of customerPagePaths(appDirectory)) {
    assert.doesNotMatch(readFileSync(pagePath, "utf8"), supplierPattern, pagePath);
  }
});
