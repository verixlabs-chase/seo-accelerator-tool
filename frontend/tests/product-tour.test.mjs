import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  PRODUCT_TOUR_TTL_MS,
  createProductTourState,
  finishProductTour,
  productTourStorageKey,
  readProductTourState,
  requestProductTour,
} from "../app/(product)/truth/productTour.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("product tour progress is scoped, resumable, and expires", () => {
  const storage = memoryStorage();
  const now = 1_900_000_000_000;
  const started = requestProductTour(storage, "org-a", "multi", now);

  assert.equal(started.persona, "multi");
  assert.equal(started.stepIndex, 0);
  assert.equal(started.expiresAt, now + PRODUCT_TOUR_TTL_MS);
  assert.equal(readProductTourState(storage, "org-b", now), null);

  const resumed = readProductTourState(storage, "org-a", now + 1_000);
  assert.equal(resumed.active, true);
  assert.equal(resumed.persona, "multi");

  const finished = finishProductTour(storage, "org-a", resumed, now + 2_000);
  assert.equal(finished.active, false);
  assert.equal(finished.completedAt, now + 2_000);
  assert.equal(readProductTourState(storage, "org-a", now + PRODUCT_TOUR_TTL_MS + 2_001), null);
});

test("product tour storage never includes authentication or provider secrets", () => {
  const state = JSON.stringify(createProductTourState("solo", 1_900_000_000_000));
  assert.doesNotMatch(state, /password|access_token|refresh_token|api_key|credential/i);
  assert.match(productTourStorageKey("tenant-a"), /tenant-a/);
});

test("short tours cover one business, multi-location, and team work", () => {
  const component = source("../app/(product)/components/GuidedProductTour.tsx");
  const layout = source("../app/(product)/layout.tsx");
  const help = source("../app/(product)/help/page.tsx");
  const setup = source("../app/(product)/components/OnboardingWizard.tsx");
  const connections = source("../app/(product)/settings/page.tsx");

  assert.match(component, /solo:\s*\[/);
  assert.match(component, /multi:\s*\[/);
  assert.match(component, /team:\s*\[/);
  assert.equal((component.match(/path: "\//g) || []).length, 12);
  assert.match(component, />\s*Close\s*</);
  assert.match(component, /tour\.started/);
  assert.match(component, /tour\.step_viewed/);
  assert.match(component, /tour\.completed/);
  assert.match(layout, /<GuidedProductTour \/>/);
  assert.match(help, /Start quick tour/);
  assert.match(setup, /requestProductTour/);
  assert.match(connections, /requestProductTour/);
});
