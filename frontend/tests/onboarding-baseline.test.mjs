import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { getStepThreeSummary, getTaskRecoveryGuidance } from "../app/(product)/truth/onboardingTruth.mjs";


const wizard = readFileSync(
  new URL("../app/(product)/components/OnboardingWizard.tsx", import.meta.url),
  "utf8",
);
const reportsPage = readFileSync(
  new URL("../app/(product)/reports/page.tsx", import.meta.url),
  "utf8",
);


test("guided setup requires an immutable baseline before completion", () => {
  assert.match(wizard, /id: "baseline"/);
  assert.match(wizard, /Create your baseline analysis and first diagnosis/);
  assert.match(wizard, /\/onboarding\/baseline\//);
  assert.match(wizard, /if \(!baselineComplete\) return/);
  assert.match(wizard, /completion_satisfied/);
  assert.match(wizard, /Open dashboard while baseline finishes/);
  assert.match(wizard, /mandatory baseline finishes/);
});


test("baseline copy explains the evidence and missing-data contract", () => {
  assert.match(wizard, /website, organic visibility, traffic, and performance evidence/);
  assert.match(wizard, /Missing optional connections are labeled—not scored as zero/);
  assert.match(wizard, /immutable starting point/);
  assert.match(wizard, /Review baseline report/);
  assert.doesNotMatch(wizard, /guarantee(?:d|s)? rankings/i);
  assert.match(reportsPage, /Onboarding baseline/);
  assert.match(reportsPage, /immutable first report preserves the starting issues/);
  assert.match(reportsPage, /insightos-onboarding-baseline/);
});


test("baseline progress and recovery remain honest", () => {
  const summary = getStepThreeSummary(
    [
      { id: "crawl", status: "done" },
      { id: "ranking", status: "done" },
      { id: "baseline", status: "running" },
    ],
    true,
  );
  assert.equal(summary.title, "Setup and baseline analysis are still in progress");
  assert.match(summary.body, /mandatory first diagnosis/i);
  assert.match(summary.next, /open the dashboard/i);

  const recovery = getTaskRecoveryGuidance({ id: "baseline", status: "error" });
  assert.match(recovery.missing, /baseline report/i);
  assert.match(recovery.recovery, /retry the baseline analysis/i);
});
