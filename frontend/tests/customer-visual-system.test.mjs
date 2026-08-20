import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  CUSTOMER_LANGUAGE_VERSION,
  customerCopyStats,
  describeChange,
  findProhibitedPrimaryPhrases,
  simplifyCustomerCopy,
} from "../app/(product)/truth/customerLanguage.mjs";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("the browser and generated language contracts share the v3 natural voice standard", () => {
  assert.equal(CUSTOMER_LANGUAGE_VERSION, "service-business-natural-voice-v3");
  assert.equal(
    simplifyCustomerCopy("Reach more eligible completed customers"),
    "Get more reviews from recent customers",
  );
  assert.equal(
    simplifyCustomerCopy("Possible benefit — more evidence needed"),
    "we need more information before estimating the result",
  );
  assert.equal(
    simplifyCustomerCopy("Likely benefit: strong"),
    "the saved information strongly supports this action",
  );
  assert.deepEqual(findProhibitedPrimaryPhrases("Open the deterministic summary"), [
    "deterministic summary",
  ]);
  assert.equal(
    simplifyCustomerCopy("Open the deterministic summary", { fallback: "Open the saved plan" }),
    "Open the saved explanation",
  );
  assert.equal(
    simplifyCustomerCopy("Measure the share of eligible customers receiving a request."),
    "Count how many recent customers were asked for a review.",
  );
  assert.equal(
    simplifyCustomerCopy("Find missed service-completion touchpoints."),
    "Find missed follow-ups after a job is finished.",
  );
  assert.equal(
    simplifyCustomerCopy("Choose compliant post-service request moments."),
    "Choose times after a job when Google allows you to ask for a review.",
  );
  assert.equal(
    simplifyCustomerCopy("Add approved requests without incentives or review gating."),
    "Ask recent customers for reviews without rewards or filtering who gets asked.",
  );
  assert.deepEqual(
    findProhibitedPrimaryPhrases("Unlock actionable insights with an AI-powered workflow"),
    ["actionable insights", "ai-powered", "unlock"],
  );
  assert.equal(
    simplifyCustomerCopy("Open the supporting data for measured demand"),
    "Open the details behind this result for estimated monthly searches",
  );
});

test("first impressions state the business outcome without self-conscious product language", () => {
  const homeSource = source("../app/page.jsx");
  const loginSource = source("../app/login/page.jsx");

  assert.match(homeSource, /Know how your business is showing up on Google/);
  assert.match(homeSource, /See which searches help people find you/);
  assert.match(loginSource, /See what changed on Google, what needs attention, and what to work on next/);
  assert.doesNotMatch(loginSource, /httpOnly|JS-accessible|auth tokens/);
  assert.deepEqual(findProhibitedPrimaryPhrases(homeSource), []);
  assert.deepEqual(findProhibitedPrimaryPhrases(loginSource), []);
});

test("change language combines words, direction, and consistent meaning", () => {
  assert.equal(describeChange("positive"), "Improving");
  assert.equal(describeChange("negative"), "Slipping");
  assert.equal(describeChange("neutral"), "No clear change");
  assert.deepEqual(customerCopyStats("Fix this page. Check the result next week."), {
    words: 8,
    sentences: 2,
    averageWordsPerSentence: 4,
  });

  const trendSource = source("../app/(product)/components/TrendIndicator.tsx");
  assert.match(trendSource, /arrow-up/);
  assert.match(trendSource, /arrow-down/);
  assert.match(trendSource, /No clear change/);
  assert.match(trendSource, /aria-label/);
});

test("every customer route has an original navigation and page-heading icon", () => {
  const navSource = source("../app/(product)/nav.config.ts");
  const introSource = source("../app/(product)/components/ProductPageIntro.tsx");
  const iconSource = source("../app/(product)/components/ProductIcon.tsx");
  const routeIcons = [
    "overview",
    "rankings",
    "keyword-research",
    "local-search",
    "website-health",
    "next-steps",
    "reports",
    "connections",
    "locations",
    "search-value",
    "ai-search",
    "competitors",
    "content",
    "listings",
    "reviews",
    "activity",
    "help",
  ];

  for (const icon of routeIcons) {
    assert.match(navSource, new RegExp(`icon: "${icon}"`));
    assert.match(iconSource, new RegExp(`case "${icon}"`));
  }
  assert.match(introSource, /PAGE_ICON_BY_PATH/);
  assert.match(introSource, /<ProductIcon name=\{icon\}/);
  assert.doesNotMatch(introSource, /lg:grid-cols/);
});

test("shared visuals expose scope, legend, details, and honest data states", () => {
  const chartSource = source("../app/(product)/components/ChartCard.tsx");
  const stateSource = source("../app/(product)/components/DataState.tsx");
  const metricSource = source("../app/(product)/components/MetricStrip.tsx");
  const systemSource = source("../app/(product)/components/visualSystem.ts");

  assert.match(chartSource, /ChartScope/);
  assert.match(chartSource, /ScopeBar/);
  assert.match(chartSource, /legend/);
  assert.match(chartSource, /DetailsDisclosure/);
  assert.match(chartSource, /DataState/);
  for (const state of ["loading", "empty", "single-point", "partial", "stale", "unsupported", "error"]) {
    assert.match(stateSource, new RegExp(`"${state}"`));
  }
  assert.match(metricSource, /TrendIndicator/);
  assert.match(systemSource, /NEXT_PUBLIC_CUSTOMER_VISUAL_SYSTEM_V2_ENABLED/);
  assert.match(systemSource, /optional-technical-data/);
});

test("shared primary UI copy does not contain prohibited customer labels", () => {
  const sharedFiles = [
    "../app/(product)/nav.config.ts",
    "../app/(product)/components/ProductPageIntro.tsx",
    "../app/(product)/components/SidebarNav.tsx",
    "../app/(product)/components/TopBar.tsx",
    "../app/(product)/components/ActionDrawer.tsx",
    "../app/(product)/components/InsightCard.tsx",
    "../app/(product)/components/KpiCard.tsx",
    "../app/(product)/components/ChartCard.tsx",
    "../app/(product)/opportunities/page.tsx",
  ];

  for (const path of sharedFiles) {
    assert.deepEqual(findProhibitedPrimaryPhrases(source(path)), [], path);
  }
});
