import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  getActionTrack,
  getActionTrackGroups,
  getCanonicalActionKey,
  getPrimaryMeasurement,
  getRecommendationPortfolio,
  getRecommendationRoutines,
  getWorkProgress,
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

test("action routines group persisted work without creating fake assignments", () => {
  const result = getRecommendationRoutines([
    recommendation({
      id: "today",
      action_plan: { action_id: "technical.speed", work_item: { cadence: "daily" } },
    }),
    recommendation({
      id: "week",
      action_plan: { action_id: "local.reviews", work_item: { cadence: "weekly" } },
    }),
    recommendation({
      id: "month",
      action_plan: { action_id: "content.plan", work_item: { cadence: "monthly" } },
    }),
    recommendation({ id: "unsupported", recommendation_type: "heuristic.only" }),
  ]);

  assert.deepEqual(result.daily.map((item) => item.id), ["today"]);
  assert.deepEqual(result.weekly.map((item) => item.id), ["week"]);
  assert.deepEqual(result.monthly.map((item) => item.id), ["month"]);
  assert.deepEqual(result.later.map((item) => item.id), ["unsupported"]);
});

test("work progress uses required checklist steps", () => {
  const progress = getWorkProgress({
    action_plan: {
      work_item: {
        progress: { completed_required: 2, required_total: 3 },
      },
    },
  });

  assert.deepEqual(progress, {
    completed: 2,
    total: 3,
    label: "2 of 3 steps done",
    percent: 67,
  });
});

test("actions are separated into website and Google profile work", () => {
  const website = recommendation({
    id: "website",
    action_plan: {
      action_id: "technical.speed",
      category: "technical",
      primary_metric_id: "cwv.lcp",
      measurement_track: "website",
    },
  });
  const profile = recommendation({
    id: "profile",
    action_plan: {
      action_id: "reputation.reviews",
      category: "reputation",
      primary_metric_id: "local.review_velocity_30d",
    },
  });

  const groups = getActionTrackGroups([website, profile]);

  assert.equal(getActionTrack(website), "website");
  assert.equal(getActionTrack(profile), "google_business_profile");
  assert.deepEqual(groups.website.map((item) => item.id), ["website"]);
  assert.deepEqual(groups.google_business_profile.map((item) => item.id), ["profile"]);
});

test("primary measurement stays tied to the governed main metric", () => {
  const item = recommendation({
    action_plan: {
      action_id: "technical.speed",
      primary_metric_id: "cwv.lcp",
      work_item: {
        measurement: {
          result_classification: "improved",
          observation_due_at: "2026-09-01T00:00:00Z",
          baseline_metrics: [
            { metric_id: "cwv.lcp", value: 4200, status: "available" },
            { metric_id: "organic.impressions", value: 100, status: "available" },
          ],
          outcome_metrics: [
            { metric_id: "organic.impressions", value: 120, status: "available" },
            { metric_id: "cwv.lcp", value: 2400, status: "available" },
          ],
        },
      },
    },
  });

  const primary = getPrimaryMeasurement(item);

  assert.equal(primary.metricId, "cwv.lcp");
  assert.equal(primary.baseline.value, 4200);
  assert.equal(primary.outcome.value, 2400);
  assert.equal(primary.resultClassification, "improved");
});

test("next steps separates finished work from a measured result", () => {
  const pageSource = readFileSync(
    fileURLToPath(new URL("../app/(product)/opportunities/page.tsx", import.meta.url)),
    "utf8",
  );

  assert.match(pageSource, /Measured result/);
  assert.match(pageSource, /Improve your website/);
  assert.match(pageSource, /Improve your Google Business Profile/);
  assert.match(pageSource, /How we&apos;ll know this helped/);
  assert.match(pageSource, /The result is about the same/);
  assert.match(pageSource, /The measurement got worse/);
  assert.match(pageSource, /Finishing a step records the work, but it does not claim the result improved/);
  assert.match(pageSource, /Work recorded — waiting for results/);
  assert.match(pageSource, /Check results now/);
  assert.match(pageSource, /There is not enough follow-up data/);
  assert.match(pageSource, /Possible improvement — not a promise/);
  assert.match(pageSource, /Conservative/);
  assert.match(pageSource, /Expected/);
  assert.match(pageSource, /Optimistic/);
  assert.match(pageSource, /It does not predict rankings, visits, leads, or revenue/);
  assert.match(pageSource, /data-forecast-visual/);
  assert.match(pageSource, /Ask about this location/);
  assert.match(pageSource, /Get an answer from the saved facts/);
  assert.match(pageSource, /Answers cannot change your website or add new actions/);
  assert.match(pageSource, /\/intelligence\/questions/);
  assert.match(pageSource, /See the saved information behind this answer/);
  assert.match(pageSource, /What this answer cannot confirm/);
  assert.match(pageSource, /Draft help for this action/);
  assert.match(pageSource, /Review every draft\s+before using it/);
  assert.match(pageSource, /Draft only - nothing is published/);
  assert.match(pageSource, /\/intelligence\/drafts/);
  assert.match(pageSource, /Nothing was changed or published/);
  assert.match(pageSource, /\/intelligence\/outcome-learning/);
  assert.match(pageSource, /What the completed work is teaching us/);
  assert.match(pageSource, /Results checked/);
  assert.match(pageSource, /Why InsightOS waits before learning/);
  assert.match(pageSource, /A person must review enough comparable examples/);
  assert.match(pageSource, /No automatic rule changes/);
});
