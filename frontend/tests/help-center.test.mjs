import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  GLOSSARY_TERMS,
  HELP_AUDIENCES,
  HELP_GUIDES,
  matchesHelpSearch,
} from "../app/(product)/help/helpContent.ts";
import { findProhibitedPrimaryPhrases } from "../app/(product)/truth/customerLanguage.mjs";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("help center covers setup, results, actions, problems, and multi-location work", () => {
  assert.deepEqual(
    HELP_AUDIENCES.map((item) => item.id),
    ["solo", "multi", "team"],
  );
  assert.ok(HELP_GUIDES.length >= 12);
  assert.ok(GLOSSARY_TERMS.length >= 10);

  for (const category of ["Get started", "Understand results", "Take action", "Fix a problem"]) {
    assert.ok(HELP_GUIDES.some((guide) => guide.category === category), category);
  }

  const multiLocationGuide = HELP_GUIDES.find((guide) => guide.id === "manage-locations");
  assert.ok(multiLocationGuide);
  assert.deepEqual(multiLocationGuide.audiences, ["multi", "team"]);
  assert.match(multiLocationGuide.summary, /its own website, listing, tracked searches/i);
});

test("help search finds owner tasks and familiar alternate words", () => {
  const gridGuide = HELP_GUIDES.find((guide) =>
    matchesHelpSearch(
      [guide.title, guide.summary, ...guide.steps, ...guide.searchTerms],
      "heatmap",
    ),
  );
  assert.equal(gridGuide?.id, "read-local-grid");

  const staleGuide = HELP_GUIDES.find((guide) =>
    matchesHelpSearch(
      [guide.title, guide.summary, ...guide.steps, ...guide.searchTerms],
      "not updating",
    ),
  );
  assert.equal(staleGuide?.id, "fix-stale-data");

  const definition = GLOSSARY_TERMS.find((item) =>
    matchesHelpSearch([item.term, item.meaning, ...item.searchTerms], "impressions"),
  );
  assert.equal(definition?.term, "Times shown on Google");
});

test("help center is discoverable and gives a safe support handoff", () => {
  const navSource = source("../app/(product)/nav.config.ts");
  const pageSource = source("../app/(product)/help/page.tsx");
  const introSource = source("../app/(product)/components/ProductPageIntro.tsx");

  assert.match(navSource, /href: "\/help", label: "Help Center", icon: "help"/);
  assert.match(introSource, /"\/help": "help"/);
  assert.match(pageSource, /What do you need help with\?/);
  assert.match(pageSource, /support@verixlabs\.com/);
  assert.match(pageSource, /Never send a password, sign-in code, payment number, or private access key/);
  assert.match(pageSource, /aria-live="polite"/);
  assert.match(pageSource, /aria-pressed=\{selected\}/);
  assert.deepEqual(findProhibitedPrimaryPhrases(pageSource), []);
  assert.deepEqual(
    findProhibitedPrimaryPhrases(source("../app/(product)/help/helpContent.ts")),
    [],
  );
});
