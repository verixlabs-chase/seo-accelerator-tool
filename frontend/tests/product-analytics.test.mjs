import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function read(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

const analyticsClient = read("../app/lib/productAnalytics.ts");
const locationContext = read("../app/(product)/components/LocationContext.tsx");
const onboarding = read("../app/(product)/components/OnboardingWizard.tsx");
const opportunities = read("../app/(product)/opportunities/page.tsx");
const platformValue = read("../app/platform/value/page.jsx");

test("the first customer journey uses explicit governed product events", () => {
  assert.match(analyticsClient, /\/product-analytics\/events/);
  assert.match(locationContext, /workspace\.location_switched/);
  assert.match(onboarding, /onboarding\.started/);
  assert.match(onboarding, /onboarding\.completed/);
  assert.match(opportunities, /recommendation\.viewed/);
  assert.match(opportunities, /forecast\.viewed/);
  assert.doesNotMatch(opportunities, /value\.first_verified_insight/);
  assert.doesNotMatch(opportunities, /action\.step_completed/);
  assert.doesNotMatch(opportunities, /action\.outcome_available/);
});

test("customer feedback stays short and structured", () => {
  assert.match(analyticsClient, /\/product-analytics\/feedback/);
  assert.match(opportunities, /Is this recommended action useful\?/);
  assert.match(opportunities, /Does this possible result feel believable\?/);
  assert.doesNotMatch(opportunities, /feedback.*textarea/is);
});

test("platform owners can see aggregate activation and measurement coverage", () => {
  assert.match(platformValue, /Activation &amp; Customer Value/);
  assert.match(platformValue, /Reached first value/);
  assert.match(platformValue, /Returned for more value/);
  assert.match(platformValue, /Instrumentation coverage/);
  assert.match(platformValue, /Synthetic activity.*excluded/);
});
