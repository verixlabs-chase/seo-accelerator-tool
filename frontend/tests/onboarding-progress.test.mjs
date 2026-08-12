import test from "node:test";
import assert from "node:assert/strict";

import {
  MAX_PROGRESS_AGE_MS,
  clearOnboardingProgress,
  getOnboardingProgressKey,
  hasOnboardingProgress,
  loadOnboardingProgress,
  saveOnboardingProgress,
} from "../app/(product)/truth/onboardingProgress.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

const progress = {
  step: 3,
  businessName: "Junk Magicians",
  websiteUrl: "junkmagiciansnv.com",
  businessLocationId: "location-1",
  campaignId: "campaign-1",
  campaignDomain: "junkmagiciansnv.com",
  servicesInput: "Junk removal",
  serviceAreasInput: "Reno, NV",
  primaryService: "Junk removal",
  rankingArea: "Reno, NV",
  scanStarted: true,
  scanDone: false,
  setupTasks: [
    { id: "location", title: "Location", description: "", status: "done" },
    { id: "campaign", title: "Campaign", description: "", status: "done" },
    { id: "business-profile", title: "Profile", description: "", status: "done" },
    { id: "crawl", title: "Scan", description: "", status: "running" },
    { id: "keyword", title: "Search", description: "", status: "done" },
    { id: "ranking", title: "Ranking", description: "", status: "pending" },
  ],
};

test("setup progress survives navigation without storing authentication secrets", () => {
  const storage = memoryStorage();
  const now = 1_800_000_000_000;

  assert.equal(saveOnboardingProgress(storage, "org-1", progress, now), true);
  assert.equal(hasOnboardingProgress(storage, "org-1", now + 1000), true);

  const restored = loadOnboardingProgress(storage, "org-1", now + 1000);
  assert.equal(restored.step, 3);
  assert.equal(restored.campaignId, "campaign-1");
  assert.equal(restored.setupTasks.find((task) => task.id === "keyword").status, "done");
  assert.equal(restored.setupTasks.find((task) => task.id === "crawl").status, "error");
  assert.equal(restored.scanDone, true);

  const raw = storage.getItem(getOnboardingProgressKey("org-1"));
  assert.doesNotMatch(raw, /password|access_token|refresh_token|api_key/i);
});

test("setup progress is isolated by organization and expires", () => {
  const storage = memoryStorage();
  const now = 1_800_000_000_000;
  saveOnboardingProgress(storage, "org-1", progress, now);

  assert.equal(loadOnboardingProgress(storage, "org-2", now), null);
  assert.equal(
    loadOnboardingProgress(storage, "org-1", now + MAX_PROGRESS_AGE_MS + 1),
    null,
  );
});

test("completed setup can remove its saved progress", () => {
  const storage = memoryStorage();
  saveOnboardingProgress(storage, "org-1", progress);
  clearOnboardingProgress(storage, "org-1");
  assert.equal(hasOnboardingProgress(storage, "org-1"), false);
});
