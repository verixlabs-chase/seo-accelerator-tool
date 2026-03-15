import test from "node:test";
import assert from "node:assert/strict";

import {
  getCrawlWorkflowState,
  getReportWorkflowState as getDashboardReportWorkflowState,
} from "../app/(product)/truth/dashboardTruth.mjs";
import {
  getDeliveryWorkflowState,
  getReportWorkflowState,
  getScheduleWorkflowState,
} from "../app/(product)/truth/reportsTruth.mjs";
import {
  getExecutionStateSummary,
  getRecommendationStateSummary,
  getSetupBlockerSummary,
} from "../app/(product)/truth/opportunitiesTruth.mjs";
import {
  getStepThreeSummary,
  getTaskStatusMeaning,
  summarizeTaskCounts,
} from "../app/(product)/truth/onboardingTruth.mjs";

const formatRelativeTime = () => "2 hours ago";

test("dashboard truth state marks failed crawl as needs attention with remediation", () => {
  const state = getCrawlWorkflowState(
    { status: "failed", crawl_type: "deep" },
    { id: "1", name: "Acme" },
    formatRelativeTime,
  );

  assert.equal(state.status, "Needs attention");
  assert.match(state.detail, /failed or stopped/i);
  assert.match(state.nextStep, /retry/i);
});

test("dashboard truth state marks generated report as action needed, not complete", () => {
  const state = getDashboardReportWorkflowState(
    { report_status: "generated", month_number: 2 },
    { id: "1", name: "Acme" },
  );

  assert.equal(state.status, "Action needed");
  assert.match(state.detail, /ready to review/i);
  assert.match(state.nextStep, /send/i);
});

test("dashboard truth state marks pending crawl as in progress, not complete", () => {
  const state = getCrawlWorkflowState(
    { status: "queued", crawl_type: "deep" },
    { id: "1", name: "Acme" },
    formatRelativeTime,
  );

  assert.equal(state.status, "In progress");
  assert.match(state.detail, /still be filling in/i);
  assert.match(state.nextStep, /wait/i);
});

test("reports truth state marks generated report as ready to send", () => {
  const state = getReportWorkflowState(
    { report_status: "generated", month_number: 3 },
    { id: "1", name: "Acme" },
  );

  assert.equal(state.status, "Ready to send");
  assert.match(state.detail, /ready for review/i);
  assert.match(state.nextStep, /send/i);
});

test("reports truth state marks failed report as needs attention", () => {
  const state = getReportWorkflowState(
    { report_status: "failed", month_number: 4 },
    { id: "1", name: "Acme" },
  );

  assert.equal(state.status, "Needs attention");
  assert.match(state.detail, /failed state|failed/i);
  assert.match(state.nextStep, /generate the report again/i);
});

test("reports truth state marks queued delivery as in progress", () => {
  const state = getDeliveryWorkflowState(
    {
      delivery_events: [
        { delivery_status: "queued", recipient: "client@example.com" },
      ],
    },
    { report_status: "generated", month_number: 3 },
  );

  assert.equal(state.status, "In progress");
  assert.match(state.detail, /not confirmed as sent/i);
  assert.match(state.nextStep, /wait/i);
});

test("reports truth state marks missing delivery events as action needed when report is not delivered", () => {
  const state = getDeliveryWorkflowState(
    { delivery_events: [] },
    { report_status: "generated", month_number: 3 },
  );

  assert.equal(state.status, "Action needed");
  assert.match(state.detail, /no delivery has been recorded/i);
  assert.match(state.nextStep, /confirm the recipient/i);
});

test("reports truth state marks exhausted scheduler retries as needs attention", () => {
  const state = getScheduleWorkflowState(
    { last_status: "max_retries_exceeded", next_run_at: "2026-03-15T10:00:00Z" },
    { id: "1", name: "Acme" },
    formatRelativeTime,
  );

  assert.equal(state.status, "Needs attention");
  assert.match(state.detail, /exhausted/i);
  assert.match(state.nextStep, /re-save/i);
});

