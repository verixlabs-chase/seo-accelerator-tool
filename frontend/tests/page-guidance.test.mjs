import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const productRoutes = [
  "dashboard",
  "citations",
  "competitors",
  "content",
  "local-visibility",
  "locations",
  "opportunities",
  "organic-value",
  "ai-visibility",
  "rankings",
  "keyword-research",
  "reports",
  "reviews",
  "settings",
  "site-health",
  "activity",
];

test("every customer page renders exactly one proactive guide", () => {
  for (const route of productRoutes) {
    const pagePath = fileURLToPath(
      new URL(`../app/(product)/${route}/page.tsx`, import.meta.url),
    );
    const source = readFileSync(pagePath, "utf8");
    const guideCount = source.match(/<TruthNotice\b/g)?.length || 0;

    assert.equal(guideCount, 1, `${route} renders ${guideCount} proactive guides`);
  }
});

test("website health separates real-user and lab performance in plain language", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/site-health/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /Real customer experience/);
  assert.match(source, /One-time lab test/);
  assert.match(source, /Not enough real-user data/);
  assert.match(source, /1 year/);
  assert.match(source, /fallback because this page lacks enough visits/);
  assert.match(source, /does not guarantee higher rankings/);
  assert.match(source, /The lab test did not finish/);
});

test("website health keeps Google index evidence distinct and actionable", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/site-health/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /Can Google find and keep your important pages/);
  assert.match(source, /crawl\/site-integrity\/refresh/);
  assert.match(source, /Check important pages/);
  assert.match(source, /Confirmed in Google/);
  assert.match(source, /specific page, evidence, source, and next step/);
  assert.match(source, /not a live indexing test/);
  assert.match(source, /A sitemap submission is not treated as proof/);
});

test("website health explains crawl integrity findings without crawler jargon", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/site-health/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /A website link leads to a broken page/);
  assert.match(source, /Two pages contain the same content/);
  assert.match(source, /No scanned page links to this page/);
  assert.match(source, /Page sends visitors through several redirects/);
  assert.match(source, /Search result details contain an error/);
  assert.match(source, /Update or remove the broken link/);
  assert.match(source, /Matches \$\{details\.duplicate_with\}/);
});

test("healthy data flags stay hidden while actionable states remain visible", () => {
  const statusPath = fileURLToPath(
    new URL("../app/(product)/components/TrustStatusBar.tsx", import.meta.url),
  );
  const kpiPath = fileURLToPath(
    new URL("../app/(product)/components/KpiCard.tsx", import.meta.url),
  );
  const statusSource = readFileSync(statusPath, "utf8");
  const kpiSource = readFileSync(kpiPath, "utf8");

  assert.match(statusSource, /signal\.tone === "warning" \|\| signal\.tone === "danger"/);
  assert.match(statusSource, /actionableSignals\.length === 0/);
  assert.match(kpiSource, /<TrendIndicator label=\{changeLabel\} tone=\{changeTone\}/);
});

test("the shared guide is daily, AI-written, cached, and dismissible", () => {
  const componentPath = fileURLToPath(
    new URL("../app/(product)/components/TruthNotice.tsx", import.meta.url),
  );
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /intelligence\/brief/);
  assert.match(source, /method: "POST"/);
  assert.match(source, /insightos-daily-guide/);
  assert.match(source, /insightos-daily-guide-v5/);
  assert.match(source, /daily_action_ids/);
  assert.match(source, /actions are ready/);
  assert.doesNotMatch(source, /localStorage\.setItem\(cacheKey, JSON\.stringify\(fallback\)\)/);
  assert.match(source, /simplifyCustomerCopy/);
  assert.match(source, /customerLanguage\.mjs/);
  assert.match(source, /localStorage\.setItem\(cacheKey/);
  assert.match(source, /sessionStorage\.setItem\(storageKey, "dismissed"\)/);
  assert.match(source, /aria-label="Close daily guidance"/);
  assert.match(source, /Today&apos;s focus/);
  assert.doesNotMatch(source, /Good to know/i);
});

test("opportunities keeps AI subordinate while using owner-friendly labels", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/opportunities/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /Open today&apos;s action list/);
  assert.match(source, /InsightOS uses the saved facts and approved actions/);
  assert.match(source, /daily_actions/);
  assert.match(source, /Today&apos;s action list/);
  assert.match(source, /Automatic changes are off/);
  assert.match(source, /cannot change your website/);
  assert.match(source, /retry_failed/);
  assert.doesNotMatch(source, /Deterministic summary/);
  assert.doesNotMatch(source, /Engine-selected action/);
  assert.doesNotMatch(source, /Decision authority/);
  assert.doesNotMatch(source, /reconciled_cost/);
});

test("opportunities shows a persistent cadence board and focused checklist", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/opportunities/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /Your action plan/);
  assert.match(source, /Your daily, weekly, and monthly checklist/);
  assert.match(source, /This week/);
  assert.match(source, /This month/);
  assert.match(source, /updateChecklistStep/);
  assert.match(source, /saves your progress automatically/);
  assert.match(source, /Current checklist/);
  assert.match(source, /Next unchecked step/);
  assert.match(source, /All actions and supporting details/);
  assert.match(source, /aria-pressed=\{isDone\}/);
  assert.match(source, /OWNER_JOURNEY_V2_ENABLED/);
  assert.match(source, /getRecommendationPortfolio/);
  assert.doesNotMatch(source, /Your one best next step/);
});

test("the shared page intro puts a start-here instruction on every primary route", () => {
  const componentPath = fileURLToPath(
    new URL("../app/(product)/components/ProductPageIntro.tsx", import.meta.url),
  );
  const source = readFileSync(componentPath, "utf8");

  for (const route of productRoutes) {
    assert.match(source, new RegExp(`"/${route}"`));
  }
  assert.match(source, /Start here/);
  assert.match(source, /ProductIcon/);
});
