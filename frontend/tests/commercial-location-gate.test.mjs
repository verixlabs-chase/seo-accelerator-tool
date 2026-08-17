import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  canActivateAnotherLocation,
  isLocationAllowanceEnforced,
} from "../app/(product)/truth/locationAllowanceTruth.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8");

const locations = source("../app/(product)/locations/page.tsx");
const onboarding = source("../app/(product)/components/OnboardingWizard.tsx");
const planNotice = source("../app/(product)/components/PlanGateNotice.tsx");
const settings = source("../app/(product)/settings/page.tsx");
const platformApi = source("../app/platform/api.js");

test("locations fail closed while plan allowance is unknown and keep saved locations readable", () => {
  assert.match(locations, /platformApi\("\/usage\/credits"/);
  assert.match(locations, /locationAllowanceUnavailable \|\|\s*!canActivateLocation/);
  assert.match(locations, /Existing locations are not affected/);
  assert.match(locations, /Check plan again/);
  assert.doesNotMatch(locations, /setHierarchy\(null\).*locationAllowanceError/s);
});

test("location create and reactivation use the same server-backed allowance gate", () => {
  assert.match(locations, /active_location_allowance_exhausted/);
  assert.match(locations, /canActivateAnotherLocation\(locationAllowance\)/);
  assert.match(source("../app/(product)/truth/locationAllowanceTruth.mjs"), /location_allowance_enforced === true/);
  assert.match(locations, /isLocationAllowanceEnforced\(locationAllowance\)/);
  assert.match(onboarding, /isLocationAllowanceEnforced\(locationAllowance\)/);
  assert.match(locations, /body: JSON\.stringify\(\{ status: "active" \}\)/);
  assert.match(locations, /Review plan to turn on/);
  assert.match(locations, /body: JSON\.stringify\(\{ status: "archived" \}\)/);

  const createRequest = locations.indexOf("/business-locations`");
  const clearName = locations.indexOf('setLocationName("")', createRequest);
  assert.ok(createRequest >= 0 && clearName > createRequest, "form values clear only after create returns");
});

test("location capacity stays observational until the server explicitly enables enforcement", () => {
  const oldBackend = {
    plan: { remaining_locations: 0, can_activate_location: false },
  };
  const observing = {
    plan: {
      location_allowance_enforced: false,
      remaining_locations: 0,
      can_activate_location: false,
    },
  };
  const enforcedAtCapacity = {
    plan: {
      location_allowance_enforced: true,
      remaining_locations: 0,
      can_activate_location: false,
    },
  };
  const enforcedWithRoom = {
    plan: {
      location_allowance_enforced: true,
      remaining_locations: 1,
      can_activate_location: true,
    },
  };

  assert.equal(isLocationAllowanceEnforced(oldBackend), false);
  assert.equal(canActivateAnotherLocation(oldBackend), true);
  assert.equal(canActivateAnotherLocation(observing), true);
  assert.equal(canActivateAnotherLocation(enforcedAtCapacity), false);
  assert.equal(canActivateAnotherLocation(enforcedWithRoom), true);
});

test("the plan handoff is contextual, role-aware, and reuses Settings billing", () => {
  assert.match(planNotice, /Your \$\{plan\.name\} plan includes/);
  assert.match(planNotice, /Everything already saved stays available/);
  assert.match(planNotice, /Ask the workspace owner to review the plan/);
  assert.match(planNotice, /\/settings#plan-and-billing/);
  assert.match(planNotice, /`\$\{upgrade\.plan_name\} includes up to 10 locations`/);
  assert.match(planNotice, /reasons\.slice\(0, 3\)/);
  assert.match(planNotice, /Ask about adding locations/);
  assert.match(settings, /id="plan-and-billing"/);
  assert.doesNotMatch(planNotice, /Stripe|provider|margin|tier_version|allowance_source/i);
});

test("guided setup reuses a saved partial location before creating another", () => {
  assert.match(onboarding, /business-locations`,\s*\{ method: "GET" \}/);
  assert.match(onboarding, /activeLocations\.length === 1/);
  assert.match(onboarding, /setBusinessLocationId\(\(current\) => current \|\| recovered\.id\)/);
  assert.match(onboarding, /Continue a saved location/);
  assert.match(onboarding, /without creating a duplicate/);
  assert.match(onboarding, /needsNewLocation && !canCreateLocation/);

  const existingCheck = onboarding.indexOf("if (!activeLocationId)");
  const createRequest = onboarding.indexOf("/business-locations`", existingCheck);
  assert.ok(existingCheck >= 0 && createRequest > existingCheck);
});

test("structured API errors preserve the stable allowance reason for race recovery", () => {
  assert.match(platformApi, /export class PlatformApiError extends Error/);
  assert.match(platformApi, /this\.reasonCode = this\.details\?\.reason_code \|\| null/);
  assert.match(locations, /err instanceof PlatformApiError/);
  assert.match(onboarding, /err instanceof PlatformApiError/);
  assert.match(onboarding, /Your setup answers are still here/);
});
