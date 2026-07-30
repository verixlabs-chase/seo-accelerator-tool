import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const productRoutes = [
  "dashboard",
  "citations",
  "competitors",
  "local-visibility",
  "locations",
  "opportunities",
  "organic-value",
  "rankings",
  "reports",
  "settings",
  "site-health",
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
  assert.match(source, /insightos-daily-guide-v4/);
  assert.doesNotMatch(source, /localStorage\.setItem\(cacheKey, JSON\.stringify\(fallback\)\)/);
  assert.match(source, /simplifyGuideText/);
  assert.match(source, /deterministic SEO intelligence/);
  assert.match(source, /Google business listing/);
  assert.match(source, /website speed and stability/);
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

  assert.match(source, /Open the plain-language explanation/);
  assert.match(source, /The system chooses the evidence and next action/);
  assert.match(source, /Automatic changes are off/);
  assert.match(source, /cannot change your website/);
  assert.match(source, /retry_failed/);
  assert.doesNotMatch(source, /Deterministic summary/);
  assert.doesNotMatch(source, /Engine-selected action/);
  assert.doesNotMatch(source, /Decision authority/);
  assert.doesNotMatch(source, /reconciled_cost/);
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
});
