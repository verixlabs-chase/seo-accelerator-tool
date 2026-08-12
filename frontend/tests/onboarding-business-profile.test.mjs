import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const wizardSource = readFileSync(
  new URL("../app/(product)/components/OnboardingWizard.tsx", import.meta.url),
  "utf8",
);
const dashboardSource = readFileSync(
  new URL("../app/(product)/dashboard/page.tsx", import.meta.url),
  "utf8",
);
const settingsSource = readFileSync(
  new URL("../app/(product)/settings/page.tsx", import.meta.url),
  "utf8",
);

test("guided setup creates a real location before its campaign", () => {
  const locationRequest = wizardSource.indexOf("/business-locations");
  const campaignRequest = wizardSource.indexOf('platformApi("/campaigns"');

  assert.ok(locationRequest >= 0, "expected the business-location request");
  assert.ok(campaignRequest > locationRequest, "campaign must be created after its location");
  assert.match(wizardSource, /business_location_id: activeLocationId/);
});

test("guided setup saves confirmed services and markets before starting checks", () => {
  const servicesRequest = wizardSource.indexOf('platformApi("/business-services"');
  const areasRequest = wizardSource.indexOf('platformApi("/business-service-areas"');
  const crawlRequest = wizardSource.indexOf('platformApi("/crawl/schedule"');

  assert.ok(servicesRequest >= 0);
  assert.ok(areasRequest > servicesRequest);
  assert.ok(crawlRequest > areasRequest);
  assert.match(wizardSource, /Services customers can hire you for/);
  assert.match(wizardSource, /Cities, counties, or ZIP codes you serve/);
  assert.match(wizardSource, /review them before they affect your search ideas/i);
});

test("guided setup explains and retries blocked first checks", () => {
  assert.match(wizardSource, /What is missing:/);
  assert.match(wizardSource, /Who acts:/);
  assert.match(wizardSource, /How to recover:/);
  assert.match(wizardSource, /Retry unfinished checks/);
  assert.match(wizardSource, /support@verixlabs\.com/);
  assert.match(wizardSource, /Never send a password or API key/);
});

test("guided setup restores non-sensitive progress after navigation", () => {
  assert.match(wizardSource, /loadOnboardingProgress\(window\.localStorage/);
  assert.match(wizardSource, /saveOnboardingProgress\(window\.localStorage/);
  assert.match(wizardSource, /clearOnboardingProgress\(window\.localStorage/);
  assert.match(wizardSource, /saved on this device for 30 days/i);
  assert.match(wizardSource, /Your setup progress was restored/i);
  assert.match(dashboardSource, /hasOnboardingProgress\(window\.localStorage/);
});

test("guided setup continues through one ordered Google connection path", () => {
  assert.match(wizardSource, /Connect your Google data next/);
  assert.match(wizardSource, /\/settings\?setup=connections&campaign_id=/);
  assert.match(settingsSource, /Work from top to bottom/);
  assert.match(settingsSource, /Approve Google access/);
  assert.match(settingsSource, /Match each website to its location/);
  assert.match(settingsSource, /Match each Google business listing/);
  assert.match(settingsSource, /setup=connections&source=business-profile/);
});
