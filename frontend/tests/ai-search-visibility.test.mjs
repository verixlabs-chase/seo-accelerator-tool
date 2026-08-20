import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

const page = source("../app/(product)/ai-visibility/page.tsx");
const nav = source("../app/(product)/nav.config.ts");
const intro = source("../app/(product)/components/ProductPageIntro.tsx");
const icons = source("../app/(product)/components/ProductIcon.tsx");

test("AI Search beta has a dedicated location-scoped workspace", () => {
  assert.match(nav, /href: "\/ai-visibility", label: "AI Search", icon: "ai-search", section: "performance", badge: "Beta"/);
  assert.match(intro, /"\/ai-visibility"/);
  assert.match(icons, /case "ai-search"/);
  assert.match(page, /useLocationContext/);
  assert.match(page, /selectedCampaignId/);
  assert.match(page, /\/ai-search\/summary\?campaign_id=/);
  assert.match(page, /Reload saved results/);
});

test("AI Search keeps every observed fact separate and refuses a composite score", () => {
  for (const label of [
    "Answers checked",
    "Mentioned",
    "Recommended",
    "Cited as a source",
    "Linked",
  ]) {
    assert.match(page, new RegExp(label));
  }
  assert.match(page, /A mention is not automatically a recommendation, citation, or link/);
  assert.match(page, /measured === null \|\| measured <= 0/);
  for (const fact of ["mentioned", "recommended", "cited", "linked"]) {
    assert.match(
      page,
      new RegExp(`coverage\\?\\.${fact}\\?\\.measured`),
      `${fact} must use its own measurement coverage`,
    );
  }
  assert.doesNotMatch(page, /AI visibility score/i);
  assert.doesNotMatch(page, /entity\/report/);
});

test("mention claims use the mention-specific measured denominator", () => {
  const decisionStart = page.indexOf("function decisionFor");
  const decisionEnd = page.indexOf("export default function", decisionStart);
  const decisionSource = page.slice(decisionStart, decisionEnd);

  assert.match(decisionSource, /coverage\?\.mentioned\?\.measured/);
  assert.match(decisionSource, /if \(mentionMeasured > 0\)/);
  assert.match(decisionSource, /appeared in \$\{mentioned\} of \$\{mentionMeasured\}/);
  assert.match(decisionSource, /total: mentionMeasured/);
  assert.match(decisionSource, /valueLabel: `\$\{mentioned\} of \$\{mentionMeasured\}`/);
  assert.match(decisionSource, /if \(checked > 0\)/);
  assert.match(decisionSource, /mentions were not checked/);
  assert.match(decisionSource, /It cannot show whether the business appeared/);
  assert.doesNotMatch(decisionSource, /appeared in \$\{mentioned\} of \$\{checked\}/);
  assert.doesNotMatch(decisionSource, /not found in the \$\{checked\}/);
});

test("AI Search uses honest unavailable, partial, stale, and saved-error states", () => {
  assert.match(page, /state === "unavailable" \|\| state === "unsupported"/);
  assert.match(page, /state === "partial"/);
  assert.match(page, /state === "stale"/);
  assert.match(page, /No result is being reported as zero/);
  assert.match(page, /Missing services are not counted as zero/);
  assert.match(page, /if \(!preserveSaved\) setPayload\(null\)/);
  assert.match(page, /The saved results from/);
  assert.match(page, /No AI search result has been measured/);
});

test("customer questions are frozen, compact, and update only from confirmed context", () => {
  const decisionStart = page.indexOf("function decisionFor");
  const decisionEnd = page.indexOf("export default function", decisionStart);
  const decisionSource = page.slice(decisionStart, decisionEnd);

  assert.match(page, /payload\?\.setup\?\.ready === true/);
  assert.match(page, /payload\.setup\.question_set_ready === false/);
  assert.match(page, /\/ai-search\/question-sets\?campaign_id=/);
  assert.match(page, /Saved customer questions need an update/);
  assert.ok(
    decisionSource.indexOf("Saved customer questions need an update") <
      decisionSource.indexOf('summary.truth?.state === "unavailable"'),
    "a stale saved question list must remain actionable while AI answer collection is unavailable",
  );
  assert.match(page, /Saved question list/);
  assert.match(page, /questionSet\?\.questions\?\.slice\(0, 12\)/);
  assert.match(page, /Show \{remainingQuestions\.length\} more saved questions/);
  assert.match(page, /This saves the questions only and does not run an AI search check/);
  assert.doesNotMatch(page, /<textarea/);
  assert.doesNotMatch(page, /chat box|chatbot/i);
});

test("engine availability is owner-readable and hides registry and supplier details", () => {
  assert.match(page, /AI answer services included/);
  assert.match(page, /No AI search services are available for this location yet/);
  assert.match(page, /engine\.supported_geographies/);
  assert.match(page, /engine\.supported_languages/);
  assert.match(page, /engine\.supported_devices/);
  assert.match(page, /Places:/);
  assert.match(page, /Languages:/);
  assert.match(page, /Devices:/);
  assert.doesNotMatch(page, /engine\.version/);
  assert.doesNotMatch(page, /supported_locales/);
  assert.doesNotMatch(page, /collection_method/);
  assert.doesNotMatch(page, new RegExp(["data", "for", "seo"].join(""), "i"));
});