test("opportunities truth state distinguishes approved recommendation from execution completion", () => {
  const state = getRecommendationStateSummary("APPROVED");

  assert.equal(state.status, "Chosen next");
  assert.match(state.detail, /not been queued for execution yet/i);
  assert.match(state.nextStep, /queue/i);
});

test("opportunities truth state marks generated recommendation as recommended, not approved", () => {
  const state = getRecommendationStateSummary("GENERATED");

  assert.equal(state.status, "Recommended");
  assert.match(state.detail, /nobody has reviewed it yet/i);
  assert.match(state.nextStep, /mark it as reviewed/i);
});

test("opportunities truth state marks scheduled execution as queued to run", () => {
  const state = getExecutionStateSummary(
    { status: "scheduled", execution_type: "fix_missing_title" },
    {
      getMutationCount: () => 0,
      canRollbackExecution: () => false,
    },
  );

  assert.equal(state.status, "Queued to run");
  assert.match(state.detail, /waiting in the queue/i);
  assert.match(state.nextStep, /run now|dry run/i);
});

test("opportunities truth state marks completed execution with rollback guidance when mutations exist", () => {
  const state = getExecutionStateSummary(
    { status: "completed", execution_type: "fix_missing_title" },
    {
      getMutationCount: () => 2,
      canRollbackExecution: () => true,
    },
  );

  assert.equal(state.status, "Completed");
  assert.match(state.detail, /recorded 2 tracked changes/i);
  assert.match(state.nextStep, /rollback/i);
});

test("opportunities truth state marks failed execution as failed with remediation", () => {
  const state = getExecutionStateSummary(
    {
      status: "failed",
      execution_type: "fix_missing_title",
      last_error: "provider_timeout",
    },
    {
      getMutationCount: () => 0,
      canRollbackExecution: () => false,
    },
  );

  assert.equal(state.status, "Failed");
  assert.match(state.detail, /provider timeout/i);
  assert.match(state.nextStep, /retry/i);
});

test("opportunities truth state marks blocked wordpress execution as blocked with setup guidance", () => {
  const state = getSetupBlockerSummary(
    { execution_type: "fix_missing_title" },
    { missing_requirements: ["Install plugin"] },
    "WordPress execution setup is incomplete.",
    (type) => type === "fix_missing_title",
  );

  assert.equal(state.status, "Blocked");
  assert.match(state.detail, /incomplete/i);
  assert.match(state.nextStep, /missing setup requirements/i);
});

test("onboarding truth state summarizes queued setup before completion", () => {
  const tasks = [
    { id: "campaign", status: "done" },
    { id: "crawl", status: "pending" },
    { id: "keyword", status: "pending" },
    { id: "ranking", status: "pending" },
  ];

  const summary = getStepThreeSummary(tasks, false);

  assert.equal(summary.title, "Setup is still in progress");
  assert.match(summary.body, /queued to start next/i);
  assert.match(summary.next, /stay on this screen/i);
});

test("onboarding truth state summarizes partial success as needs attention", () => {
  const tasks = [
    { id: "campaign", status: "done" },
    { id: "crawl", status: "done" },
    { id: "keyword", status: "error" },
    { id: "ranking", status: "pending" },
  ];

  const counts = summarizeTaskCounts(tasks);
  const summary = getStepThreeSummary(tasks, true);

  assert.equal(counts.hasSetupIssues, true);
  assert.equal(summary.title, "Setup finished with issues");
  assert.match(summary.body, /needs attention/i);
  assert.match(summary.next, /review the workflow status/i);
});

test("onboarding truth state summarizes successful setup without false completion of results", () => {
  const tasks = [
    { id: "campaign", status: "done" },
    { id: "crawl", status: "done" },
    { id: "keyword", status: "done" },
    { id: "ranking", status: "done" },
  ];

  const summary = getStepThreeSummary(tasks, true);

  assert.equal(summary.title, "Setup finished successfully");
  assert.match(summary.body, /first checks are now running in the background/i);
  assert.doesNotMatch(summary.body, /results are complete/i);
});

test("onboarding task meaning keeps queued and failed states distinct", () => {
  assert.match(getTaskStatusMeaning("pending"), /queued/i);
  assert.match(getTaskStatusMeaning("error"), /needs attention/i);
});
