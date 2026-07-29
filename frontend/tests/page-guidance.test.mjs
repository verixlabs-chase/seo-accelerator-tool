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

test("the shared guide is dismissible for the browser session", () => {
  const componentPath = fileURLToPath(
    new URL("../app/(product)/components/TruthNotice.tsx", import.meta.url),
  );
  const source = readFileSync(componentPath, "utf8");

  assert.match(source, /sessionStorage\.setItem\(storageKey, "dismissed"\)/);
  assert.match(source, /aria-label="Close page guidance"/);
  assert.doesNotMatch(source, /Good to know/i);
});
