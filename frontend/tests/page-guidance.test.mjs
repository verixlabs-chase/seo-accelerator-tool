import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const productRoutes = [
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

test("customer pages render at most one proactive guide", () => {
  for (const route of productRoutes) {
    const pagePath = fileURLToPath(
      new URL(`../app/(product)/${route}/page.tsx`, import.meta.url),
    );
    const source = readFileSync(pagePath, "utf8");
    const guideCount = source.match(/<TruthNotice\b/g)?.length || 0;

    assert.ok(
      guideCount <= 1,
      `${route} renders ${guideCount} proactive guides`,
    );
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

test("the shared guide is dismissible for the browser session", () => {
  const componentPath = fileURLToPath(
    new URL("../app/(product)/components/TruthNotice.tsx", import.meta.url),
  );
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /sessionStorage\.setItem\(storageKey, "dismissed"\)/);
  assert.match(source, /aria-label="Close page guidance"/);
  assert.doesNotMatch(source, /Good to know/i);
});

test("opportunities keeps AI subordinate to deterministic intelligence", () => {
  const pagePath = fileURLToPath(
    new URL("../app/(product)/opportunities/page.tsx", import.meta.url),
  );
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /A plain-language explanation of your next move/);
  assert.match(source, /Decision authority: intelligence engine/);
  assert.match(source, /AI role: explain only/);
  assert.match(source, /Automatic\s+changes: off/);
  assert.match(source, /cannot change the action/);
  assert.match(source, /retry_failed/);
  assert.doesNotMatch(source, /reconciled_cost/);
});
