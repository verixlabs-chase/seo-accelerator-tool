import test from "node:test";
import assert from "node:assert/strict";

import {
  getCanonicalActionKey,
  getRecommendationPortfolio,
} from "../app/(product)/truth/actionPlan.mjs";

function recommendation(overrides = {}) {
  return {
    id: overrides.id || crypto.randomUUID(),
    recommendation_type: "technical.reduce_render_blocking",
    confidence_score: 0.8,
    risk_tier: 2,
    status: "GENERATED",
    created_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

test("action portfolio keeps one first action and exposes several next actions", () => {
  const result = getRecommendationPortfolio([
    recommendation({ id: "medium", recommendation_type: "content.refresh", risk_tier: 2 }),
    recommendation({ id: "first", recommendation_type: "technical.speed", risk_tier: 4 }),
    recommendation({ id: "next-1", recommendation_type: "local.reviews", risk_tier: 3 }),
    recommendation({ id: "next-2", recommendation_type: "organic.snippet", risk_tier: 2 }),
  ]);

  assert.equal(result.primary.id, "first");
  assert.deepEqual(result.next.map((item) => item.id), ["next-1", "medium", "next-2"]);
  assert.equal(result.later.length, 0);
});

test("action portfolio removes archived artifacts and duplicate canonical actions", () => {
  const result = getRecommendationPortfolio([
    recommendation({
      id: "new-speed",
      recommendation_type: "policy::cwv::technical.speed",
      action_plan: { action_id: "technical.speed" },
      confidence_score: 0.9,
    }),
    recommendation({
      id: "old-speed",
      recommendation_type: "policy::legacy::technical.speed",
      action_plan: { action_id: "technical.speed" },
      confidence_score: 0.7,
    }),
    recommendation({ id: "archived", recommendation_type: "local.reviews", status: "ARCHIVED" }),
    recommendation({ id: "artifact", recommendation_type: "strategy_bundle_record" }),
  ]);

  assert.deepEqual(result.ordered.map((item) => item.id), ["new-speed"]);
  assert.equal(getCanonicalActionKey(result.primary), "technical.speed");
});

test("action portfolio does not create filler when evidence supports only one action", () => {
  const result = getRecommendationPortfolio([
    recommendation({ id: "only-action" }),
  ]);

  assert.equal(result.primary.id, "only-action");
  assert.deepEqual(result.next, []);
  assert.deepEqual(result.later, []);
});
