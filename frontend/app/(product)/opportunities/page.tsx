"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  ActionDrawer,
  AppShell,
  EmptyState,
  ExecutionTimeline,
  KpiCard,
  LoadingCard,
  OWNER_JOURNEY_V2_ENABLED,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type RuntimeTruth,
  type TimelineEntry,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi, platformApiFile } from "../../platform/api";
import {
  analyticsDayKey,
  submitProductFeedback,
  trackProductEvent,
  type ProductFeedbackInput,
} from "../../lib/productAnalytics";
import {
  getExecutionStateSummary,
  getRecommendationStateSummary,
  getSetupBlockerSummary,
} from "../truth/opportunitiesTruth.mjs";
import {
  buildRuntimeTruthSignal,
  pickPrimaryRuntimeTruth,
} from "../truth/runtimeTruth.mjs";
import {
  getActionTrackGroups,
  getPrimaryMeasurement,
  getRecommendationPortfolio,
  getRecommendationRoutines,
  getWorkProgress,
} from "../truth/actionPlan.mjs";
import { simplifyCustomerCopy } from "../truth/customerLanguage.mjs";
import { ProgressMilestones } from "./ProgressMilestones";

const EXECUTION_CONSOLE_ENABLED =
  process.env.NEXT_PUBLIC_EXECUTION_CONSOLE_ENABLED !== "false";
const WORDPRESS_EXECUTION_SETUP_UI_ENABLED =
  process.env.NEXT_PUBLIC_WORDPRESS_EXECUTION_SETUP_UI !== "false";
const ROUTINE_SECTIONS = [
  { key: "daily", title: "Today", summary: "Short or time-sensitive work" },
  { key: "weekly", title: "This week", summary: "The improvements to keep moving" },
  { key: "monthly", title: "This month", summary: "Larger projects and regular upkeep" },
] as const;

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
  setup_state?: string;
};

type ActionWorkStep = {
  id: string;
  step_key: string;
  position: number;
  instruction: string;
  required: boolean;
  status: "not_started" | "in_progress" | "done" | "skipped" | "blocked";
  blocker_reason?: string | null;
  evidence?: string[];
  completed_at?: string | null;
};

type ActionMeasurementMetric = {
  metric_id: string;
  display_name: string;
  unit: string;
  status: "available" | "insufficient_data";
  value?: number | null;
  baseline_value?: number | null;
  change?: number | null;
  comparison?: "improved" | "unchanged" | "worse" | "insufficient_data";
  source?: string | null;
  source_provider?: string | null;
  measured_at?: string | null;
  evidence_window_start?: string | null;
  evidence_window_end?: string | null;
  insufficient_reason?: string | null;
  insufficient_reasons?: string[];
};

type ActionMeasurement = {
  measurement_status: "baseline_ready" | "insufficient_baseline" | "waiting_for_results" | "measured";
  readiness: "work_in_progress" | "baseline_unavailable" | "waiting" | "ready_to_check" | "measured";
  outcome_status: "pending" | "helped" | "did_not_help" | "insufficient_data";
  result_classification?: "waiting_for_results" | "improved" | "about_the_same" | "worse" | "not_enough_information";
  measurement_track?: "website" | "google_business_profile";
  primary_metric_id?: string | null;
  measurement_contract?: {
    version?: string;
    track?: "website" | "google_business_profile";
    primary_metric_id?: string | null;
    target?: {
      direction?: "higher_is_better" | "lower_is_better" | null;
      target_value?: number | null;
    };
    observation?: { check_on_or_after?: string | null };
    result?: { classification?: string; measured_at?: string | null };
  };
  baseline_metrics: ActionMeasurementMetric[];
  baseline_available_count: number;
  outcome_metrics: ActionMeasurementMetric[];
  observation_window_days: number;
  observation_due_at?: string | null;
  baseline_captured_at: string;
  work_completed_at?: string | null;
  outcome_measured_at?: string | null;
};

type ActionForecastMetric = {
  metric_id: string;
  display_name: string;
  plain_language?: string;
  unit: string;
  direction: "higher_is_better" | "lower_is_better";
  current_value: number;
  target_value: number;
  conservative_value: number;
  expected_value: number;
  optimistic_value: number;
  range_low: number;
  range_high: number;
  confidence: "moderate";
};

type ActionForecastComparison = {
  metric_id: string;
  status: "within_range" | "outside_range" | "insufficient_data";
  position: "within_range" | "better_than_range" | "worse_than_range" | "unknown";
  observed_value?: number | null;
};

type ActionForecast = {
  forecast_status: "available" | "not_available";
  metric_forecasts: ActionForecastMetric[];
  assumptions: string[];
  unavailable_reasons: Array<{ code: string; metric_id?: string | null; message: string }>;
  data_quality: "strong" | "moderate" | "insufficient";
  model_version: string;
  observation_window_days: number;
  outcome_comparisons: ActionForecastComparison[];
  generated_at: string;
  promise: false;
  unknown_effects: string[];
};

type ActionWorkItem = {
  id: string;
  recommendation_id: string;
  action_id: string;
  cadence: "daily" | "weekly" | "monthly" | "later";
  period_key: string;
  timezone: string;
  due_at?: string | null;
  due_state: "due_now" | "upcoming" | "overdue" | "completed" | "snoozed" | "later" | "waiting_for_results" | "ready_to_measure";
  status: string;
  progress: {
    completed_required: number;
    required_total: number;
    completed_total: number;
    total: number;
  };
  next_step?: ActionWorkStep | null;
  steps: ActionWorkStep[];
  measurement?: ActionMeasurement | null;
  forecast?: ActionForecast | null;
};

type Recommendation = {
  id: string;
  recommendation_type?: string;
  rationale?: string;
  confidence?: number;
  confidence_score?: number;
  evidence?: string[];
  engine_source?: string;
  risk_tier?: number;
  status?: string;
  created_at?: string;
  action_plan?: {
    action_id: string;
    category: string;
    display_name: string;
    why_it_matters: string;
    steps: string[];
    risk_tier: number;
    effort: string;
    owner_role: string;
    dependencies: string[];
    success_metric_ids: string[];
    primary_metric_id?: string | null;
    measurement_track?: "website" | "google_business_profile";
    observation_window_days: number;
    lexicon_id: string;
    lexicon_version: string;
    work_item?: ActionWorkItem | null;
  } | null;
};

type IntelligenceEngineState = {
  activation_mode?: string;
  guidance_source?: string;
  orchestrator_recommendation_count?: number;
  heuristic_recommendation_count?: number;
  data_scope?: string;
  provider_checks_allowed?: boolean;
  mutation_scheduling_enabled?: boolean;
  mutation_execution_enabled?: boolean;
  operator_review_required?: boolean;
  learning_state?: string;
  cycle_schedule?: string;
  last_generated_at?: string | null;
};

type RecommendationSummary = {
  total_count?: number;
  counts_by_state?: Record<string, number>;
  counts_by_risk_tier?: Record<string, number>;
  average_confidence_score?: number;
  engine?: IntelligenceEngineState;
  truth?: RuntimeTruth;
};

type IntelligenceScoreResponse = {
  score_value?: number;
  latest_score?: {
    score_value?: number;
    captured_at?: string;
  };
  engine?: IntelligenceEngineState;
  truth?: RuntimeTruth;
};

type RecommendationListResponse = {
  items?: Recommendation[];
  engine?: IntelligenceEngineState;
  truth?: RuntimeTruth;
};

type RecommendationOutcome = {
  id: string;
  recommendation_id: string;
  recommendation_type?: string;
  recommendation_rationale?: string;
  recommendation_status?: string;
  engine_source?: string;
  measurement_kind?: string;
  metric_label?: string;
  metric_before?: number;
  metric_after?: number;
  delta?: number;
  direction?: string;
  measured_at?: string;
  causal_proof?: boolean;
};

type OutcomeHistoryResponse = {
  count?: number;
  summary?: {
    improved_count?: number;
    declined_count?: number;
    unchanged_count?: number;
    average_score_delta?: number;
    latest_measured_at?: string | null;
  };
  learning?: {
    state?: string;
    observations_recorded?: number;
    policy_updates_enabled?: boolean;
    causal_claims_allowed?: boolean;
    minimum_outcomes_before_review?: number;
  };
  items?: RecommendationOutcome[];
  truth?: RuntimeTruth;
};

type IntelligenceCycleResponse = {
  status?: string;
  created?: boolean;
  idempotent_replay?: boolean;
  result?: {
    recommendations_generated?: number;
    recommendations_selected_by_simulation?: number;
    executions_scheduled?: number;
    executions_completed?: number;
  };
  safety?: {
    provider_checks_allowed?: boolean;
    activation_mode?: string;
    mutation_scheduling_enabled?: boolean;
    mutation_execution_enabled?: boolean;
    executions_scheduled?: number;
    executions_completed?: number;
  };
};

type GovernedIntelligenceAction = {
  action_id: string;
  display_name: string;
  why_it_matters?: string;
  steps?: string[];
  risk_tier?: number;
  effort?: string;
  approval_required?: boolean;
};

type GovernedIntelligenceBrief = {
  id: string;
  status: "validated" | "fallback" | "rejected" | "failed";
  provider_state?: string;
  provider_name?: string;
  model_name?: string;
  output: {
    summary: string;
    why_now: string;
    selected_action_id?: string | null;
    daily_action_ids?: string[];
    daily_actions?: GovernedIntelligenceAction[];
    evidence_used?: string[];
    uncertainties?: string[];
    approval_required: boolean;
    selected_action?: GovernedIntelligenceAction | null;
  };
  created_at?: string;
};

type GovernedIntelligenceBriefResponse = {
  item?: GovernedIntelligenceBrief | null;
  runtime?: {
    backend?: string;
    model?: string;
    configured?: boolean;
    decision_authority?: string;
    ai_role?: string;
    automatic_execution?: boolean;
  };
  allowance?: {
    monthly_actions?: number;
    used?: number;
    remaining?: number;
  };
  idempotent_replay?: boolean;
};

type GovernedEvidenceDetail = {
  evidence_id: string;
  label: string;
  detail?: string | null;
  captured_at?: string | null;
};

type GovernedRelatedAction = {
  action_id: string;
  display_name?: string | null;
  why_it_matters?: string | null;
};

type GovernedEvidenceAnswer = {
  id: string;
  status: "validated" | "fallback" | "rejected" | "failed";
  provider_state?: string;
  output: {
    question: string;
    answer: string;
    answer_state:
      | "answered"
      | "not_enough_information"
      | "temporarily_unavailable";
    evidence_used?: string[];
    evidence_details?: GovernedEvidenceDetail[];
    related_action_ids?: string[];
    related_actions?: GovernedRelatedAction[];
    uncertainties?: string[];
  };
  created_at?: string;
};

type GovernedEvidenceAnswerResponse = {
  item?: GovernedEvidenceAnswer | null;
  items?: GovernedEvidenceAnswer[];
  runtime?: GovernedIntelligenceBriefResponse["runtime"];
  allowance?: GovernedIntelligenceBriefResponse["allowance"];
  idempotent_replay?: boolean;
};

type GovernedDraftType =
  | "search_result"
  | "review_request"
  | "review_response"
  | "page_outline";

type GovernedDraftTypeOption = {
  draft_type: GovernedDraftType;
  label: string;
  description?: string;
  title_label?: string;
  body_label?: string;
};

type GovernedDraftAction = {
  action_id: string;
  display_name?: string | null;
  why_it_matters?: string | null;
  draft_types: GovernedDraftTypeOption[];
};

type GovernedActionDraft = {
  id: string;
  status: "validated" | "fallback" | "rejected" | "failed";
  provider_state?: string;
  output: {
    action_id: string;
    draft_type: GovernedDraftType;
    draft_type_label?: string;
    draft_state:
      | "ready"
      | "not_enough_information"
      | "temporarily_unavailable";
    title: string;
    body: string;
    title_label?: string;
    body_label?: string;
    evidence_used?: string[];
    evidence_details?: GovernedEvidenceDetail[];
    uncertainties?: string[];
    approval_required: true;
  };
  created_at?: string;
};

type GovernedActionDraftResponse = {
  item?: GovernedActionDraft | null;
  items?: GovernedActionDraft[];
  available_actions?: GovernedDraftAction[];
  runtime?: GovernedIntelligenceBriefResponse["runtime"];
  allowance?: GovernedIntelligenceBriefResponse["allowance"];
  idempotent_replay?: boolean;
};

type ExecutionResult = {
  status?: string;
  notes?: string;
  message?: string;
  reason_code?: string;
  mutations?: unknown[];
  rolled_back_mutations?: unknown[];
  preview?: WordPressChangePreview;
  rollback_available?: boolean;
  recovery_action?: string;
  public_verification?: {
    passed: boolean;
    verified_at?: string;
    pages_checked: number;
    checks_total: number;
    checks_passed: number;
    checks_failed: number;
    rollback_available: boolean;
    results: Array<{
      mutation_id?: string;
      mutation_type?: string;
      target_url?: string;
      status?: string;
      passed: boolean;
      message: string;
    }>;
  };
};

type WordPressChangeVersion = {
  revision_id?: string;
  content_hash?: string;
};

type WordPressChangePreviewItem = {
  mutation_id?: string;
  mutation_type?: string;
  target_url?: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  expected_version?: WordPressChangeVersion;
  validation_checks?: Array<{ code?: string; passed?: boolean; message?: string }>;
  conflicts?: Array<{ code?: string; message?: string; recovery?: string }>;
  rollback_plan?: { available?: boolean; summary?: string };
};

type WordPressChangePreview = {
  id?: string;
  preview_hash: string;
  status: "ready" | "blocked" | "approved" | "superseded";
  affected_urls?: string[];
  mutation_count?: number;
  conflict_count?: number;
  changes?: WordPressChangePreviewItem[];
  conflicts?: Array<{ code?: string; message?: string; recovery?: string }>;
  rollback_summary?: string;
  created_at?: string;
};

type Execution = {
  id: string;
  recommendation_id: string;
  campaign_id: string;
  execution_type: string;
  execution_payload: string;
  idempotency_key: string;
  deterministic_hash: string;
  status: string;
  attempt_count: number;
  last_error?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  risk_score: number;
  risk_level?: string;
  scope_of_change: number;
  historical_success_rate: number;
  result_summary?: string | null;
  executed_at?: string | null;
  rolled_back_at?: string | null;
  created_at?: string;
  payload?: Record<string, unknown>;
  result?: ExecutionResult;
  mutation_count?: number;
};

type DryRunPreview = {
  executionId: string;
  result: ExecutionResult;
};


type WordPressExecutionSetup = {
  campaign_id: string;
  provider_name: string;
  mode: string;
  configured: boolean;
  execution_ready: boolean;
  blocked: boolean;
  health_state: string;
  credential_source: string;
  credential_mode: string;
  missing_fields: string[];
  missing_requirements: string[];
  plugin_version?: string | null;
  plugin_package?: {
    filename: string;
    version: string;
    sha256: string;
    size_bytes: number;
    file_count: number;
  };
  breaker_state?: string;
  last_error_code?: string | null;
  last_error_at?: string | null;
  last_success_at?: string | null;
  status_summary: string;
  disabled_reason?: string | null;
  pairing_pending?: boolean;
  pairing_expires_at?: string | null;
  content_item_count?: number;
  content_source_total_count?: number;
  content_inventory_truncated?: boolean;
  last_content_sync_at?: string | null;
};

type WordPressPairingDetails = {
  campaign_id: string;
  site_url: string;
  pairing_code: string;
  expires_at: string;
  replaces_existing_connection: boolean;
  instructions: string[];
};

type WordPressContentItem = {
  id: string;
  wp_post_id: number;
  post_type: string;
  publication_status: string;
  url: string;
  title: string;
  meta_title?: string | null;
  meta_description?: string | null;
  canonical_url?: string | null;
  headings: Array<{ level?: number; text?: string }>;
  internal_links: string[];
  schema_types: string[];
  schema_present: boolean;
  word_count: number;
  revision_id: string;
  modified_at?: string | null;
};

type WordPressContentInventory = {
  campaign_id: string;
  has_inventory: boolean;
  last_synced_at?: string | null;
  wordpress_version?: string | null;
  seo_plugins?: Array<{ name?: string; version?: string }>;
  truncated?: boolean;
  source_total_count?: number;
  summary: {
    pages_found: number;
    published: number;
    drafts: number;
    missing_description: number;
    with_schema: number;
    without_internal_links: number;
  };
  items: WordPressContentItem[];
  message?: string;
};

function toTitleCase(value?: string) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_:-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatRelativeTime(value?: string | null) {
  if (!value) {
    return "No recent update";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No recent update";
  }

  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const hours = Math.round(diffMs / 3600000);

  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(diffMs / 86400000);
  return formatter.format(days, "day");
}

function formatMeasurementValue(metric: { unit: string }, value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Not available";
  }
  const number = Number(value);
  if (metric.unit === "ratio") {
    return `${(number * 100).toFixed(1)}%`;
  }
  if (metric.unit === "milliseconds") {
    return `${Math.round(number).toLocaleString()} ms`;
  }
  if (metric.unit === "stars") {
    return `${number.toFixed(1)} stars`;
  }
  if (metric.unit === "position") {
    return number.toFixed(1);
  }
  return Number.isInteger(number) ? number.toLocaleString() : number.toFixed(2);
}

function formatMeasurementDate(value?: string | null) {
  if (!value) {
    return "when enough new data is available";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "when enough new data is available";
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getPriorityLabel(riskTier = 0) {
  if (riskTier >= 3) {
    return "High priority";
  }

  if (riskTier === 2) {
    return "Medium priority";
  }

  return "Low priority";
}

function getPriorityTone(riskTier = 0) {
  if (riskTier >= 3) {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }

  if (riskTier === 2) {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }

  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
}

function getImpactLabel(confidenceScore = 0) {
  if (confidenceScore >= 0.8) {
    return "The saved information strongly supports doing this";
  }

  if (confidenceScore >= 0.6) {
    return "The saved information supports doing this";
  }

  return "We need more information before estimating the result";
}

function getWorkflowToneClass(tone: string) {
  if (tone === "success") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (tone === "danger") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  if (tone === "info") {
    return "border-sky-500/20 bg-sky-500/10 text-sky-100";
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function getStatusTone(status?: string) {
  if (status === "APPROVED" || status === "SCHEDULED") {
    return "border-accent-500/20 bg-accent-500/10 text-zinc-100";
  }

  if (status === "VALIDATED") {
    return "border-sky-500/20 bg-sky-500/10 text-sky-100";
  }

  if (status === "ARCHIVED" || status === "FAILED") {
    return "border-[#26272c] bg-[#141518] text-zinc-300";
  }

  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
}

function getStatusLabel(status?: string) {
  if (status === "GENERATED") {
    return "New";
  }
  if (status === "VALIDATED") {
    return "Checked";
  }
  if (status === "APPROVED") {
    return "Chosen";
  }
  if (status === "SCHEDULED") {
    return "Queued";
  }
  if (status === "ARCHIVED") {
    return "Cleared";
  }
  if (status === "FAILED") {
    return "Needs review";
  }
  return toTitleCase(status);
}

function describeType(type?: string) {
  if (!type) {
    return "Recommended action";
  }

  const normalized = type.toLowerCase();

  if (normalized.includes("internal_link")) {
    return "Strengthen internal links";
  }

  if (normalized.includes("content")) {
    return "Improve content coverage";
  }

  if (normalized.includes("gbp") || normalized.includes("review")) {
    return "Improve local profile trust";
  }

  if (normalized.includes("title") || normalized.includes("schema") || normalized.includes("technical")) {
    return "Make the website clearer for search";
  }

  if (normalized.includes("foundation")) {
    return "Stabilize the foundation first";
  }

  if (normalized.includes("growth")) {
    return "Push growth on stronger terms";
  }

  return toTitleCase(type);
}

function getRecommendationTitle(recommendation?: Recommendation | null) {
  const fallback = describeType(recommendation?.recommendation_type);
  return simplifyCustomerCopy(recommendation?.action_plan?.display_name || fallback, { fallback });
}

function getEffortLabel(effort?: string) {
  if (effort === "low") {
    return "Quick task";
  }
  if (effort === "medium") {
    return "Some work";
  }
  if (effort === "high") {
    return "Larger project";
  }
  return "Effort not set";
}

function getOwnerLabel(ownerRole?: string) {
  if (ownerRole === "business_owner") {
    return "Business owner";
  }
  if (ownerRole === "content_owner") {
    return "Content help";
  }
  if (ownerRole === "seo_operator") {
    return "Search marketing help";
  }
  if (ownerRole === "developer") {
    return "Website help";
  }
  return ownerRole ? toTitleCase(ownerRole) : "Owner not set";
}

function getCadenceLabel(cadence?: string) {
  if (cadence === "daily") {
    return "Today";
  }
  if (cadence === "weekly") {
    return "This week";
  }
  if (cadence === "monthly") {
    return "This month";
  }
  return "Later";
}

function describeRecommendationReason(reason?: string | null) {
  if (!reason) {
    return "InsightOS identified this as a useful improvement to review.";
  }

  const normalized = reason.toLowerCase();
  if (normalized.includes("recent review pace")) {
    return "This location is getting fewer new Google reviews than the saved goal.";
  }
  if (
    normalized.includes("google business profile") &&
    normalized.includes("review acquisition velocity")
  ) {
    return "This location is not getting enough new Google reviews.";
  }
  if (
    normalized.includes("content throughput") ||
    normalized.includes("backlink acquisition velocity")
  ) {
    return "Search visibility is steady, but growth may require more useful service content and more trusted websites linking to it.";
  }

  const rewritten = reason
    .replace(/Google Business Profile/gi, "Google business listing")
    .replace(/review acquisition velocity/gi, "new review activity")
    .replace(/acquisition velocity/gi, "new activity")
    .replace(/content throughput/gi, "new content");

  return simplifyCustomerCopy(rewritten, {
    fallback: "InsightOS found a useful improvement for this location.",
  });
}

function getEngineSourceLabel(source?: string) {
  if (source === "orchestrator_v1") {
    return "More information";
  }
  if (source === "mixed_v1") {
    return "Combined review";
  }
  if (source === "heuristic_score_v1") {
    return "Saved information";
  }
  if (source === "heuristic_threshold_v1") {
    return "Starting point";
  }
  return "Not reviewed yet";
}

function formatEvidence(value: string) {
  if (/^[a-z0-9_:.-]+$/i.test(value) && value.includes("_")) {
    return simplifyCustomerCopy(toTitleCase(value), {
      fallback: "Saved business information",
    });
  }
  return simplifyCustomerCopy(value, { fallback: "Saved business information" });
}

function canMeasureOutcome(status?: string) {
  return ["APPROVED", "SCHEDULED", "EXECUTED", "ROLLED_BACK"].includes(status || "");
}

function getOutcomeDirectionLabel(direction?: string) {
  if (direction === "improved") {
    return "Score improved";
  }
  if (direction === "declined") {
    return "Score declined";
  }
  if (direction === "no_material_change") {
    return "No measurable change";
  }
  return "Change recorded";
}

function getOutcomeTone(direction?: string) {
  if (direction === "improved") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (direction === "declined") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function formatScoreDelta(delta?: number) {
  const normalized = Number(delta || 0);
  return `${normalized > 0 ? "+" : ""}${normalized.toFixed(1)} points`;
}

function describeExecutionType(type?: string) {
  if (!type) {
    return "Execution step";
  }

  if (type === "create_content_brief") {
    return "Create content brief";
  }

  if (type === "improve_internal_links") {
    return "Improve internal links";
  }

  if (type === "fix_missing_title") {
    return "Fix missing title";
  }

  if (type === "optimize_gbp_profile") {
    return "Optimize GBP profile";
  }

  if (type === "publish_schema_markup") {
    return "Publish schema markup";
  }

  return toTitleCase(type);
}

function nextActionForStatus(status?: string) {
  if (status === "GENERATED") {
    return {
      label: "Mark as checked",
      targetState: "VALIDATED",
      summary: "Choose this after you have read the recommendation and want to keep it.",
    };
  }

  if (status === "VALIDATED") {
    return {
      label: "Make this the next action",
      targetState: "APPROVED",
      summary: "Use this when you want this recommendation to become the next action to follow.",
    };
  }

  if (status === "APPROVED") {
    return {
      label: "Queue for follow-up",
      targetState: "SCHEDULED",
      summary: "Choose this when you are ready for the team to follow up on this action.",
    };
  }

  return null;
}


function shouldAllowArchive(status?: string) {
  return status === "GENERATED" || status === "VALIDATED" || status === "APPROVED";
}

function getExecutionStatusLabel(status?: string) {
  if (status === "pending") {
    return "Awaiting approval";
  }
  if (status === "scheduled") {
    return "Ready to run";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "completed") {
    return "Completed";
  }
  if (status === "failed") {
    return "Failed";
  }
  if (status === "rolled_back") {
    return "Rolled back";
  }
  return toTitleCase(status);
}

function getExecutionStatusTone(status?: string) {
  if (status === "completed") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "scheduled" || status === "running") {
    return "border-sky-500/20 bg-sky-500/10 text-sky-100";
  }
  if (status === "pending") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  if (status === "rolled_back") {
    return "border-[#26272c] bg-[#141518] text-zinc-200";
  }
  if (status === "failed") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  return "border-[#26272c] bg-[#141518] text-zinc-200";
}

function getRiskLevelTone(level?: string) {
  if (level === "high") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  if (level === "medium") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
}

function getApprovalState(execution: Execution) {
  if (execution.approved_by && execution.approved_at) {
    return `Approved ${formatRelativeTime(execution.approved_at)} by ${execution.approved_by}`;
  }
  if (execution.status === "failed" && execution.last_error === "manual_rejection") {
    return "Rejected";
  }
  if (execution.status === "pending") {
    return "Awaiting approval";
  }
  return "No approval required";
}

function getExecutionSummary(execution: Execution) {
  if (execution.result?.notes) {
    return execution.result.notes;
  }
  if (execution.result?.message) {
    return execution.result.message;
  }
  if (execution.last_error) {
    return execution.last_error.replace(/_/g, " ");
  }
  return "Execution detail will appear here after planning, approval, or delivery events.";
}


function getMutationCount(execution: Execution) {
  if (typeof execution.mutation_count === "number") {
    return execution.mutation_count;
  }
  if (Array.isArray(execution.result?.mutations)) {
    return execution.result.mutations.length;
  }
  if (Array.isArray(execution.result?.rolled_back_mutations)) {
    return execution.result.rolled_back_mutations.length;
  }
  return 0;
}

function canApproveExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled";
}

function canApprovePreview(execution: Execution, preview?: WordPressChangePreview | null) {
  if (!requiresWordPressSetup(execution.execution_type)) {
    return canApproveExecution(execution);
  }
  return (
    (canApproveExecution(execution) ||
      (execution.status === "failed" && !execution.result?.rollback_available)) &&
    preview?.status === "ready" &&
    !preview.conflict_count
  );
}

function describeMutationType(type?: string) {
  if (type === "update_meta_title") return "Change the search title";
  if (type === "update_meta_description") return "Change the search description";
  if (type === "insert_internal_link") return "Add a helpful page link";
  if (type === "create_internal_anchor") return "Add a page section marker";
  if (type === "add_schema_markup") return "Add structured business information";
  if (type === "publish_content_page") return "Create a new draft page";
  return toTitleCase(type || "Website change");
}

function formatPreviewValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Nothing is set yet";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value, null, 2);
}

function canRejectExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled";
}

function canRunExecution(execution: Execution) {
  return (
    execution.status === "pending" ||
    execution.status === "scheduled" ||
    (execution.status === "failed" && !execution.result?.rollback_available)
  );
}

function canRunLiveExecution(execution: Execution) {
  return canRunExecution(execution) && (
    !requiresWordPressSetup(execution.execution_type) || Boolean(execution.approved_by && execution.approved_at)
  );
}

function canRetryExecution(execution: Execution) {
  return execution.status === "failed" && !execution.result?.rollback_available;
}

function canCancelExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled";
}

function canRollbackExecution(execution: Execution) {
  return (
    (execution.status === "completed" ||
      (execution.status === "failed" && execution.result?.rollback_available)) &&
    getMutationCount(execution) > 0
  );
}

function requiresWordPressSetup(executionType?: string) {
  return [
    "create_content_brief",
    "fix_missing_title",
    "improve_internal_links",
    "publish_schema_markup",
  ].includes(executionType || "");
}

function getWordPressHealthLabel(setup?: WordPressExecutionSetup | null) {
  if (!setup) {
    return "Unknown";
  }
  if (setup.blocked) {
    return "Blocked";
  }
  if (setup.health_state === "healthy") {
    return "Healthy";
  }
  return "Awaiting signal";
}

function getWordPressHealthTone(setup?: WordPressExecutionSetup | null) {
  if (!setup) {
    return "border-[#26272c] bg-[#141518] text-zinc-200";
  }
  if (setup.blocked) {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  if (setup.health_state === "healthy") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function getLiveExecutionDisabledReason(
  execution: Execution | null,
  wordpressSetup: WordPressExecutionSetup | null,
) {
  if (!WORDPRESS_EXECUTION_SETUP_UI_ENABLED || !execution) {
    return "";
  }
  if (!requiresWordPressSetup(execution.execution_type)) {
    return "";
  }
  if (wordpressSetup?.execution_ready) {
    return "";
  }
  return wordpressSetup?.disabled_reason || "WordPress execution setup is incomplete.";
}

function normalizeExecutionActionResponse(response: unknown) {
  if (!response || typeof response !== "object") {
    return { execution: null, result: null, dryRun: false };
  }

  const payload = response as {
    execution?: Execution;
    result?: ExecutionResult;
    dry_run?: boolean;
    id?: string;
  };

  if (payload.execution) {
    return {
      execution: payload.execution,
      result: payload.result || null,
      dryRun: Boolean(payload.dry_run),
    };
  }

  if (typeof payload.id === "string") {
    return {
      execution: payload as Execution,
      result: null,
      dryRun: false,
    };
  }

  return { execution: null, result: null, dryRun: false };
}


function buildExecutionTimeline(execution: Execution): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  const mutationCount = getMutationCount(execution);

  // Always first: when the execution was created
  entries.push({
    key: "created",
    label: "Execution created",
    detail: `${describeExecutionType(execution.execution_type)}. Risk level: ${toTitleCase(execution.risk_level || "medium")}.`,
    timestamp: execution.created_at ?? null,
    tone: "neutral",
  });

  // Approval decision (mutually exclusive outcomes)
  if (execution.approved_by && execution.approved_at) {
    entries.push({
      key: "approved",
      label: "Approved",
      detail: `Approved by ${execution.approved_by}.`,
      timestamp: execution.approved_at,
      tone: "success",
    });
  } else if (
    execution.status === "failed" &&
    execution.last_error === "manual_rejection"
  ) {
    entries.push({
      key: "rejected",
      label: "Rejected",
      detail: "This execution was manually rejected by an operator.",
      timestamp: null,
      tone: "error",
    });
  } else if (execution.status === "pending") {
    entries.push({
      key: "awaiting",
      label: "Awaiting approval",
      detail: "An operator needs to approve or reject this execution before it can run.",
      timestamp: null,
      tone: "warning",
    });
  }

  // Queued after approval but before execution
  if (execution.status === "scheduled") {
    entries.push({
      key: "scheduled",
      label: "Scheduled",
      detail: "This execution is approved and queued to run.",
      timestamp: null,
      tone: "neutral",
    });
  }

  // Ran (has executed_at)
  if (execution.executed_at) {
    const ranSuccessfully =
      execution.status === "completed" || execution.status === "rolled_back";
    const retryNote =
      execution.attempt_count > 1
        ? ` (${execution.attempt_count} attempts total)`
        : "";
    entries.push({
      key: "executed",
      label: ranSuccessfully ? "Executed" : "Attempted",
      detail: ranSuccessfully
        ? `Execution ran and recorded ${mutationCount} tracked change${mutationCount === 1 ? "" : "s"}.`
        : `Execution was attempted${retryNote} but did not complete successfully.`,
      timestamp: execution.executed_at,
      tone: ranSuccessfully ? "success" : "warning",
    });
  }

  // Failed state (excluding manual rejections, which are covered above)
  if (execution.status === "failed" && execution.last_error !== "manual_rejection") {
    entries.push({
      key: "failed",
      label: "Failed",
      detail: execution.last_error
        ? execution.last_error.replace(/_/g, " ")
        : "The execution failed without a recorded error message.",
      timestamp: null,
      tone: "error",
    });
  }

  // Completed with no rollback
  if (execution.status === "completed" && !execution.rolled_back_at) {
    entries.push({
      key: "completed",
      label: "Completed",
      detail:
        mutationCount > 0
          ? `${mutationCount} change${mutationCount === 1 ? "" : "s"} are now live. Rollback is available if mutations were tracked.`
          : "Execution completed. No mutations were tracked for this step.",
      timestamp: execution.executed_at ?? null,
      tone: "success",
    });
  }

  // Rolled back
  if (execution.rolled_back_at) {
    entries.push({
      key: "rolled_back",
      label: "Rolled back",
      detail:
        mutationCount > 0
          ? `${mutationCount} change${mutationCount === 1 ? "" : "s"} were reversed using the persisted mutation record.`
          : "Rollback was applied to this execution.",
      timestamp: execution.rolled_back_at,
      tone: "neutral",
    });
  }

  return entries;
}

function ForecastMetricVisual({
  metric,
  comparison,
}: {
  metric: ActionForecastMetric;
  comparison?: ActionForecastComparison;
}) {
  const observed = comparison?.observed_value;
  const values = [
    metric.current_value,
    metric.target_value,
    metric.conservative_value,
    metric.expected_value,
    metric.optimistic_value,
    ...(typeof observed === "number" ? [observed] : []),
  ];
  const rawMinimum = Math.min(...values);
  const rawMaximum = Math.max(...values);
  const span = Math.max(rawMaximum - rawMinimum, Math.abs(rawMaximum) * 0.05, 0.01);
  const minimum = rawMinimum - span * 0.08;
  const maximum = rawMaximum + span * 0.08;
  const position = (value: number) =>
    Math.min(100, Math.max(0, ((value - minimum) / (maximum - minimum)) * 100));
  const rangeStart = position(metric.range_low);
  const rangeEnd = position(metric.range_high);
  const comparisonCopy =
    comparison?.status === "within_range"
      ? "The follow-up result landed inside this range."
      : comparison?.position === "better_than_range"
        ? "The follow-up result was better than this range."
        : comparison?.position === "worse_than_range"
          ? "The follow-up result was outside this range in the wrong direction."
          : comparison?.status === "insufficient_data"
            ? "There is not enough new data to compare the result with this range."
            : null;

  return (
    <section
      data-forecast-visual={metric.metric_id}
      className="border-t border-white/10 py-4 first:border-t-0 first:pt-0 last:pb-0"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="text-sm font-semibold text-white">
            {simplifyCustomerCopy(metric.display_name, { fallback: "Website measurement" })}
          </h5>
          <p className="mt-1 text-xs leading-5 text-zinc-400">
            {simplifyCustomerCopy(metric.plain_language || "", {
              fallback: "The website measurement this work is meant to improve.",
            })}
          </p>
        </div>
        <span className="text-xs text-zinc-400">Field measurement</span>
      </div>

      <div
        role="img"
        aria-label={`${metric.display_name}: starting at ${formatMeasurementValue(metric, metric.current_value)}, possible range ${formatMeasurementValue(metric, metric.optimistic_value)} to ${formatMeasurementValue(metric, metric.conservative_value)}, expected ${formatMeasurementValue(metric, metric.expected_value)}, target ${formatMeasurementValue(metric, metric.target_value)}.`}
        className="relative mt-6 h-9"
      >
        <div className="absolute left-0 right-0 top-4 h-1 rounded-full bg-zinc-700" />
        <div
          className="absolute top-[13px] h-2 rounded-full bg-sky-400/55"
          style={{ left: `${rangeStart}%`, width: `${Math.max(2, rangeEnd - rangeStart)}%` }}
        />
        <span
          className="absolute top-1 h-7 w-0.5 bg-emerald-400"
          style={{ left: `${position(metric.target_value)}%` }}
          title="Current target"
        />
        <span
          className="absolute top-[9px] h-4 w-4 -translate-x-1/2 rounded-full border-2 border-[#151619] bg-white"
          style={{ left: `${position(metric.current_value)}%` }}
          title="Starting point"
        />
        <span
          className="absolute top-[10px] h-3.5 w-3.5 -translate-x-1/2 rounded-full border-2 border-[#151619] bg-orange-400"
          style={{ left: `${position(metric.expected_value)}%` }}
          title="Expected scenario"
        />
        {typeof observed === "number" ? (
          <span
            className="absolute top-[8px] h-5 w-5 -translate-x-1/2 rounded-full border-2 border-violet-100 bg-violet-500"
            style={{ left: `${position(observed)}%` }}
            title="Follow-up result"
          />
        ) : null}
      </div>

      <dl className="grid grid-cols-2 gap-x-5 gap-y-3 text-xs sm:grid-cols-3 xl:grid-cols-6">
        <div>
          <dt className="text-zinc-500">Starting point</dt>
          <dd className="mt-1 font-semibold text-white">{formatMeasurementValue(metric, metric.current_value)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Conservative</dt>
          <dd className="mt-1 font-semibold text-sky-100">{formatMeasurementValue(metric, metric.conservative_value)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Expected</dt>
          <dd className="mt-1 font-semibold text-orange-200">{formatMeasurementValue(metric, metric.expected_value)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Optimistic</dt>
          <dd className="mt-1 font-semibold text-sky-100">{formatMeasurementValue(metric, metric.optimistic_value)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Current target</dt>
          <dd className="mt-1 font-semibold text-emerald-200">{formatMeasurementValue(metric, metric.target_value)}</dd>
        </div>
        {typeof observed === "number" ? (
          <div>
            <dt className="text-zinc-500">Follow-up result</dt>
            <dd className="mt-1 font-semibold text-violet-200">{formatMeasurementValue(metric, observed)}</dd>
          </div>
        ) : null}
      </dl>
      {comparisonCopy ? <p className="mt-3 text-xs font-medium text-zinc-300">{comparisonCopy}</p> : null}
    </section>
  );
}

function ActionResultStatus({
  workItem,
  busy,
  onMeasure,
}: {
  workItem: ActionWorkItem;
  busy: boolean;
  onMeasure: () => void;
}) {
  const measurement = workItem.measurement;
  if (!measurement) {
    return (
      <div className="mt-4 rounded-md border border-[#303137] bg-[#111214] p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">How results will be checked</p>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          Your starting measurement will be saved when you begin the checklist. Finishing a step records the work, but it does not claim the result improved.
        </p>
      </div>
    );
  }

  const forecast = workItem.forecast;
  const baselineMetrics = measurement.baseline_metrics.filter((metric) => metric.status === "available");
  const outcomeMetrics = new Map(
    measurement.outcome_metrics.map((metric) => [metric.metric_id, metric]),
  );
  const forecastComparisons = new Map(
    (forecast?.outcome_comparisons || []).map((item) => [item.metric_id, item]),
  );
  const primaryMeasurement = getPrimaryMeasurement({
    action_plan: { work_item: workItem },
  }) as {
    baseline: ActionMeasurementMetric | null;
    outcome: ActionMeasurementMetric | null;
    resultClassification: string;
    checkOnOrAfter: string | null;
    target: { target_value?: number | null } | null;
  } | null;
  const resultClassification =
    measurement.result_classification || primaryMeasurement?.resultClassification;
  const statusCopy =
    measurement.readiness === "measured"
      ? resultClassification === "improved"
        ? { title: "The measurement improved", body: "The follow-up measurement moved in the right direction after the work was completed.", tone: "border-emerald-500/30 bg-emerald-500/10 text-emerald-100" }
        : resultClassification === "about_the_same"
          ? { title: "The result is about the same", body: "The main measurement has not changed enough to call it better or worse.", tone: "border-zinc-500/30 bg-zinc-500/10 text-zinc-100" }
          : resultClassification === "worse"
            ? { title: "The measurement got worse", body: "The main measurement moved in the wrong direction. Review what changed before choosing another step.", tone: "border-rose-500/30 bg-rose-500/10 text-rose-100" }
          : { title: "There is not enough follow-up data", body: "The work is recorded, but the connected sources do not have enough new information to judge the result.", tone: "border-sky-500/30 bg-sky-500/10 text-sky-100" }
      : measurement.readiness === "ready_to_check"
        ? { title: "Results are ready to check", body: "The waiting period is complete. Compare the latest connected measurement with the saved starting point.", tone: "border-accent-500/35 bg-accent-500/10 text-white" }
        : measurement.readiness === "waiting"
          ? { title: "Work recorded — waiting for results", body: `The checklist is finished. Results should be checked on or after ${formatMeasurementDate(measurement.observation_due_at)}.`, tone: "border-sky-500/25 bg-sky-500/10 text-sky-100" }
          : measurement.readiness === "baseline_unavailable"
            ? { title: "Starting point saved without a usable measurement", body: "The connected sources did not have enough data when this work began. The system will not invent a before-and-after result.", tone: "border-amber-500/25 bg-amber-500/10 text-amber-100" }
            : { title: "Starting point saved", body: "Complete the checklist. The result will only be judged after the waiting period and a new measurement.", tone: "border-[#303137] bg-[#111214] text-zinc-200" };

  return (
    <div className={`mt-4 rounded-md border p-4 ${statusCopy.tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] opacity-75">
            <ProductIcon name="chart" size={15} />
            Measured result
          </p>
          <h4 className="mt-2 text-base font-semibold">{statusCopy.title}</h4>
          <p className="mt-1 text-sm leading-6 opacity-85">{statusCopy.body}</p>
        </div>
        {measurement.readiness === "ready_to_check" ? (
          <button
            type="button"
            onClick={onMeasure}
            disabled={busy}
            className="rounded-md border border-accent-400/50 bg-accent-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-400 disabled:cursor-wait disabled:opacity-60"
          >
            {busy ? "Checking..." : "Check results now"}
          </button>
        ) : null}
      </div>

      {primaryMeasurement ? (
        <div className="mt-4 grid gap-3 rounded-md border border-white/10 bg-black/20 p-4 md:grid-cols-[1.3fr_0.8fr_0.8fr_1fr]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] opacity-60">
              How we&apos;ll know this helped
            </p>
            <p className="mt-1 text-sm font-semibold">
              {simplifyCustomerCopy(primaryMeasurement.baseline?.display_name, {
                fallback: "The main measurement for this action",
              })}
            </p>
            <p className="mt-1 text-xs opacity-65">
              {primaryMeasurement.baseline?.source || "A connected business source"}
            </p>
          </div>
          <div>
            <p className="text-xs opacity-60">Starting value</p>
            <p className="mt-1 text-base font-semibold">
              {primaryMeasurement.baseline?.status === "available"
                ? formatMeasurementValue(
                    primaryMeasurement.baseline,
                    primaryMeasurement.baseline.value,
                  )
                : "Not available"}
            </p>
          </div>
          <div>
            <p className="text-xs opacity-60">Latest value</p>
            <p className="mt-1 text-base font-semibold">
              {primaryMeasurement.outcome?.status === "available"
                ? formatMeasurementValue(
                    primaryMeasurement.outcome,
                    primaryMeasurement.outcome.value,
                  )
                : "Waiting"}
            </p>
          </div>
          <div>
            <p className="text-xs opacity-60">When to check</p>
            <p className="mt-1 text-sm font-semibold">
              {primaryMeasurement.checkOnOrAfter
                ? formatMeasurementDate(primaryMeasurement.checkOnOrAfter)
                : "After the checklist is finished"}
            </p>
          </div>
        </div>
      ) : null}

      {forecast?.forecast_status === "available" ? (
        <div className="mt-5 rounded-md bg-black/20 p-4 text-zinc-200">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-2xl">
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-sky-200/80">
                <ProductIcon name="chart" size={15} />
                Possible improvement — not a promise
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-300">
                This range estimates the measurement this work directly affects. It does not predict rankings, visits, leads, or revenue.
              </p>
            </div>
            <span className="text-xs text-zinc-400">
              {forecast.data_quality === "strong" ? "Strong starting data" : "Partial starting data"}
            </span>
          </div>
          <div className="mt-5">
            {forecast.metric_forecasts.map((metric) => (
              <ForecastMetricVisual
                key={metric.metric_id}
                metric={metric}
                comparison={forecastComparisons.get(metric.metric_id)}
              />
            ))}
          </div>
          <details className="mt-4 text-xs text-zinc-400">
            <summary className="cursor-pointer font-medium text-zinc-300">What this estimate assumes</summary>
            <ul className="mt-2 space-y-1 pl-4">
              {forecast.assumptions.map((assumption) => (
                <li key={assumption} className="list-disc leading-5">{assumption}</li>
              ))}
            </ul>
          </details>
        </div>
      ) : forecast?.forecast_status === "not_available" ? (
        <p className="mt-4 text-xs leading-5 text-zinc-400">
          <span className="font-semibold text-zinc-300">Forecast not available yet.</span>{" "}
          {forecast.unavailable_reasons[0]?.message || "A trustworthy numeric estimate is not available for this action."}
        </p>
      ) : null}

      {baselineMetrics.length > 0 && forecast?.forecast_status !== "available" ? (
        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {baselineMetrics.map((metric) => {
            const outcome = outcomeMetrics.get(metric.metric_id);
            return (
              <div key={metric.metric_id} className="rounded-md border border-white/10 bg-black/20 p-3">
                <p className="text-xs opacity-65">{simplifyCustomerCopy(metric.display_name, { fallback: "Saved measurement" })}</p>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-lg font-semibold">{formatMeasurementValue(metric, metric.value)}</span>
                  {outcome ? (
                    <span className="text-xs opacity-75">to {formatMeasurementValue(outcome, outcome.value)}</span>
                  ) : null}
                </div>
                <p className="mt-1 text-xs opacity-60">Based on saved information</p>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

type FeedbackChoice = {
  label: string;
  rating: number;
  reasonCode: ProductFeedbackInput["reasonCode"];
};

function ProductFeedbackPrompt({
  question,
  context,
  subjectType,
  subjectId,
  campaignId,
  choices,
}: {
  question: string;
  context: ProductFeedbackInput["context"];
  subjectType: ProductFeedbackInput["subjectType"];
  subjectId: string;
  campaignId: string;
  choices: FeedbackChoice[];
}) {
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function choose(choice: FeedbackChoice) {
    setStatus("saving");
    try {
      await submitProductFeedback({
        context,
        subjectType,
        subjectId,
        campaignId,
        rating: choice.rating,
        reasonCode: choice.reasonCode,
      });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="rounded-md border border-[#303137] bg-[#111214] p-3">
      <p className="text-sm font-medium text-white">{question}</p>
      {status === "saved" ? (
        <p className="mt-2 text-xs text-emerald-300">Thanks. Your answer was saved.</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {choices.map((choice) => (
            <button
              key={choice.label}
              type="button"
              disabled={status === "saving"}
              onClick={() => void choose(choice)}
              className="rounded-md border border-[#3a3b42] bg-[#18191c] px-3 py-1.5 text-xs font-medium text-zinc-200 transition hover:border-accent-500/40 disabled:opacity-50"
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}
      {status === "error" ? (
        <p className="mt-2 text-xs text-rose-300">That answer could not be saved. Try again.</p>
      ) : null}
    </div>
  );
}

export default function OpportunitiesPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedRecommendationId, setSelectedRecommendationId] = useState("");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState("");
  const [executionStatusFilter, setExecutionStatusFilter] = useState("all");
  const [dryRunPreview, setDryRunPreview] = useState<DryRunPreview | null>(null);
  const [summary, setSummary] = useState<RecommendationSummary | null>(null);
  const [score, setScore] = useState<IntelligenceScoreResponse | null>(null);
  const [recommendationsTruth, setRecommendationsTruth] = useState<RuntimeTruth | null>(null);
  const [engineState, setEngineState] = useState<IntelligenceEngineState | null>(null);
  const [outcomeHistory, setOutcomeHistory] = useState<OutcomeHistoryResponse | null>(null);
  const [intelligenceBrief, setIntelligenceBrief] =
    useState<GovernedIntelligenceBrief | null>(null);
  const [intelligenceRuntime, setIntelligenceRuntime] =
    useState<GovernedIntelligenceBriefResponse["runtime"] | null>(null);
  const [intelligenceAllowance, setIntelligenceAllowance] =
    useState<GovernedIntelligenceBriefResponse["allowance"] | null>(null);
  const [questionInput, setQuestionInput] = useState("");
  const [evidenceAnswers, setEvidenceAnswers] = useState<GovernedEvidenceAnswer[]>([]);
  const [actionDrafts, setActionDrafts] = useState<GovernedActionDraft[]>([]);
  const [draftActions, setDraftActions] = useState<GovernedDraftAction[]>([]);
  const [selectedDraftType, setSelectedDraftType] = useState<GovernedDraftType | "">("");
  const [wordpressSetup, setWordpressSetup] = useState<WordPressExecutionSetup | null>(null);
  const [wordpressSetupError, setWordpressSetupError] = useState("");
  const [wordpressPairing, setWordpressPairing] = useState<WordPressPairingDetails | null>(null);
  const [wordpressInventory, setWordpressInventory] = useState<WordPressContentInventory | null>(null);
  const [wordpressInventoryError, setWordpressInventoryError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
    const response = await platformApi("/campaigns", { method: "GET" });
    const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
    setCampaigns(items);
    setSelectedCampaignId((current) => {
      if (current && items.some((item) => item.id === current)) {
        return current;
      }
      return items[0]?.id || "";
    });
    return items;
  }, []);

  const loadOpportunities = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setRecommendations([]);
      setSummary(null);
      setScore(null);
      setRecommendationsTruth(null);
      setEngineState(null);
      setOutcomeHistory(null);
      setIntelligenceBrief(null);
      setIntelligenceRuntime(null);
      setIntelligenceAllowance(null);
      setQuestionInput("");
      setEvidenceAnswers([]);
      setActionDrafts([]);
      setDraftActions([]);
      setSelectedDraftType("");
      setSelectedRecommendationId("");
      return;
    }

    const [
      recommendationsResponse,
      summaryResponse,
      scoreResponse,
      outcomeResponse,
      briefResponse,
      questionResponse,
      draftResponse,
    ] = await Promise.all([
      platformApi(`/intelligence/recommendations?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/recommendations/summary?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/intelligence/score?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/intelligence/outcomes?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/intelligence/brief?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(
        `/intelligence/questions?campaign_id=${encodeURIComponent(campaignId)}&limit=5`,
        { method: "GET" },
      ),
      platformApi(
        `/intelligence/drafts?campaign_id=${encodeURIComponent(campaignId)}&limit=5`,
        { method: "GET" },
      ),
    ]);

    const normalizedRecommendations = (recommendationsResponse as RecommendationListResponse) || null;
    const items = Array.isArray(normalizedRecommendations?.items)
      ? (normalizedRecommendations.items as Recommendation[])
      : [];

    setRecommendations(items);
    setSummary((summaryResponse as RecommendationSummary) || null);
    setScore((scoreResponse as IntelligenceScoreResponse) || null);
    setRecommendationsTruth(normalizedRecommendations?.truth || null);
    setEngineState(
      normalizedRecommendations?.engine ||
        (summaryResponse as RecommendationSummary)?.engine ||
        (scoreResponse as IntelligenceScoreResponse)?.engine ||
        null,
    );
    setOutcomeHistory((outcomeResponse as OutcomeHistoryResponse) || null);
    const normalizedBrief = (briefResponse as GovernedIntelligenceBriefResponse) || null;
    setIntelligenceBrief(normalizedBrief?.item || null);
    setIntelligenceRuntime(normalizedBrief?.runtime || null);
    setIntelligenceAllowance(normalizedBrief?.allowance || null);
    const normalizedQuestions =
      (questionResponse as GovernedEvidenceAnswerResponse) || null;
    setEvidenceAnswers(
      Array.isArray(normalizedQuestions?.items) ? normalizedQuestions.items : [],
    );
    if (normalizedQuestions?.runtime) {
      setIntelligenceRuntime(normalizedQuestions.runtime);
    }
    if (normalizedQuestions?.allowance) {
      setIntelligenceAllowance(normalizedQuestions.allowance);
    }
    const normalizedDrafts = (draftResponse as GovernedActionDraftResponse) || null;
    setActionDrafts(
      Array.isArray(normalizedDrafts?.items) ? normalizedDrafts.items : [],
    );
    setDraftActions(
      Array.isArray(normalizedDrafts?.available_actions)
        ? normalizedDrafts.available_actions
        : [],
    );
    if (normalizedDrafts?.runtime) {
      setIntelligenceRuntime(normalizedDrafts.runtime);
    }
    if (normalizedDrafts?.allowance) {
      setIntelligenceAllowance(normalizedDrafts.allowance);
    }
    const portfolio = getRecommendationPortfolio(items);
    setSelectedRecommendationId((current) => {
      if (current && portfolio.ordered.some((item: Recommendation) => item.id === current)) {
        return current;
      }
      return (portfolio.primary as Recommendation | null)?.id || "";
    });
  }, []);

  const loadExecutions = useCallback(
    async (campaignId: string) => {
      if (!campaignId) {
        setExecutions([]);
        setSelectedExecutionId("");
        setDryRunPreview(null);
        return;
      }

      const query = new URLSearchParams({ campaign_id: campaignId });
      if (executionStatusFilter !== "all") {
        query.set("status", executionStatusFilter);
      }

      const response = await platformApi(`/executions?${query.toString()}`, {
        method: "GET",
      });
      const items = Array.isArray(response?.items) ? (response.items as Execution[]) : [];

      setExecutions(items);
      setSelectedExecutionId((current) => {
        if (current && items.some((item) => item.id === current)) {
          return current;
        }
        return items[0]?.id || "";
      });
      setDryRunPreview((current) => {
        if (current && items.some((item) => item.id === current.executionId)) {
          return current;
        }
        return null;
      });
    },
    [executionStatusFilter],
  );

  const loadWordPressExecutionSetup = useCallback(async (campaignId: string) => {
    if (!WORDPRESS_EXECUTION_SETUP_UI_ENABLED) {
      setWordpressSetup(null);
      setWordpressSetupError("");
      return;
    }
    if (!campaignId) {
      setWordpressSetup(null);
      setWordpressSetupError("");
      return;
    }

    try {
      const response = await platformApi(
        `/provider-health/wordpress-execution-setup?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      );
      setWordpressSetup((response as WordPressExecutionSetup) || null);
      setWordpressSetupError("");
    } catch (err) {
      setWordpressSetup(null);
      setWordpressSetupError(
        err instanceof Error ? err.message : "Unable to load WordPress execution setup.",
      );
    }
  }, []);

  const loadWordPressInventory = useCallback(async (campaignId: string) => {
    if (!WORDPRESS_EXECUTION_SETUP_UI_ENABLED || !campaignId) {
      setWordpressInventory(null);
      setWordpressInventoryError("");
      return;
    }
    try {
      const response = await platformApi(
        `/provider-health/wordpress-content-inventory?campaign_id=${encodeURIComponent(campaignId)}&limit=100`,
        { method: "GET" },
      );
      setWordpressInventory((response as WordPressContentInventory) || null);
      setWordpressInventoryError("");
    } catch (err) {
      setWordpressInventory(null);
      setWordpressInventoryError(
        err instanceof Error ? err.message : "Unable to load the WordPress page list.",
      );
    }
  }, []);

  async function testWordPressConnection() {
    if (!selectedCampaignId) return;
    await runAction("wordpress-connection-check", async () => {
      const response = await platformApi(
        `/provider-health/wordpress-execution-check?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      await loadWordPressExecutionSetup(selectedCampaignId);
      setNotice(
        response?.message ||
          "Connection confirmed. WordPress changes still require review and approval.",
      );
    });
  }

  async function createWordPressPairingCode() {
    if (!selectedCampaignId) return;
    await runAction("wordpress-pairing", async () => {
      const response = await platformApi(
        `/provider-health/wordpress-pairing/start?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      setWordpressPairing((response as WordPressPairingDetails) || null);
      await loadWordPressExecutionSetup(selectedCampaignId);
      setNotice("Pairing code created. Enter it in the InsightOS WordPress plugin within 10 minutes.");
    });
  }

  async function downloadWordPressPlugin() {
    if (!selectedCampaignId) return;
    await runAction("wordpress-plugin-download", async () => {
      const file = await platformApiFile(
        `/provider-health/wordpress-plugin-download?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "GET" },
      );
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download =
        wordpressSetup?.plugin_package?.filename || "insightos-wordpress-plugin.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 60_000);
      setNotice("The WordPress plugin was downloaded. Keep the ZIP file intact for upload.");
    });
  }

  async function disconnectWordPress() {
    if (!selectedCampaignId) return;
    if (!window.confirm("Disconnect this website from InsightOS? No website content will be removed.")) {
      return;
    }
    await runAction("wordpress-disconnect", async () => {
      const response = await platformApi(
        `/provider-health/wordpress-connection?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "DELETE" },
      );
      setWordpressPairing(null);
      setWordpressInventory(null);
      await loadWordPressExecutionSetup(selectedCampaignId);
      setNotice(response?.message || "WordPress is disconnected.");
    });
  }

  async function syncWordPressContent() {
    if (!selectedCampaignId) return;
    await runAction("wordpress-content-sync", async () => {
      const response = await platformApi(
        `/provider-health/wordpress-content-sync?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      setWordpressInventory((response as WordPressContentInventory) || null);
      await loadWordPressExecutionSetup(selectedCampaignId);
      setNotice(response?.message || "Website pages are up to date. Nothing was changed.");
    });
  }

  const refreshCampaignData = useCallback(
    async (campaignId: string) => {
      await Promise.all([
        loadOpportunities(campaignId),
        loadExecutions(campaignId),
        loadWordPressExecutionSetup(campaignId),
        loadWordPressInventory(campaignId),
      ]);
    },
    [loadExecutions, loadOpportunities, loadWordPressExecutionSetup, loadWordPressInventory],
  );

  async function runAction(action: string, fn: () => Promise<void>) {
    setBusyAction(action);
    setError("");
    setNotice("");

    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusyAction("");
    }
  }

  async function updateChecklistStep(
    recommendationId: string,
    workItemId: string,
    stepId: string,
    currentStatus: ActionWorkStep["status"],
  ) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    const targetStatus = currentStatus === "done" ? "not_started" : "done";
    await runAction(`${workItemId}:${stepId}`, async () => {
      await platformApi(
        `/intelligence/action-plans/${encodeURIComponent(workItemId)}/steps/${encodeURIComponent(stepId)}?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: targetStatus }),
        },
      );
      await loadOpportunities(selectedCampaignId);
      setSelectedRecommendationId(recommendationId);
      setNotice(
        targetStatus === "done"
          ? "Step saved. Your checklist will be here when you come back."
          : "Step reopened and saved.",
      );
    });
  }

  async function measureActionPlanResult(
    recommendationId: string,
    workItemId: string,
  ) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction(`${workItemId}:measure`, async () => {
      await platformApi(
        `/intelligence/action-plans/${encodeURIComponent(workItemId)}/measure?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      await loadOpportunities(selectedCampaignId);
      setSelectedRecommendationId(recommendationId);
      setNotice("The latest measurement was compared with the saved starting point.");
    });
  }

  async function transitionRecommendation(
    recommendationId: string,
    targetState: string,
    successNotice: string,
  ) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction(`${recommendationId}:${targetState}`, async () => {
      await platformApi(
        `/intelligence/recommendations/${recommendationId}/transition?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({ target_state: targetState }),
        },
      );

      await loadOpportunities(selectedCampaignId);
      setSelectedRecommendationId(recommendationId);
      setNotice(`${successNotice} Check the workflow state on this page to confirm what should happen next.`);
    });
  }

  async function measureRecommendationOutcome(recommendationId: string) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction(`${recommendationId}:measure-outcome`, async () => {
      const response = await platformApi(
        `/intelligence/recommendations/${recommendationId}/measure-outcome?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      await loadOpportunities(selectedCampaignId);
      const outcome = response?.outcome as RecommendationOutcome | undefined;
      setSelectedRecommendationId(recommendationId);
      setNotice(
        response?.created
          ? `Progress measured: ${getOutcomeDirectionLabel(outcome?.direction).toLowerCase()} (${formatScoreDelta(outcome?.delta)}). This is an observation, not proof that the recommendation caused the change.`
          : "The saved score has not changed since the latest measurement, so no duplicate outcome was added.",
      );
    });
  }

  async function runStoredDataIntelligenceCycle() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction("run-intelligence-cycle", async () => {
      const currentCampaign =
        campaigns.find((item) => item.id === selectedCampaignId) ?? null;
      const activationPath: Record<string, string[]> = {
        Draft: ["Configured", "BaselineRunning", "Active"],
        Configured: ["BaselineRunning", "Active"],
        BaselineRunning: ["Active"],
        Paused: ["Active"],
        Active: [],
      };
      const currentSetupState = currentCampaign?.setup_state || "Draft";
      const transitions = activationPath[currentSetupState];
      if (!transitions) {
        throw new Error(
          `Campaign setup state “${currentSetupState}” cannot be activated from this workspace.`,
        );
      }

      let activatedCampaign = false;
      for (const targetState of transitions) {
        await platformApi(
          `/campaigns/${encodeURIComponent(selectedCampaignId)}/setup-state`,
          {
            method: "PATCH",
            body: JSON.stringify({ target_state: targetState }),
          },
        );
        activatedCampaign = true;
      }

      const response = (await platformApi(
        `/intelligence/cycles/run?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      )) as IntelligenceCycleResponse;
      await Promise.all([loadCampaigns(), loadOpportunities(selectedCampaignId)]);
      if (response.status === "running") {
        setNotice(
          `${activatedCampaign ? "Recommendations are now active for this location. " : ""}InsightOS is already reviewing the saved information. Check again in a moment to see the result.`,
        );
        return;
      }
      if (response.status !== "completed") {
        throw new Error(
          "InsightOS could not finish reviewing this location. Check the business setup and try again.",
        );
      }
      if (response.idempotent_replay) {
        setNotice(
          `${activatedCampaign ? "Recommendations are now active for this location. " : ""}Today’s review was already complete, so the existing recommendations were kept without creating duplicates.`,
        );
        return;
      }
      setNotice(
        `${activatedCampaign ? "Recommendations are now active for this location. " : ""}Review complete: ${response.result?.recommendations_generated || 0} recommendation${response.result?.recommendations_generated === 1 ? "" : "s"} ready. No paid checks or automatic website changes were started.`,
      );
    });
  }

  async function explainIntelligenceBrief() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction("explain-intelligence-brief", async () => {
      const response = (await platformApi(
        `/intelligence/brief?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            retry_failed: Boolean(
              intelligenceBrief && intelligenceBrief.status !== "validated",
            ),
          }),
        },
      )) as GovernedIntelligenceBriefResponse;
      setIntelligenceBrief(response.item || null);
      setIntelligenceRuntime(response.runtime || null);
      setIntelligenceAllowance(response.allowance || null);

      if (response.item?.status === "validated") {
        setNotice(
          response.idempotent_replay
            ? "Today’s action plan is already up to date."
            : "Today’s action plan is ready. InsightOS kept the saved facts, actions, and approval rules unchanged.",
        );
      } else {
        setNotice(
          "Fresh wording was not available, so InsightOS kept the saved action plan. Your checklist still works.",
        );
      }
    });
  }

  async function askEvidenceQuestion() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    const question = questionInput.trim();
    if (question.length < 3) {
      setError("Ask a short question about this business.");
      return;
    }

    const priorAttempt = evidenceAnswers.find(
      (item) => item.output.question.toLowerCase() === question.toLowerCase(),
    );
    await runAction("ask-evidence-question", async () => {
      const response = (await platformApi(
        `/intelligence/questions?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            question,
            retry_failed: Boolean(
              priorAttempt && priorAttempt.status !== "validated",
            ),
          }),
        },
      )) as GovernedEvidenceAnswerResponse;
      if (response.item) {
        setEvidenceAnswers((current) => [
          response.item!,
          ...current.filter((item) => item.id !== response.item!.id),
        ].slice(0, 5));
      }
      if (response.runtime) {
        setIntelligenceRuntime(response.runtime);
      }
      if (response.allowance) {
        setIntelligenceAllowance(response.allowance);
      }

      if (response.item?.status === "validated") {
        setQuestionInput("");
        setNotice(
          response.idempotent_replay
            ? "That answer is already up to date for the saved information."
            : "Answer ready. It only uses the saved information shown for this location.",
        );
      } else {
        setNotice(
          "A verified answer was not available, so InsightOS kept your saved facts and actions unchanged.",
        );
      }
    });
  }

  async function generateActionDraft(refresh = false) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    if (!selectedDraftAction || !activeDraftType) {
      setError("Choose an action that has writing help available.");
      return;
    }

    const priorAttempt = actionDrafts.find(
      (item) =>
        item.output.action_id === selectedDraftAction.action_id &&
        item.output.draft_type === activeDraftType,
    );
    await runAction("generate-action-draft", async () => {
      const response = (await platformApi(
        `/intelligence/drafts?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            action_id: selectedDraftAction.action_id,
            draft_type: activeDraftType,
            refresh,
            retry_failed: Boolean(
              priorAttempt && priorAttempt.status !== "validated",
            ),
          }),
        },
      )) as GovernedActionDraftResponse;
      if (response.item) {
        setActionDrafts((current) => [
          response.item!,
          ...current.filter((item) => item.id !== response.item!.id),
        ].slice(0, 5));
      }
      if (Array.isArray(response.available_actions)) {
        setDraftActions(response.available_actions);
      }
      if (response.runtime) {
        setIntelligenceRuntime(response.runtime);
      }
      if (response.allowance) {
        setIntelligenceAllowance(response.allowance);
      }

      if (response.item?.status === "validated") {
        setNotice(
          response.idempotent_replay
            ? "This draft is already up to date for the saved information."
            : "Draft ready for your review. Nothing was changed or published.",
        );
      } else {
        setNotice(
          "Writing help is unavailable right now. The saved action and checklist were not changed.",
        );
      }
    });
  }

  async function transitionExecution(
    executionId: string,
    action: "approve" | "reject" | "run" | "retry" | "cancel" | "rollback",
    successNotice: string,
    body?: Record<string, unknown>,
  ) {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction(`${executionId}:${action}`, async () => {
      const response = await platformApi(`/executions/${executionId}/${action}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : JSON.stringify({}),
      });
      const normalized = normalizeExecutionActionResponse(response);

      if (normalized.dryRun && normalized.result) {
        setDryRunPreview({ executionId, result: normalized.result });
      } else if (action !== "run") {
        setDryRunPreview((current) => (current?.executionId === executionId ? null : current));
      }

      await refreshCampaignData(selectedCampaignId);
      setSelectedExecutionId(normalized.execution?.id || executionId);
      setNotice(`${successNotice} Check the execution state below to confirm whether it completed, queued, failed, or needs follow-up.`);
    });
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        await platformApi("/auth/me", { method: "GET" });
        const items = await loadCampaigns();
        if (items[0]?.id) {
          await refreshCampaignData(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load opportunities.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns, refreshCampaignData]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void refreshCampaignData(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load opportunities.");
    });
  }, [selectedCampaignId, executionStatusFilter, loading, refreshCampaignData]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const runtimeTruth = useMemo(
    () => pickPrimaryRuntimeTruth([recommendationsTruth, summary?.truth, score?.truth]),
    [recommendationsTruth, score?.truth, summary?.truth],
  );

  const actionPortfolio = useMemo(
    () => getRecommendationPortfolio(recommendations),
    [recommendations],
  );
  const sortedRecommendations = actionPortfolio.ordered as Recommendation[];
  const topRecommendation = actionPortfolio.primary as Recommendation | null;
  const routineGroups = useMemo(
    () => getRecommendationRoutines(recommendations) as Record<string, Recommendation[]>,
    [recommendations],
  );
  const actionTrackGroups = useMemo(
    () => getActionTrackGroups(recommendations) as Record<"website" | "google_business_profile", Recommendation[]>,
    [recommendations],
  );

  const selectedRecommendation =
    sortedRecommendations.find((item) => item.id === selectedRecommendationId) ??
    sortedRecommendations[0] ??
    null;
  const selectedDraftAction = draftActions.find(
    (item) => item.action_id === selectedRecommendation?.action_plan?.action_id,
  ) ?? null;
  const activeDraftType: GovernedDraftType | "" =
    selectedDraftAction?.draft_types.some(
      (item) => item.draft_type === selectedDraftType,
    )
      ? selectedDraftType
      : selectedDraftAction?.draft_types[0]?.draft_type || "";
  const activeDraftTypeOption = selectedDraftAction?.draft_types.find(
    (item) => item.draft_type === activeDraftType,
  ) ?? null;
  const currentActionDraft = actionDrafts.find(
    (item) =>
      item.output.action_id === selectedDraftAction?.action_id &&
      item.output.draft_type === activeDraftType,
  ) ?? null;

  const selectedExecution =
    executions.find((item) => item.id === selectedExecutionId) ?? executions[0] ?? null;

  useEffect(() => {
    if (!selectedCampaignId || !selectedRecommendation?.id) {
      return;
    }
    const dayKey = analyticsDayKey();
    void trackProductEvent({
      eventName: "recommendation.viewed",
      campaignId: selectedCampaignId,
      properties: { surface: "next_steps" },
      idempotencyKey: `recommendation.viewed:${selectedRecommendation.id}:${dayKey}`,
    });
    const forecast = selectedRecommendation.action_plan?.work_item?.forecast;
    if (forecast?.forecast_status === "available") {
      void trackProductEvent({
        eventName: "forecast.viewed",
        campaignId: selectedCampaignId,
        properties: {
          data_quality: forecast.data_quality === "strong" ? "strong" : "partial",
        },
        idempotencyKey: `forecast.viewed:${selectedRecommendation.id}:${dayKey}`,
      });
    }
  }, [selectedCampaignId, selectedRecommendation]);

  const highPriorityCount = sortedRecommendations.filter((item) => (item.risk_tier ?? 0) >= 3).length;
  const readyCount = sortedRecommendations.filter((item) =>
    ["VALIDATED", "APPROVED"].includes(item.status || ""),
  ).length;
  const queuedCount = sortedRecommendations.filter((item) => item.status === "SCHEDULED").length;
  const archivedCount = recommendations.filter((item) => item.status === "ARCHIVED").length;
  const pendingExecutionsCount = executions.filter((item) => item.status === "pending").length;
  const failedExecutionsCount = executions.filter((item) => item.status === "failed").length;
  const completedExecutionsCount = executions.filter((item) => item.status === "completed").length;

  const topSummary = useMemo(() => {
    if (!selectedCampaign) {
      return {
        title: "No business is selected yet",
        body: "Set up a business first so InsightOS can identify what needs attention next.",
        next: "Go back to the dashboard to finish setup and start your first checks.",
      };
    }

    if (!topRecommendation) {
      return {
        title: `${selectedCampaign.name || "This business"} has no active opportunities yet`,
        body: "InsightOS has not surfaced a recommendation queue for this business yet.",
        next: "Refresh after more crawl, ranking, or local data is available.",
      };
    }

    return {
      title: getRecommendationTitle(topRecommendation),
      body: describeRecommendationReason(topRecommendation.rationale),
      next: simplifyCustomerCopy(
        topRecommendation.action_plan?.work_item?.next_step?.instruction ||
          topRecommendation.action_plan?.steps?.[0] ||
          nextActionForStatus(topRecommendation.status)?.summary ||
          "Check what we found, then decide whether this action should stay on your list.",
        { fallback: "Open this action and follow the first step." },
      ),
    };
  }, [selectedCampaign, topRecommendation]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Action plan status",
        runtimeTruth,
        "Recommendations and scores are heuristic until execution setup is ready and a run succeeds.",
      ),
      {
        label: "Next steps",
        value: sortedRecommendations.length ? `${sortedRecommendations.length} active` : "None yet",
        tone: sortedRecommendations.length > 0 ? "info" : "warning",
      },
      {
        label: "High priority",
        value: highPriorityCount > 0 ? `${highPriorityCount} urgent` : "No urgent items",
        tone: highPriorityCount > 0 ? "warning" : "success",
      },
      {
        label: "How guidance was prepared",
        value: getEngineSourceLabel(engineState?.guidance_source),
        tone:
          engineState?.guidance_source === "orchestrator_v1" ||
          engineState?.guidance_source === "mixed_v1"
            ? "success"
            : "info",
      },
      {
        label: "Overall score",
        value:
          score?.score_value !== undefined && score?.score_value !== null
            ? `${score.score_value}/100`
            : "Awaiting score",
        tone:
          (score?.score_value || 0) >= 70
            ? "success"
            : (score?.score_value || 0) >= 50
              ? "info"
              : "warning",
      },
    ],
    [
      engineState?.guidance_source,
      highPriorityCount,
      runtimeTruth,
      score?.score_value,
      sortedRecommendations.length,
    ],
  );

  const primaryAction = selectedRecommendation
    ? nextActionForStatus(selectedRecommendation.status)
    : null;
  const recommendationState = selectedRecommendation
    ? getRecommendationStateSummary(selectedRecommendation.status)
    : null;

  const executionEvidence = selectedExecution
    ? [
        `Approval state: ${getApprovalState(selectedExecution)}`,
        `Attempts: ${selectedExecution.attempt_count || 0}`,
        `Mutations tracked: ${getMutationCount(selectedExecution)}`,
        selectedExecution.last_error
          ? `Latest error: ${selectedExecution.last_error.replace(/_/g, " ")}`
          : "Latest error: none",
      ]
    : [];
  const liveExecutionDisabledReason = getLiveExecutionDisabledReason(selectedExecution, wordpressSetup);
  const executionState = selectedExecution
    ? getExecutionStateSummary(selectedExecution, { getMutationCount, canRollbackExecution })
    : null;
  const setupBlockerState = getSetupBlockerSummary(
    selectedExecution,
    wordpressSetup,
    liveExecutionDisabledReason,
    requiresWordPressSetup,
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed campaign"} / ${selectedCampaign.domain || "No domain"}`
          : "No campaign selected"
      }
      dateRangeLabel="Saved action plan"
      topBarActions={
        <>
          <button
            onClick={() => void refreshCampaignData(selectedCampaignId)}
            disabled={!selectedCampaignId || busyAction !== ""}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reload saved data
          </button>
          <button
            onClick={() => void runStoredDataIntelligenceCycle()}
            disabled={!selectedCampaignId || busyAction !== ""}
            className="rounded-md border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-sm font-medium text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busyAction === "run-intelligence-cycle"
              ? "Reviewing saved information..."
              : selectedCampaign?.setup_state === "Active"
                ? "Check for new recommendations"
                : "Start recommendations"}
          </button>
          <button
            onClick={() => router.push("/reports")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            View reports
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Next steps"
          title="Your action plan"
          summary="Start with the most important improvement for this location, then work through the other useful actions below it."
          compact
        />

        <TruthNotice title="Nothing changes on your website without review.">
          These are recommendations. A suggested change is not complete until it has been reviewed,
          approved, and successfully carried out.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading opportunities"
            summary="Pulling the latest recommended actions, priority signals, and next-step guidance for the active business."
          />
        ) : null}

        {error ? (
          <section className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}

        {notice ? (
          <section className="rounded-md border border-accent-500/20 bg-accent-500/10 p-4 text-sm text-zinc-100">
            {notice}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="No business is ready for opportunities yet"
            summary="Set up a business first so InsightOS can recommend what should happen next."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            {!OWNER_JOURNEY_V2_ENABLED ? (
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Do this first
              </p>
              <div className="mt-3 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <div>
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                    {topSummary.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.body}</p>
                  {topRecommendation ? (
                    <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-zinc-400">
                      <span>{getPriorityLabel(topRecommendation.risk_tier)}</span>
                      <span>{getEffortLabel(topRecommendation.action_plan?.effort)}</span>
                      <span>{getOwnerLabel(topRecommendation.action_plan?.owner_role)}</span>
                    </div>
                  ) : null}
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What to do next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.next}</p>
                </div>
              </div>
            </section>
            ) : null}

            {topRecommendation ? (
              <section aria-labelledby="work-routine-title" className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.32)]">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Your work routine
                    </p>
                    <h2 id="work-routine-title" className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Your daily, weekly, and monthly checklist
                    </h2>
                    <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                      Finish the next unchecked step. InsightOS saves your progress automatically.
                    </p>
                  </div>
                  <span className="text-xs text-zinc-500">
                    {sortedRecommendations.length} active action{sortedRecommendations.length === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="mt-5 grid gap-3 lg:grid-cols-2">
                  {([
                    {
                      key: "website" as const,
                      title: "Improve your website",
                      summary: "Pages, search visibility, speed, and website fixes.",
                      icon: "website-health" as const,
                    },
                    {
                      key: "google_business_profile" as const,
                      title: "Improve your Google Business Profile",
                      summary: "Reviews, profile activity, calls, clicks, and direction requests.",
                      icon: "listings" as const,
                    },
                  ]).map((track) => {
                    const trackItems = actionTrackGroups[track.key] || [];
                    return (
                      <section
                        key={track.key}
                        className="rounded-md border border-[#2a2b31] bg-[#111214] p-4"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3">
                            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-accent-500/20 bg-accent-500/10 text-accent-300">
                              <ProductIcon name={track.icon} size={18} />
                            </span>
                            <div>
                              <h3 className="text-base font-semibold text-white">{track.title}</h3>
                              <p className="mt-1 text-xs leading-5 text-zinc-400">{track.summary}</p>
                            </div>
                          </div>
                          <span className="rounded-full bg-[#202126] px-2 py-0.5 text-xs text-zinc-300">
                            {trackItems.length}
                          </span>
                        </div>
                        {trackItems.length > 0 ? (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {trackItems.slice(0, 3).map((recommendation) => (
                              <button
                                key={recommendation.id}
                                type="button"
                                onClick={() => setSelectedRecommendationId(recommendation.id)}
                                className={`rounded-md border px-3 py-2 text-left text-xs font-medium transition ${
                                  selectedRecommendation?.id === recommendation.id
                                    ? "border-accent-500/40 bg-accent-500/10 text-white"
                                    : "border-[#303137] bg-[#16171a] text-zinc-300 hover:border-accent-500/30"
                                }`}
                              >
                                {getRecommendationTitle(recommendation)}
                              </button>
                            ))}
                            {trackItems.length > 3 ? (
                              <span className="self-center text-xs text-zinc-500">
                                +{trackItems.length - 3} more
                              </span>
                            ) : null}
                          </div>
                        ) : (
                          <p className="mt-4 text-xs text-zinc-500">No active work in this area right now.</p>
                        )}
                      </section>
                    );
                  })}
                </div>

                <div className="mt-5 grid gap-3 xl:grid-cols-3">
                  {ROUTINE_SECTIONS.map((section) => {
                    const routineItems = section.key === "monthly"
                      ? [
                          ...(routineGroups.monthly || []),
                          ...(routineGroups.later || []),
                        ]
                      : routineGroups[section.key] || [];
                    return (
                      <div
                        key={section.key}
                        className="rounded-md border border-[#2a2b31] bg-[#111214] p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-base font-semibold text-white">{section.title}</h3>
                            <p className="mt-1 text-xs leading-5 text-zinc-500">{section.summary}</p>
                          </div>
                          <span className="rounded-full bg-[#202126] px-2 py-0.5 text-xs text-zinc-300">
                            {routineItems.length}
                          </span>
                        </div>

                        {routineItems.length > 0 ? (
                          <div className="mt-4 space-y-2">
                            {routineItems.map((recommendation) => {
                              const progress = getWorkProgress(recommendation);
                              const nextStep = recommendation.action_plan?.work_item?.next_step;
                              return (
                                <button
                                  key={recommendation.id}
                                  type="button"
                                  onClick={() => setSelectedRecommendationId(recommendation.id)}
                                  className="w-full rounded-md border border-[#2a2b31] bg-[#16171a] p-3 text-left transition hover:border-accent-500/35"
                                >
                                  <p className="text-sm font-semibold leading-5 text-white">
                                    {getRecommendationTitle(recommendation)}
                                  </p>
                                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#292a30]">
                                    <div
                                      className="h-full rounded-full bg-accent-500"
                                      style={{ width: `${progress.percent}%` }}
                                    />
                                  </div>
                                  <p className="mt-2 text-xs text-zinc-400">{progress.label}</p>
                                  <p className="mt-3 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-zinc-500">
                                    <ProductIcon name="check" size={13} className="text-accent-400" />
                                    Next unchecked step
                                  </p>
                                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-300">
                                    {simplifyCustomerCopy(nextStep?.instruction, {
                                      fallback:
                                      (progress.total > 0
                                        ? "Checklist complete. Wait for the result window."
                                        : "Open this action to review the plan."),
                                    })}
                                  </p>
                                </button>
                              );
                            })}
                          </div>
                        ) : (
                          <p className="mt-4 rounded-md border border-dashed border-[#2a2b31] px-3 py-4 text-xs leading-5 text-zinc-500">
                            Nothing is due here right now.
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>

                {(routineGroups.later || []).length > 0 ? (
                  <p className="mt-4 border-t border-[#26272c] pt-4 text-xs text-zinc-500">
                    Actions without a firm date are included under This month so nothing useful is hidden.
                  </p>
                ) : null}

                {OWNER_JOURNEY_V2_ENABLED && selectedRecommendation ? (
                  <section aria-labelledby="current-checklist-title" className="mt-5 border-t border-[#303137] pt-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="max-w-3xl">
                        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-300">
                          <ProductIcon name="check" size={15} />
                          Current checklist
                        </p>
                        <h3 id="current-checklist-title" className="mt-2 text-lg font-semibold text-white">
                          {getRecommendationTitle(selectedRecommendation)}
                        </h3>
                        <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                          {simplifyCustomerCopy(
                            selectedRecommendation.action_plan?.work_item?.next_step?.instruction ||
                              selectedRecommendation.action_plan?.steps?.[0] ||
                              "Open this action when you are ready to begin.",
                            { fallback: "Open this action when you are ready to begin." },
                          )}
                        </p>
                      </div>
                      <div className="text-right text-xs text-zinc-400">
                        <p>{getWorkProgress(selectedRecommendation).label}</p>
                        <p className="mt-1">{getEffortLabel(selectedRecommendation.action_plan?.effort)}</p>
                      </div>
                    </div>

                    {selectedRecommendation.action_plan?.work_item?.steps?.length ? (
                      <div className="mt-4 grid gap-2 lg:grid-cols-3">
                        {selectedRecommendation.action_plan.work_item.steps.map((step) => {
                          const isDone = step.status === "done";
                          const actionKey = `${selectedRecommendation.action_plan?.work_item?.id}:${step.id}`;
                          return (
                            <button
                              key={step.id}
                              type="button"
                              aria-pressed={isDone}
                              onClick={() =>
                                void updateChecklistStep(
                                  selectedRecommendation.id,
                                  selectedRecommendation.action_plan!.work_item!.id,
                                  step.id,
                                  step.status,
                                )
                              }
                              disabled={busyAction === actionKey}
                              className={`flex min-h-24 items-start gap-3 rounded-md border p-3 text-left transition disabled:cursor-wait disabled:opacity-60 ${
                                isDone
                                  ? "border-emerald-500/25 bg-emerald-500/10"
                                  : "border-[#303137] bg-[#111214] hover:border-accent-500/40"
                              }`}
                            >
                              <span
                                aria-hidden="true"
                                className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border ${
                                  isDone
                                    ? "border-emerald-400 bg-emerald-500 text-[#07130d]"
                                    : "border-zinc-600 text-zinc-400"
                                }`}
                              >
                                {isDone ? <ProductIcon name="check" size={14} /> : step.position}
                              </span>
                              <span>
                                <span className={`block text-sm leading-5 ${isDone ? "text-zinc-500 line-through" : "text-zinc-200"}`}>
                                  {simplifyCustomerCopy(step.instruction, { fallback: "Complete this step." })}
                                </span>
                                <span className="mt-2 block text-xs text-zinc-500">
                                  {busyAction === actionKey
                                    ? "Saving..."
                                    : isDone
                                      ? "Finished — select to reopen"
                                      : "Select when finished"}
                                </span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="mt-4 rounded-md border border-dashed border-[#303137] px-4 py-3 text-sm text-zinc-400">
                        The detailed checklist is still being prepared. The first useful step is shown above.
                      </p>
                    )}
                    {selectedRecommendation.action_plan?.work_item ? (
                      <>
                        <ActionResultStatus
                          workItem={selectedRecommendation.action_plan.work_item}
                          busy={busyAction === `${selectedRecommendation.action_plan.work_item.id}:measure`}
                          onMeasure={() =>
                            void measureActionPlanResult(
                              selectedRecommendation.id,
                              selectedRecommendation.action_plan!.work_item!.id,
                            )
                          }
                        />
                        <div className="mt-3 grid gap-3 lg:grid-cols-2">
                          <ProductFeedbackPrompt
                            question="Is this recommended action useful?"
                            context="recommendation_usefulness"
                            subjectType="recommendation"
                            subjectId={selectedRecommendation.id}
                            campaignId={selectedCampaignId}
                            choices={[
                              { label: "Yes", rating: 5, reasonCode: "useful" },
                              { label: "Not yet", rating: 2, reasonCode: "not_useful_yet" },
                            ]}
                          />
                          {selectedRecommendation.action_plan.work_item.forecast?.forecast_status === "available" ? (
                            <ProductFeedbackPrompt
                              question="Does this possible result feel believable?"
                              context="forecast_trust"
                              subjectType="forecast"
                              subjectId={selectedRecommendation.id}
                              campaignId={selectedCampaignId}
                              choices={[
                                { label: "Yes", rating: 5, reasonCode: "believable" },
                                { label: "Not sure", rating: 3, reasonCode: "missing_context" },
                                { label: "No", rating: 1, reasonCode: "not_believable" },
                              ]}
                            />
                          ) : null}
                        </div>
                      </>
                    ) : null}
                  </section>
                ) : null}
              </section>
            ) : null}

            {selectedCampaignId ? (
              <ProgressMilestones campaignId={selectedCampaignId} />
            ) : null}

            <details className="rounded-md border border-violet-500/20 bg-[linear-gradient(135deg,rgba(139,92,246,0.07),rgba(20,21,24,0.96)_52%)] p-4 shadow-[0_0_30px_rgba(0,0,0,0.3)]">
              <summary className="cursor-pointer list-none">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-200/70">
                  Today&apos;s plan
                </p>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <h2 className="text-base font-semibold text-white">
                    Open today&apos;s action list
                  </h2>
                  <span className="text-xs text-violet-200">Show</span>
                </div>
              </summary>
              <div className="mt-4 flex flex-wrap items-start justify-between gap-4 border-t border-violet-500/15 pt-4">
                <p className="max-w-3xl text-sm leading-6 text-zinc-300">
                  InsightOS uses the saved facts and approved actions to prepare this wording.
                  It cannot change your website.
                </p>
                <button
                  onClick={() => void explainIntelligenceBrief()}
                  disabled={!selectedCampaignId || busyAction !== ""}
                  className="rounded-md border border-violet-400/30 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "explain-intelligence-brief"
                    ? "Preparing today’s plan..."
                    : intelligenceBrief
                      ? "Refresh today’s plan"
                      : "Build today’s plan"}
                </button>
              </div>

              {intelligenceBrief ? (
                <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                  <div className="rounded-md border border-violet-500/15 bg-[#111214]/90 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                          intelligenceBrief.status === "validated"
                            ? "border-violet-400/25 bg-violet-500/10 text-violet-100"
                            : "border-amber-500/20 bg-amber-500/10 text-amber-100"
                        }`}
                      >
                        {intelligenceBrief.status === "validated"
                          ? "Today’s summary"
                          : "Saved guidance"}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {formatRelativeTime(intelligenceBrief.created_at)}
                      </span>
                    </div>
                    <p className="mt-4 text-base font-medium leading-7 text-white">
                      {intelligenceBrief.output.summary}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-zinc-300">
                      {intelligenceBrief.output.why_now}
                    </p>
                    {intelligenceBrief.output.uncertainties?.length ? (
                      <details className="mt-4 border-t border-[#26272c] pt-3">
                        <summary className="cursor-pointer text-sm font-medium text-zinc-300">
                          What is still uncertain
                        </summary>
                        <ul className="mt-2 space-y-1 text-sm leading-6 text-zinc-400">
                          {intelligenceBrief.output.uncertainties.map((item) => (
                            <li key={item}>• {item}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </div>

                  <div className="rounded-md border border-[#26272c] bg-[#111214]/90 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Today&apos;s action list
                    </p>
                    {intelligenceBrief.output.daily_actions?.length ? (
                      <ol className="mt-3 space-y-3">
                        {intelligenceBrief.output.daily_actions.map((action, index) => (
                          <li
                            key={action.action_id}
                            className="rounded-md border border-[#2b2c32] bg-[#15161a] p-3"
                          >
                            <div className="flex items-start gap-3">
                              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-violet-500/15 text-xs font-semibold text-violet-100">
                                {index + 1}
                              </span>
                              <div>
                                <h3 className="text-sm font-semibold text-white">
                                  {simplifyCustomerCopy(action.display_name, {
                                    fallback: "Review this action",
                                  })}
                                </h3>
                                <p className="mt-1 text-xs leading-5 text-zinc-400">
                                  {simplifyCustomerCopy(action.steps?.[0], {
                                    fallback: "Open the checklist and complete the next step.",
                                  })}
                                </p>
                              </div>
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="mt-2 text-sm leading-6 text-zinc-300">
                        There is not enough verified information for a specific action yet.
                        Check again after more business data is collected.
                      </p>
                    )}
                    {intelligenceBrief.output.daily_actions?.some(
                      (action) => action.approval_required,
                    ) ? (
                      <p className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 p-3 text-sm leading-6 text-amber-100">
                        Review and approve these actions before anyone carries them out.
                      </p>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="mt-5 rounded-md border border-dashed border-violet-400/20 bg-[#111214]/80 p-4">
                  <p className="text-sm font-medium text-white">
                    No explanation has been prepared for this business yet.
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    Choose “Build today’s plan” to turn the current approved recommendations
                    into a short business-owner plan.
                  </p>
                </div>
              )}

              <section className="mt-5 border-t border-violet-500/15 pt-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="max-w-2xl">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-200/70">
                      Draft help for this action
                    </p>
                    <h3 className="mt-1 text-lg font-semibold text-white">
                      Get useful wording without starting from scratch
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Choose what you want written. InsightOS uses only this saved action
                      and the business information already on file. Review every draft
                      before using it.
                    </p>
                  </div>
                  <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-100">
                    Draft only - nothing is published
                  </span>
                </div>

                {selectedDraftAction ? (
                  <>
                    <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
                      <label className="flex-1 text-sm text-zinc-300">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                          What should be written?
                        </span>
                        <select
                          value={activeDraftType}
                          onChange={(event) =>
                            setSelectedDraftType(event.target.value as GovernedDraftType)
                          }
                          className="min-h-11 w-full rounded-md border border-[#303137] bg-[#111214] px-3 py-2 text-sm text-white outline-none focus:border-violet-400/50"
                        >
                          {selectedDraftAction.draft_types.map((item) => (
                            <option key={item.draft_type} value={item.draft_type}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                        {activeDraftTypeOption?.description ? (
                          <span className="mt-2 block text-xs leading-5 text-zinc-500">
                            {activeDraftTypeOption.description}
                          </span>
                        ) : null}
                      </label>
                      <button
                        type="button"
                        onClick={() => void generateActionDraft(Boolean(currentActionDraft))}
                        disabled={!activeDraftType || busyAction !== ""}
                        className="min-h-11 rounded-md border border-violet-400/30 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busyAction === "generate-action-draft"
                          ? "Writing..."
                          : currentActionDraft
                            ? "Create another version"
                            : "Create draft"}
                      </button>
                    </div>

                    {currentActionDraft ? (
                      <article className="mt-5 rounded-md bg-[#111214]/90 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <span
                            className={`text-xs font-semibold ${
                              currentActionDraft.output.draft_state === "ready"
                                ? "text-emerald-300"
                                : "text-amber-200"
                            }`}
                          >
                            {currentActionDraft.output.draft_state === "ready"
                              ? "Ready for your review"
                              : currentActionDraft.output.draft_state ===
                                  "not_enough_information"
                                ? "More business information is needed"
                                : "Writing help is temporarily unavailable"}
                          </span>
                          <span className="text-xs text-zinc-500">
                            {formatRelativeTime(currentActionDraft.created_at)}
                          </span>
                        </div>

                        <div className="mt-4 grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
                          <div>
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                {currentActionDraft.output.title_label ||
                                  activeDraftTypeOption?.title_label ||
                                  "Suggested heading"}
                              </p>
                              <button
                                type="button"
                                onClick={() =>
                                  void navigator.clipboard.writeText(
                                    currentActionDraft.output.title,
                                  )
                                }
                                className="text-xs text-violet-200 hover:text-white"
                              >
                                Copy
                              </button>
                            </div>
                            <p className="mt-2 text-base font-medium leading-7 text-white">
                              {currentActionDraft.output.title}
                            </p>
                          </div>
                          <div>
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                {currentActionDraft.output.body_label ||
                                  activeDraftTypeOption?.body_label ||
                                  "Suggested wording"}
                              </p>
                              <button
                                type="button"
                                onClick={() =>
                                  void navigator.clipboard.writeText(
                                    currentActionDraft.output.body,
                                  )
                                }
                                className="text-xs text-violet-200 hover:text-white"
                              >
                                Copy
                              </button>
                            </div>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-200">
                              {currentActionDraft.output.body}
                            </p>
                          </div>
                        </div>

                        {currentActionDraft.output.evidence_details?.length ? (
                          <details className="mt-4 border-t border-[#26272c] pt-3">
                            <summary className="cursor-pointer text-sm font-medium text-zinc-300">
                              See what this draft used
                            </summary>
                            <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-400">
                              {currentActionDraft.output.evidence_details.map((evidence) => (
                                <li key={evidence.evidence_id}>
                                  <span className="font-medium text-white">
                                    {evidence.label}
                                  </span>
                                  {evidence.detail ? ` - ${evidence.detail}` : ""}
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : null}

                        <p className="mt-4 border-l-2 border-amber-400/40 pl-3 text-sm leading-6 text-amber-100">
                          Review names, services, timing, and business details before you copy
                          this anywhere. Nothing was changed or published.
                        </p>
                      </article>
                    ) : (
                      <p className="mt-4 text-sm text-zinc-500">
                        No draft has been created for this action yet.
                      </p>
                    )}
                  </>
                ) : (
                  <p className="mt-4 rounded-md border border-dashed border-[#303137] px-4 py-3 text-sm leading-6 text-zinc-400">
                    Draft help is not available for this action yet. You can still use the
                    saved checklist above.
                  </p>
                )}
              </section>

              <section className="mt-5 border-t border-violet-500/15 pt-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="max-w-2xl">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-200/70">
                      Ask about this location
                    </p>
                    <h3 className="mt-1 text-lg font-semibold text-white">
                      Get an answer from the saved facts
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Ask why an action matters, what number supports it, or what is still
                      unknown. Answers cannot change your website or add new actions.
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      Do not include passwords, API keys, customer details, or other private information.
                    </p>
                  </div>
                  <span className="text-xs text-zinc-500">
                    One question uses one explanation
                  </span>
                </div>

                <form
                  className="mt-4 flex flex-col gap-3 sm:flex-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void askEvidenceQuestion();
                  }}
                >
                  <label className="sr-only" htmlFor="evidence-question">
                    Ask a question about this location
                  </label>
                  <input
                    id="evidence-question"
                    value={questionInput}
                    onChange={(event) => setQuestionInput(event.target.value)}
                    maxLength={500}
                    placeholder="Why is this the first thing I should work on?"
                    className="min-h-11 flex-1 rounded-md border border-[#303137] bg-[#111214] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-violet-400/50"
                  />
                  <button
                    type="submit"
                    disabled={
                      !selectedCampaignId ||
                      questionInput.trim().length < 3 ||
                      busyAction !== ""
                    }
                    className="min-h-11 rounded-md border border-violet-400/30 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "ask-evidence-question"
                      ? "Checking saved facts..."
                      : "Answer from my data"}
                  </button>
                </form>

                <div className="mt-3 flex flex-wrap gap-2" aria-label="Example questions">
                  {[
                    "Why is this the first step?",
                    "What number supports this?",
                    "What is still unknown?",
                  ].map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => setQuestionInput(question)}
                      className="rounded-full border border-[#303137] px-3 py-1.5 text-xs text-zinc-300 hover:border-violet-400/40 hover:text-white"
                    >
                      {question}
                    </button>
                  ))}
                </div>

                {evidenceAnswers[0] ? (
                  <article className="mt-5 rounded-md bg-[#111214]/90 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span
                        className={`text-xs font-semibold ${
                          evidenceAnswers[0].output.answer_state === "answered"
                            ? "text-emerald-300"
                            : "text-amber-200"
                        }`}
                      >
                        {evidenceAnswers[0].output.answer_state === "answered"
                          ? "Answered from saved information"
                          : evidenceAnswers[0].output.answer_state ===
                              "not_enough_information"
                            ? "More information is needed"
                            : "Answer is temporarily unavailable"}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {formatRelativeTime(evidenceAnswers[0].created_at)}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-medium text-zinc-400">
                      {evidenceAnswers[0].output.question}
                    </p>
                    <p className="mt-2 text-base leading-7 text-white">
                      {evidenceAnswers[0].output.answer}
                    </p>

                    {evidenceAnswers[0].output.related_actions?.length ? (
                      <div className="mt-4 border-l-2 border-violet-400/40 pl-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                          Related saved action
                        </p>
                        <p className="mt-1 text-sm font-medium text-zinc-100">
                          {simplifyCustomerCopy(
                            evidenceAnswers[0].output.related_actions[0].display_name ||
                              undefined,
                            { fallback: "Open the current action plan" },
                          )}
                        </p>
                      </div>
                    ) : null}

                    {evidenceAnswers[0].output.evidence_details?.length ? (
                      <details className="mt-4 border-t border-[#26272c] pt-3">
                        <summary className="cursor-pointer text-sm font-medium text-zinc-300">
                          See the saved information behind this answer
                        </summary>
                        <ul className="mt-3 space-y-3">
                          {evidenceAnswers[0].output.evidence_details.map((evidence) => (
                            <li key={evidence.evidence_id} className="text-sm text-zinc-300">
                              <span className="font-medium text-white">{evidence.label}</span>
                              {evidence.detail ? (
                                <span className="mt-1 block leading-6 text-zinc-400">
                                  {evidence.detail}
                                </span>
                              ) : null}
                              {evidence.captured_at ? (
                                <span className="mt-1 block text-xs text-zinc-500">
                                  Saved {formatRelativeTime(evidence.captured_at)}
                                </span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}

                    {evidenceAnswers[0].output.uncertainties?.length ? (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-sm font-medium text-zinc-300">
                          What this answer cannot confirm
                        </summary>
                        <ul className="mt-2 space-y-1 text-sm leading-6 text-zinc-400">
                          {evidenceAnswers[0].output.uncertainties.map((item) => (
                            <li key={item}>- {item}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </article>
                ) : (
                  <p className="mt-4 text-sm text-zinc-500">
                    No questions have been asked for this location yet.
                  </p>
                )}

                {evidenceAnswers.length > 1 ? (
                  <details className="mt-4 text-sm text-zinc-400">
                    <summary className="cursor-pointer font-medium text-zinc-300">
                      See {evidenceAnswers.length - 1} earlier answer
                      {evidenceAnswers.length === 2 ? "" : "s"}
                    </summary>
                    <div className="mt-3 space-y-3">
                      {evidenceAnswers.slice(1).map((item) => (
                        <div key={item.id} className="border-l border-[#303137] pl-3">
                          <p className="font-medium text-zinc-300">{item.output.question}</p>
                          <p className="mt-1 leading-6 text-zinc-500">{item.output.answer}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                ) : null}
              </section>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-violet-500/15 pt-4 text-xs text-zinc-500">
                <span>
                  Recommendations stay unchanged until you review them. Automatic changes are off.
                </span>
                {intelligenceRuntime?.configured &&
                intelligenceAllowance?.remaining !== undefined ? (
                  <span>
                    {intelligenceAllowance.remaining} refreshed plans remaining this month
                  </span>
                ) : (
                  <span>
                    Fresh wording is unavailable; the saved action plan remains available
                  </span>
                )}
              </div>
            </details>

            <details className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.3)]">
              <summary className="cursor-pointer list-none">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  Progress
                </p>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <h2 className="text-base font-semibold text-white">
                    {recommendationState.status}
                  </h2>
                  <span className="text-xs text-zinc-400">See progress details</span>
                </div>
              </summary>
              <p className="mt-4 border-t border-[#26272c] pt-4 text-sm leading-6 text-zinc-300">
                See what still needs checking, what is ready to do, and what has already been handled.
              </p>
              <div className="mt-4 grid gap-4 xl:grid-cols-3">
                {[recommendationState, executionState, setupBlockerState]
                  .map((state) =>
                    state === setupBlockerState && !selectedExecution ? null : state,
                  )
                  .filter(Boolean)
                  .map((state) => (
                    <div
                      key={state?.label}
                      className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            {state?.label}
                          </p>
                          <h3 className="mt-2 text-base font-semibold text-white">{state?.status}</h3>
                        </div>
                        <span
                          className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${getWorkflowToneClass(
                            state?.tone || "warning",
                          )}`}
                        >
                          {state?.status}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-zinc-300">{state?.detail}</p>
                      <p className="mt-3 text-sm font-medium text-zinc-100">Next: {state?.nextStep}</p>
                    </div>
                  ))}
              </div>
            </details>

            <details className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <summary className="flex cursor-pointer list-none items-center gap-3 text-sm font-semibold text-zinc-200">
                <ProductIcon name="info" size={16} className="text-zinc-500" />
                All actions and supporting details
                <span className="ml-auto text-xs font-normal text-zinc-500">
                  Open the full list only when needed
                </span>
              </summary>
              <div className="mt-5 space-y-5 border-t border-[#26272c] pt-5">
            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Active actions"
                value={String(sortedRecommendations.length)}
                summary="Duplicate and cleared records are removed from this location's working plan."
              />
              <KpiCard
                label="High priority"
                value={String(highPriorityCount)}
                summary="These are the items most likely to need attention first."
                tone="highlight"
              />
              <KpiCard
                label="Checked"
                value={String(readyCount)}
                summary="These actions were checked or chosen as likely next steps."
              />
              <KpiCard
                label="Finished or cleared"
                value={`${queuedCount + archivedCount}`}
                summary="This includes actions already planned or intentionally removed from the active list."
              />
            </div>

            {sortedRecommendations.length === 0 ? (
              <EmptyState
                title="No next steps are ready yet"
                summary="Refresh after more crawl, ranking, or local data is available for this business."
                actionLabel="Refresh opportunities"
                onAction={() => void refreshCampaignData(selectedCampaignId)}
              />
            ) : (
              <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
                <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Choose an action
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Complete action list
                    </h2>
                    <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                      Choose any active action to see its reason, what we found, and the plan.
                    </p>
                  </div>

                  <div className="space-y-3">
                    {sortedRecommendations.map((recommendation) => {
                      const isSelected = recommendation.id === selectedRecommendation?.id;
                      return (
                        <button
                          key={recommendation.id}
                          onClick={() => setSelectedRecommendationId(recommendation.id)}
                          className={`w-full rounded-md border p-4 text-left shadow-[0_0_30px_rgba(0,0,0,0.4)] transition ${
                            isSelected
                              ? "border-accent-500/30 bg-accent-500/10"
                              : "border-[#26272c] bg-[#111214]"
                          }`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="text-base font-semibold text-white">
                                {getRecommendationTitle(recommendation)}
                              </p>
                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                {describeRecommendationReason(recommendation.rationale)}
                              </p>
                            </div>
                            <span
                              className={`rounded-md border px-2 py-1 text-xs font-medium ${getPriorityTone(recommendation.risk_tier)}`}
                            >
                              {getPriorityLabel(recommendation.risk_tier)}
                            </span>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {recommendation.action_plan?.work_item ? (
                              <>
                                <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-200">
                                  {getCadenceLabel(recommendation.action_plan.work_item.cadence)}
                                </span>
                                <span className="rounded-md border border-accent-500/20 bg-accent-500/10 px-2 py-1 text-xs font-medium text-zinc-100">
                                  {getWorkProgress(recommendation).label}
                                </span>
                              </>
                            ) : (
                              <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-300">
                                Plan details coming soon
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>

                <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                  {selectedRecommendation ? (
                    <>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Action details
                          </p>
                          <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                            {getRecommendationTitle(selectedRecommendation)}
                          </h2>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${getPriorityTone(selectedRecommendation.risk_tier)}`}
                          >
                            {getPriorityLabel(selectedRecommendation.risk_tier)}
                          </span>
                          {selectedRecommendation.action_plan?.work_item ? (
                            <>
                              <span className="rounded-md border border-[#26272c] bg-[#111214] px-2 py-1 text-xs font-medium text-zinc-200">
                                {getCadenceLabel(selectedRecommendation.action_plan.work_item.cadence)}
                              </span>
                              <span className="rounded-md border border-accent-500/20 bg-accent-500/10 px-2 py-1 text-xs font-medium text-zinc-100">
                                {getWorkProgress(selectedRecommendation).label}
                              </span>
                            </>
                          ) : null}
                        </div>
                      </div>

                      <div className="mt-5 grid gap-4 md:grid-cols-3">
                        <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            What needs attention
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                            {describeRecommendationReason(selectedRecommendation.rationale)}
                          </p>
                        </div>
                        <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Why this is prioritized
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                            {getImpactLabel(
                              selectedRecommendation.confidence_score ||
                                selectedRecommendation.confidence ||
                                0,
                            )}
                            . {selectedRecommendation.risk_tier && selectedRecommendation.risk_tier >= 3
                              ? "Handle this one first because it needs attention now."
                              : "This is worth doing, but it is not the most urgent item."}
                          </p>
                        </div>
                        <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            What to do next
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {simplifyCustomerCopy(
                                selectedRecommendation.action_plan?.steps?.[0] ||
                                  primaryAction?.summary ||
                                  "Check what we found, then decide whether to keep this action on your list.",
                                { fallback: "Open the plan and follow the first step." },
                              )}
                          </p>
                          <p className="mt-3 text-xs uppercase tracking-[0.14em] text-zinc-500">
                            {recommendationState
                              ? `${recommendationState.label}. ${recommendationState.detail}`
                              : "Review the current recommendation state before moving it forward."}
                          </p>
                        </div>
                      </div>

                      {selectedRecommendation.action_plan ? (
                        <section className="mt-5 rounded-md border border-accent-500/20 bg-accent-500/5 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-4">
                            <div className="max-w-2xl">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">
                                Practical plan
                              </p>
                              <p className="mt-2 text-sm leading-6 text-zinc-200">
                                {simplifyCustomerCopy(
                                  selectedRecommendation.action_plan.why_it_matters,
                                  { fallback: "This action can help more customers trust the business." },
                                )}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2 text-xs text-zinc-300">
                              <span className="rounded-md border border-[#34353b] bg-[#111214] px-2.5 py-1.5">
                                {getCadenceLabel(selectedRecommendation.action_plan.work_item?.cadence)}
                              </span>
                              <span className="rounded-md border border-[#34353b] bg-[#111214] px-2.5 py-1.5">
                                {getWorkProgress(selectedRecommendation).label}
                              </span>
                              <span className="rounded-md border border-[#34353b] bg-[#111214] px-2.5 py-1.5">
                                Check results after {selectedRecommendation.action_plan.observation_window_days} days
                              </span>
                            </div>
                          </div>
                          {selectedRecommendation.action_plan.work_item ? (
                            <div className="mt-4 space-y-2">
                              {selectedRecommendation.action_plan.work_item.steps.map((step) => {
                                const isDone = step.status === "done";
                                const actionKey = `${selectedRecommendation.action_plan?.work_item?.id}:${step.id}`;
                                return (
                                  <button
                                    key={step.id}
                                    type="button"
                                    aria-pressed={isDone}
                                    onClick={() =>
                                      void updateChecklistStep(
                                        selectedRecommendation.id,
                                        selectedRecommendation.action_plan!.work_item!.id,
                                        step.id,
                                        step.status,
                                      )
                                    }
                                    disabled={busyAction === actionKey}
                                    className={`flex w-full items-start gap-3 rounded-md border p-3 text-left transition disabled:cursor-wait disabled:opacity-60 ${
                                      isDone
                                        ? "border-emerald-500/25 bg-emerald-500/10"
                                        : "border-[#2a2b31] bg-[#111214] hover:border-accent-500/35"
                                    }`}
                                  >
                                    <span
                                      aria-hidden="true"
                                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border text-xs font-bold ${
                                        isDone
                                          ? "border-emerald-400 bg-emerald-500 text-[#07130d]"
                                          : "border-zinc-600 bg-[#18191c] text-zinc-500"
                                      }`}
                                    >
                                      {isDone ? "✓" : step.position}
                                    </span>
                                    <span>
                                      <span className={`block text-sm leading-6 ${isDone ? "text-zinc-500 line-through" : "text-zinc-200"}`}>
                                        {simplifyCustomerCopy(step.instruction, {
                                          fallback: "Complete this step.",
                                        })}
                                      </span>
                                      <span className="mt-1 block text-xs text-zinc-500">
                                        {busyAction === actionKey
                                          ? "Saving..."
                                          : isDone
                                            ? "Done — select to reopen"
                                            : "Select when finished"}
                                      </span>
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="mt-4 grid gap-2 md:grid-cols-3">
                              {selectedRecommendation.action_plan.steps.map((step, index) => (
                                <div
                                  key={`${selectedRecommendation.action_plan?.action_id}:${index}`}
                                  className="rounded-md border border-[#2a2b31] bg-[#111214] p-3"
                                >
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                                    Step {index + 1}
                                  </p>
                                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                                    {simplifyCustomerCopy(step, { fallback: "Complete this step." })}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                          <p className="mt-3 text-xs text-zinc-500">
                            Your progress is saved and follows you across devices.
                          </p>
                        </section>
                      ) : null}

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                          What we found
                        </p>
                        {selectedRecommendation.evidence?.length ? (
                          <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                            {selectedRecommendation.evidence.map((item) => (
                              <li key={item}>• {formatEvidence(item)}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-3 text-sm leading-6 text-zinc-300">
                            InsightOS needs more information before it can explain why this action belongs here.
                          </p>
                        )}
                      </div>

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <details>
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-zinc-200">
                            <span>More about this action</span>
                            <span className="text-xs font-normal text-zinc-500">Show</span>
                          </summary>
                          <div className="mt-4 grid gap-4 border-t border-[#26272c] pt-4 md:grid-cols-4">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Support for this action
                            </p>
                            <p className="mt-2 text-sm text-zinc-200">
                              {getImpactLabel(
                                selectedRecommendation.confidence_score ||
                                  selectedRecommendation.confidence ||
                                  0,
                              )}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Information checked
                            </p>
                            <p className="mt-2 text-sm text-zinc-200">
                              {getEngineSourceLabel(selectedRecommendation.engine_source)}
                            </p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              Saved business information
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Status
                            </p>
                            <p className="mt-2 text-sm text-zinc-200">
                              {getStatusLabel(selectedRecommendation.status)}
                            </p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              {recommendationState?.nextStep}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Added
                            </p>
                            <p className="mt-2 text-sm text-zinc-200">
                              {formatRelativeTime(selectedRecommendation.created_at)}
                            </p>
                          </div>
                          </div>
                        </details>

                        <div className="mt-4 flex flex-wrap gap-3">
                          {primaryAction ? (
                            <button
                              onClick={() =>
                                void transitionRecommendation(
                                  selectedRecommendation.id,
                                  primaryAction.targetState,
                                  `${describeType(selectedRecommendation.recommendation_type)} moved to ${getStatusLabel(primaryAction.targetState)}.`,
                                )
                              }
                              disabled={busyAction !== ""}
                              className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {busyAction === `${selectedRecommendation.id}:${primaryAction.targetState}`
                                ? "Updating..."
                                : primaryAction.label}
                            </button>
                          ) : null}

                          {canMeasureOutcome(selectedRecommendation.status) ? (
                            <button
                              onClick={() =>
                                void measureRecommendationOutcome(selectedRecommendation.id)
                              }
                              disabled={busyAction !== ""}
                              className="rounded-md border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {busyAction === `${selectedRecommendation.id}:measure-outcome`
                                ? "Measuring..."
                                : "Check progress"}
                            </button>
                          ) : null}

                          {shouldAllowArchive(selectedRecommendation.status) ? (
                            <button
                              onClick={() =>
                                void transitionRecommendation(
                                  selectedRecommendation.id,
                                  "ARCHIVED",
                                  `${describeType(selectedRecommendation.recommendation_type)} was removed from the active list.`,
                                )
                              }
                              disabled={busyAction !== ""}
                              className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {busyAction === `${selectedRecommendation.id}:ARCHIVED`
                                ? "Updating..."
                                : "Remove from list"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </>
                  ) : (
                    <EmptyState
                      title="No recommendation selected"
                      summary="Choose an action from the list to see why it matters and what to do next."
                      actionLabel="Return to dashboard"
                      onAction={() => router.push("/dashboard")}
                    />
                  )}
                </section>
              </div>
            )}
              </div>
            </details>

            <details className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-white">
                Advanced workflow tools
                <span className="text-xs font-normal text-zinc-500">
                  Progress history and website change controls
                </span>
              </summary>
              <div className="mt-5 space-y-6 border-t border-[#26272c] pt-5">
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Outcome history
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    What changed after recommendations were chosen
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    InsightOS compares saved opportunity-score checkpoints. This shows whether the
                    overall score moved; it does not claim that one recommendation caused the
                    change.
                  </p>
                </div>
                <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-100">
                  Observation-only learning
                </span>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-4">
                <KpiCard
                  label="Measurements"
                  value={String(outcomeHistory?.count || 0)}
                  summary="Saved before-and-after score checkpoints for this business."
                />
                <KpiCard
                  label="Improved"
                  value={String(outcomeHistory?.summary?.improved_count || 0)}
                  summary="Measurements where the saved opportunity score increased."
                />
                <KpiCard
                  label="No clear change"
                  value={String(outcomeHistory?.summary?.unchanged_count || 0)}
                  summary="Measurements where the score stayed effectively the same."
                />
                <KpiCard
                  label="Declined"
                  value={String(outcomeHistory?.summary?.declined_count || 0)}
                  summary="Measurements that need review because the saved score decreased."
                  tone={
                    (outcomeHistory?.summary?.declined_count || 0) > 0
                      ? "highlight"
                      : "default"
                  }
                />
              </div>

              {outcomeHistory?.items?.length ? (
                <div className="mt-5 space-y-3">
                  {outcomeHistory.items.map((outcome) => (
                    <button
                      key={outcome.id}
                      onClick={() => setSelectedRecommendationId(outcome.recommendation_id)}
                      className="w-full rounded-md border border-[#26272c] bg-[#111214] p-4 text-left"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-white">
                            {describeType(outcome.recommendation_type)}
                          </p>
                          <p className="mt-1 text-sm text-zinc-300">
                            {outcome.metric_label || "Opportunity score"}:{" "}
                            {Number(outcome.metric_before || 0).toFixed(1)} →{" "}
                            {Number(outcome.metric_after || 0).toFixed(1)} (
                            {formatScoreDelta(outcome.delta)})
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${getOutcomeTone(outcome.direction)}`}
                          >
                            {getOutcomeDirectionLabel(outcome.direction)}
                          </span>
                          <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-300">
                            {formatRelativeTime(outcome.measured_at)}
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="mt-5 rounded-md border border-dashed border-[#34363c] bg-[#111214] p-5">
                  <p className="text-sm font-medium text-white">
                    No outcomes have been measured yet.
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    Review and choose a recommendation first. After work has had time to affect the
                    saved campaign signals, use “Measure saved-data progress” on that recommendation.
                  </p>
                </div>
              )}

              <p className="mt-4 text-xs uppercase tracking-[0.14em] text-zinc-500">
                Policy updates disabled · Causal claims disabled ·{" "}
                {outcomeHistory?.learning?.observations_recorded || 0} observations recorded
              </p>
            </section>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              {WORDPRESS_EXECUTION_SETUP_UI_ENABLED ? (
                <div className="mb-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Connect WordPress
                      </p>
                      <h3 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                        Let InsightOS make approved website updates
                      </h3>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                        {wordpressSetup?.status_summary ||
                          "Connect the website once, then review every suggested change before it runs."}
                      </p>
                      <p className="mt-2 text-sm text-zinc-400">
                        Your WordPress administrator password is never shared with InsightOS.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {wordpressSetup ? (
                        <button
                          type="button"
                          onClick={() => void downloadWordPressPlugin()}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-accent-500/40 bg-accent-500/10 px-3 py-1.5 text-xs font-medium text-accent-100 disabled:opacity-50"
                        >
                          {busyAction === "wordpress-plugin-download"
                            ? "Preparing download..."
                            : wordpressSetup.configured
                              ? "Download latest plugin"
                              : "Download WordPress plugin"}
                        </button>
                      ) : null}
                      {wordpressSetup?.configured && wordpressSetup.mode !== "test" ? (
                        <button
                          type="button"
                          onClick={() => void testWordPressConnection()}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-sky-500/40 px-3 py-1.5 text-xs font-medium text-sky-100 disabled:opacity-50"
                        >
                          {busyAction === "wordpress-connection-check"
                            ? "Testing connection…"
                            : wordpressSetup.execution_ready
                              ? "Test connection again"
                              : "Test connection"}
                        </button>
                      ) : null}
                      {wordpressSetup?.mode !== "test" ? (
                        <button
                          type="button"
                          onClick={() => void createWordPressPairingCode()}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-accent-500/40 bg-accent-500/10 px-3 py-1.5 text-xs font-medium text-accent-100 disabled:opacity-50"
                        >
                          {busyAction === "wordpress-pairing"
                            ? "Creating code…"
                            : wordpressSetup?.credential_source === "site"
                              ? "Replace connection key"
                              : "Create pairing code"}
                        </button>
                      ) : null}
                      {wordpressSetup?.credential_source === "site" ? (
                        <button
                          type="button"
                          onClick={() => void disconnectWordPress()}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-rose-500/30 px-3 py-1.5 text-xs font-medium text-rose-100 disabled:opacity-50"
                        >
                          {busyAction === "wordpress-disconnect" ? "Disconnecting…" : "Disconnect"}
                        </button>
                      ) : null}
                      <span
                        className={`rounded-md border px-2 py-1 text-xs font-medium ${
                          wordpressSetup?.configured
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
                            : "border-rose-500/20 bg-rose-500/10 text-rose-100"
                        }`}
                      >
                        {wordpressSetup?.configured ? "Configured" : "Not configured"}
                      </span>
                      <span
                        className={`rounded-md border px-2 py-1 text-xs font-medium ${getWordPressHealthTone(
                          wordpressSetup,
                        )}`}
                      >
                        {getWordPressHealthLabel(wordpressSetup)}
                      </span>
                      <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-200">
                        {wordpressSetup?.mode === "test" ? "Test mode" : "Live mode"}
                      </span>
                    </div>
                  </div>

                  {wordpressSetup?.mode !== "test" ? (
                    <details
                      className="mt-4 rounded-md border border-[#26272c] bg-[#141518] p-4"
                      open={!wordpressSetup?.configured}
                    >
                      <summary className="cursor-pointer text-sm font-semibold text-white">
                        How to install and connect WordPress
                      </summary>
                      <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-zinc-300">
                        <li>Download the plugin ZIP above. Do not unzip it.</li>
                        <li>
                          Sign in to WordPress, open Plugins, choose Add Plugin, then Upload Plugin.
                        </li>
                        <li>Choose the ZIP file, install it, and select Activate Plugin.</li>
                        <li>Return here and choose Create pairing code.</li>
                        <li>
                          In WordPress, open Settings, choose InsightOS, paste the code, and connect the
                          website.
                        </li>
                        <li>Return here and choose Test connection.</li>
                      </ol>
                      <p className="mt-4 text-xs leading-5 text-zinc-500">
                        {wordpressSetup.plugin_package
                          ? `Download version ${wordpressSetup.plugin_package.version}. Package check: ${wordpressSetup.plugin_package.sha256.slice(0, 12)}...`
                          : "The download contains only the InsightOS plugin. It never contains your website password or pairing code."}
                      </p>
                    </details>
                  ) : null}

                  {wordpressPairing?.campaign_id === selectedCampaignId ? (
                    <div className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-200">
                        One-time pairing code
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-3">
                        <code className="rounded-md border border-accent-500/30 bg-[#111214] px-4 py-3 text-lg font-semibold tracking-[0.12em] text-white">
                          {wordpressPairing.pairing_code}
                        </code>
                        <button
                          type="button"
                          onClick={() => void navigator.clipboard.writeText(wordpressPairing.pairing_code)}
                          className="rounded-md border border-[#34363c] px-3 py-2 text-xs font-medium text-zinc-100"
                        >
                          Copy code
                        </button>
                      </div>
                      <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-zinc-200">
                        {wordpressPairing.instructions.map((instruction) => (
                          <li key={instruction}>{instruction}</li>
                        ))}
                      </ol>
                      <p className="mt-3 text-xs text-zinc-400">
                        This code expires {formatRelativeTime(wordpressPairing.expires_at)} and works only for {wordpressPairing.site_url}.
                      </p>
                    </div>
                  ) : null}

                  {wordpressSetup?.credential_source === "site" ? (
                    <div className="mt-4 rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Website pages
                          </p>
                          <h4 className="mt-1.5 text-base font-semibold text-white">
                            {wordpressInventory?.has_inventory
                              ? `${wordpressInventory.summary.pages_found} pages are ready to review`
                              : "See what is currently on the website"}
                          </h4>
                          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-zinc-300">
                            This reads page settings and revision fingerprints so future previews use the current website. It does not change anything.
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void syncWordPressContent()}
                          disabled={!wordpressSetup.execution_ready || busyAction !== ""}
                          className="rounded-md border border-sky-500/40 px-3 py-2 text-xs font-medium text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {busyAction === "wordpress-content-sync"
                            ? "Reading website pages…"
                            : wordpressInventory?.has_inventory
                              ? "Refresh page list"
                              : "Read website pages"}
                        </button>
                      </div>

                      {!wordpressSetup.execution_ready ? (
                        <p className="mt-3 text-xs text-amber-100">
                          Test the connection before reading the website pages.
                        </p>
                      ) : null}
                      {wordpressInventoryError ? (
                        <p className="mt-3 text-sm text-rose-200">{wordpressInventoryError}</p>
                      ) : null}

                      {wordpressInventory?.has_inventory ? (
                        <>
                          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            {[
                              ["Pages found", wordpressInventory.summary.pages_found],
                              ["Published", wordpressInventory.summary.published],
                              ["Need a description", wordpressInventory.summary.missing_description],
                              ["Have structured details", wordpressInventory.summary.with_schema],
                            ].map(([label, value]) => (
                              <div key={String(label)} className="border-l border-[#34363c] pl-3">
                                <p className="text-xs text-zinc-500">{label}</p>
                                <p className="mt-1 text-lg font-semibold text-white">{value}</p>
                              </div>
                            ))}
                          </div>
                          <details className="mt-4 border-t border-[#26272c] pt-4">
                            <summary className="cursor-pointer text-sm font-medium text-zinc-200">
                              View website page list
                            </summary>
                            <div className="mt-3 divide-y divide-[#26272c]">
                              {wordpressInventory.items.slice(0, 100).map((item) => (
                                <div key={item.id} className="grid gap-2 py-3 lg:grid-cols-[1fr_auto]">
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-medium text-white">
                                      {item.title || item.url}
                                    </p>
                                    <p className="mt-1 truncate text-xs text-zinc-500">{item.url}</p>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                                    <span>{toTitleCase(item.publication_status)}</span>
                                    <span>{item.word_count.toLocaleString()} words</span>
                                    <span>{item.meta_description ? "Description saved" : "Needs a description"}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </details>
                          <p className="mt-3 text-xs text-zinc-500">
                            Last read {formatRelativeTime(wordpressInventory.last_synced_at)}.
                            {wordpressInventory.truncated
                              ? ` Showing the first ${wordpressInventory.summary.pages_found} of ${wordpressInventory.source_total_count || "the"} pages.`
                              : ""}
                          </p>
                        </>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Website connection
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup?.credential_source === "site"
                          ? "Paired to this website"
                          : wordpressSetup?.configured
                            ? "Older connection saved"
                            : "Not connected"}
                      </p>
                    </div>
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Plugin version
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup?.plugin_version
                          ? `Version ${wordpressSetup.plugin_version}`
                          : "No plugin version reported yet"}
                      </p>
                    </div>
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Last connection check
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup?.last_success_at
                          ? formatRelativeTime(wordpressSetup.last_success_at)
                          : "Not checked yet"}
                      </p>
                    </div>
                  </div>

                  {wordpressSetupError ? (
                    <div className="mt-4 rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
                      {wordpressSetupError}
                    </div>
                  ) : null}

                  {wordpressSetup?.missing_requirements?.length ? (
                    <div className="mt-4 rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        What is missing
                      </p>
                      <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                        {wordpressSetup.missing_requirements.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Execution inbox
                  </p>
                  <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                    Approval, delivery, and rollback
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    Review the execution queue for the active business, approve or reject work,
                    and use the console to run, retry, cancel, or roll back steps when needed.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <select
                    value={executionStatusFilter}
                    onChange={(event) => {
                      setExecutionStatusFilter(event.target.value);
                      setNotice("");
                    }}
                    className="rounded-md border border-[#26272c] bg-[#111214] px-3 py-2 text-sm text-zinc-100 outline-none"
                  >
                    <option value="all">All statuses</option>
                    <option value="pending">Awaiting approval</option>
                    <option value="scheduled">Ready to run</option>
                    <option value="running">Running</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="rolled_back">Rolled back</option>
                  </select>
                  <button
                    onClick={() => void loadExecutions(selectedCampaignId)}
                    disabled={!selectedCampaignId || busyAction !== ""}
                    className="rounded-md border border-[#26272c] bg-[#111214] px-3 py-2 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Refresh inbox
                  </button>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-3">
                <KpiCard
                  label="Awaiting approval"
                  value={String(pendingExecutionsCount)}
                  summary="These execution steps still need an operator decision."
                />
                <KpiCard
                  label="Completed"
                  value={String(completedExecutionsCount)}
                  summary="These execution steps finished and can be reviewed for outcomes."
                />
                <KpiCard
                  label="Needs attention"
                  value={String(failedExecutionsCount)}
                  summary="These execution steps failed, were rejected, or were canceled."
                  tone="highlight"
                />
              </div>

              {executions.length === 0 ? (
                <div className="mt-5">
                  <EmptyState
                    title="No executions in this inbox yet"
                    summary="Execution rows appear here after approved recommendations are scheduled for delivery."
                    actionLabel="Refresh inbox"
                    onAction={() => void loadExecutions(selectedCampaignId)}
                  />
                </div>
              ) : (
                <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
                  <section className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <div className="mb-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Queue
                      </p>
                      <h3 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                        Execution inbox
                      </h3>
                    </div>

                    <div className="space-y-3">
                      {executions.map((execution) => {
                        const isSelected = execution.id === selectedExecution?.id;
                        return (
                          <button
                            key={execution.id}
                            onClick={() => setSelectedExecutionId(execution.id)}
                            className={`w-full rounded-md border p-4 text-left transition ${
                              isSelected
                                ? "border-accent-500/30 bg-accent-500/10"
                                : "border-[#26272c] bg-[#141518]"
                            }`}
                          >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <p className="text-base font-semibold text-white">
                                  {describeExecutionType(execution.execution_type)}
                                </p>
                                <p className="mt-1 text-sm text-zinc-300">
                                  {getApprovalState(execution)}
                                </p>
                              </div>
                              <span
                                className={`rounded-md border px-2 py-1 text-xs font-medium ${getExecutionStatusTone(execution.status)}`}
                              >
                                {getExecutionStatusLabel(execution.status)}
                              </span>
                            </div>

                            <div className="mt-3 flex flex-wrap gap-2">
                              <span
                                className={`rounded-md border px-2 py-1 text-xs font-medium ${getRiskLevelTone(execution.risk_level)}`}
                              >
                                {toTitleCase(execution.risk_level || "medium")} risk
                              </span>
                              <span className="rounded-md border border-[#26272c] bg-[#111214] px-2 py-1 text-xs font-medium text-zinc-200">
                                Created {formatRelativeTime(execution.created_at)}
                              </span>
                              <span className="rounded-md border border-[#26272c] bg-[#111214] px-2 py-1 text-xs font-medium text-zinc-200">
                                {getMutationCount(execution)} mutations
                              </span>
                              {execution.attempt_count > 1 ? (
                                <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-100">
                                  {execution.attempt_count} attempts
                                </span>
                              ) : null}
                              {execution.rolled_back_at ? (
                                <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-400">
                                  Rolled back {formatRelativeTime(execution.rolled_back_at)}
                                </span>
                              ) : null}
                            </div>

                            <p className="mt-3 text-sm leading-6 text-zinc-300">
                              {execution.last_error
                                ? `Latest error: ${execution.last_error.replace(/_/g, " ")}`
                                : getExecutionSummary(execution)}
                            </p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              {getExecutionStateSummary(execution, {
                                getMutationCount,
                                canRollbackExecution,
                              }).nextStep}
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </section>

                  <section className="space-y-4 rounded-md border border-[#26272c] bg-[#111214] p-4">
                    {selectedExecution ? (
                      <>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Execution detail
                            </p>
                            <h3 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                              {describeExecutionType(selectedExecution.execution_type)}
                            </h3>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <span
                              className={`rounded-md border px-2 py-1 text-xs font-medium ${getExecutionStatusTone(selectedExecution.status)}`}
                            >
                              {getExecutionStatusLabel(selectedExecution.status)}
                            </span>
                            <span
                              className={`rounded-md border px-2 py-1 text-xs font-medium ${getRiskLevelTone(selectedExecution.risk_level)}`}
                            >
                              {toTitleCase(selectedExecution.risk_level || "medium")} risk
                            </span>
                          </div>
                        </div>

                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Approval state
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {getApprovalState(selectedExecution)}
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Result summary
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {getExecutionSummary(selectedExecution)}
                            </p>
                            <p className="mt-3 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              {executionState?.detail}
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Mutation count
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {getMutationCount(selectedExecution)} tracked changes
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Attempts
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {selectedExecution.attempt_count}{" "}
                              {selectedExecution.attempt_count === 1 ? "attempt" : "attempts"}
                            </p>
                          </div>
                        </div>

                        <div className="grid gap-4 md:grid-cols-3">
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Created
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {formatRelativeTime(selectedExecution.created_at)}
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Executed
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {selectedExecution.executed_at
                                ? formatRelativeTime(selectedExecution.executed_at)
                                : "Not yet executed"}
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Rolled back
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {selectedExecution.rolled_back_at
                                ? formatRelativeTime(selectedExecution.rolled_back_at)
                                : "No rollback recorded"}
                            </p>
                          </div>
                        </div>

                        {selectedExecution.last_error ? (
                          <div className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-400">
                              Last error
                            </p>
                            <p className="mt-2 text-sm leading-6 text-rose-100">
                              {selectedExecution.last_error.replace(/_/g, " ")}
                            </p>
                            <p className="mt-3 text-xs uppercase tracking-[0.14em] text-rose-200">
                              Next: {executionState?.nextStep}
                            </p>
                          </div>
                        ) : null}

                        {selectedExecution.result?.public_verification ? (
                          <div
                            className={`rounded-md border p-4 ${
                              selectedExecution.result.public_verification.passed
                                ? "border-emerald-500/20 bg-emerald-500/10"
                                : "border-rose-500/20 bg-rose-500/10"
                            }`}
                          >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <p
                                  className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${
                                    selectedExecution.result.public_verification.passed
                                      ? "text-emerald-300"
                                      : "text-rose-300"
                                  }`}
                                >
                                  Public website check
                                </p>
                                <h4 className="mt-1.5 text-base font-semibold text-white">
                                  {selectedExecution.result.public_verification.passed
                                    ? "The live website matches the approved changes"
                                    : "The live website does not match every approved change yet"}
                                </h4>
                                <p className="mt-2 text-sm leading-6 text-zinc-200">
                                  {selectedExecution.result.public_verification.checks_passed} of{" "}
                                  {selectedExecution.result.public_verification.checks_total} checks passed
                                  across {selectedExecution.result.public_verification.pages_checked}{" "}
                                  {selectedExecution.result.public_verification.pages_checked === 1
                                    ? "page"
                                    : "pages"}
                                  .
                                </p>
                              </div>
                              <span className="rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-zinc-100">
                                {selectedExecution.result.public_verification.passed
                                  ? "Verified"
                                  : "Needs attention"}
                              </span>
                            </div>
                            <div className="mt-4 space-y-2">
                              {selectedExecution.result.public_verification.results.map((check, index) => (
                                <div
                                  key={`${check.mutation_id || check.mutation_type || "check"}-${index}`}
                                  className="rounded-md border border-white/10 bg-[#111214]/70 p-3"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <p className="text-sm font-medium text-white">
                                      {check.passed ? "Passed" : "Not confirmed"}: {describeMutationType(check.mutation_type)}
                                    </p>
                                    {check.target_url ? (
                                      <a
                                        href={check.target_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-xs font-medium text-sky-200 hover:text-sky-100"
                                      >
                                        Open public page
                                      </a>
                                    ) : null}
                                  </div>
                                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">{check.message}</p>
                                </div>
                              ))}
                            </div>
                            {!selectedExecution.result.public_verification.passed ? (
                              <p className="mt-4 text-sm font-medium text-rose-100">
                                {selectedExecution.result.recovery_action ||
                                  "Review the failed checks. If the live page is wrong, use Rollback to restore the saved values."}
                              </p>
                            ) : null}
                          </div>
                        ) : null}

                        <ActionDrawer
                          title={describeExecutionType(selectedExecution.execution_type)}
                          summary={getExecutionSummary(selectedExecution)}
                          evidence={executionEvidence}
                          actions={
                            <>
                              {canApprovePreview(
                                selectedExecution,
                                dryRunPreview?.executionId === selectedExecution.id
                                  ? dryRunPreview.result.preview
                                  : null,
                              ) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "approve",
                                      `${describeExecutionType(selectedExecution.execution_type)} approved and kept in the execution queue.`,
                                      {
                                        preview_hash:
                                          dryRunPreview?.executionId === selectedExecution.id
                                            ? dryRunPreview.result.preview?.preview_hash
                                            : undefined,
                                      },
                                    )
                                  }
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:approve`
                                    ? "Approving..."
                                    : "Approve these changes"}
                                </button>
                              ) : null}

                              {canRejectExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "reject",
                                      `${describeExecutionType(selectedExecution.execution_type)} was rejected and removed from the pending queue.`,
                                    )
                                  }
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:reject`
                                    ? "Rejecting..."
                                    : "Reject"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canRunExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "run",
                                      `${describeExecutionType(selectedExecution.execution_type)} dry run completed.`,
                                      { dry_run: true },
                                    )
                                  }
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:run`
                                    ? "Running..."
                                    : requiresWordPressSetup(selectedExecution.execution_type)
                                      ? "Check website changes"
                                      : "Preview action"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canRunLiveExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "run",
                                      `${describeExecutionType(selectedExecution.execution_type)} sent to execution.`,
                                      { dry_run: false },
                                    )
                                  }
                                  disabled={busyAction !== "" || Boolean(liveExecutionDisabledReason)}
                                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:run`
                                    ? "Running..."
                                    : "Run now"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canRetryExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "retry",
                                      `${describeExecutionType(selectedExecution.execution_type)} retried and re-queued.`,
                                    )
                                  }
                                  disabled={busyAction !== "" || Boolean(liveExecutionDisabledReason)}
                                  className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:retry`
                                    ? "Retrying..."
                                    : "Retry"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canCancelExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "cancel",
                                      `${describeExecutionType(selectedExecution.execution_type)} was canceled before execution.`,
                                    )
                                  }
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:cancel`
                                    ? "Cancelling..."
                                    : "Cancel"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canRollbackExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "rollback",
                                      `${describeExecutionType(selectedExecution.execution_type)} rolled back using persisted mutations.`,
                                    )
                                  }
                                  disabled={busyAction !== "" || Boolean(liveExecutionDisabledReason)}
                                  className="rounded-md border border-rose-500/20 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:rollback`
                                    ? "Rolling back..."
                                    : "Rollback"}
                                </button>
                              ) : null}
                            </>
                          }
                        />

                        {liveExecutionDisabledReason ? (
                          <div className="rounded-md border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                            <p>Live execution is disabled: {liveExecutionDisabledReason}</p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-amber-200">
                              Next: {setupBlockerState.nextStep}
                            </p>
                          </div>
                        ) : null}

                        {dryRunPreview?.executionId === selectedExecution.id ? (
                          dryRunPreview.result.preview ? (
                            <div className="space-y-4 rounded-md border border-[#26272c] bg-[#141518] p-4">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                                    Website change preview
                                  </p>
                                  <h3 className="mt-2 text-lg font-semibold text-zinc-100">
                                    {dryRunPreview.result.preview.conflict_count
                                      ? "A problem needs attention before anything can change"
                                      : `${dryRunPreview.result.preview.mutation_count || 0} proposed website change${dryRunPreview.result.preview.mutation_count === 1 ? "" : "s"}`}
                                  </h3>
                                  <p className="mt-1 text-sm leading-6 text-zinc-400">
                                    Nothing on the website was changed. Review the exact values below before approving.
                                  </p>
                                </div>
                                <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${dryRunPreview.result.preview.conflict_count ? "border-rose-500/20 bg-rose-500/10 text-rose-100" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"}`}>
                                  {dryRunPreview.result.preview.conflict_count ? "Needs attention" : "Ready for approval"}
                                </span>
                              </div>

                              {(dryRunPreview.result.preview.conflicts || []).map((conflict, index) => (
                                <div key={`${conflict.code || "conflict"}-${index}`} className="rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-100">
                                  <p>{conflict.message || "This change cannot run safely yet."}</p>
                                  {conflict.recovery ? <p className="mt-1 text-rose-200">Next: {conflict.recovery}</p> : null}
                                </div>
                              ))}

                              <div className="space-y-3">
                                {(dryRunPreview.result.preview.changes || []).map((change, index) => (
                                  <div key={change.mutation_id || `${change.mutation_type}-${index}`} className="rounded-md border border-[#2b2c31] bg-[#101114] p-4">
                                    <p className="font-semibold text-zinc-100">{describeMutationType(change.mutation_type)}</p>
                                    <p className="mt-1 break-all text-xs text-zinc-500">{change.target_url || "Website page"}</p>
                                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                                      <div className="rounded-md border border-[#26272c] p-3">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Current</p>
                                        <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-zinc-300">{formatPreviewValue(change.before?.value ?? change.before)}</pre>
                                      </div>
                                      <div className="rounded-md border border-accent-500/20 bg-accent-500/5 p-3">
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-300">Proposed</p>
                                        <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-zinc-100">{formatPreviewValue(change.after?.value ?? change.after)}</pre>
                                      </div>
                                    </div>
                                    <div className="mt-3 flex flex-wrap gap-2">
                                      {(change.validation_checks || []).map((check, checkIndex) => (
                                        <span key={`${check.code || "check"}-${checkIndex}`} className={`rounded-full border px-2.5 py-1 text-xs ${check.passed ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100" : "border-rose-500/20 bg-rose-500/10 text-rose-100"}`}>
                                          {check.passed ? "✓" : "!"} {check.message || "Safety check"}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>

                              <div className="rounded-md border border-sky-500/20 bg-sky-500/10 p-3 text-sm leading-6 text-sky-100">
                                <strong>If you need to undo it:</strong>{" "}
                                {dryRunPreview.result.preview.rollback_summary || "InsightOS will save the previous values before applying anything."}
                              </div>
                            </div>
                          ) : (
                            <div className="rounded-md border border-[#26272c] bg-[#141518] p-4 text-sm text-zinc-300">
                              This action was previewed without changing anything.
                            </div>
                          )
                        ) : null}

                        {!EXECUTION_CONSOLE_ENABLED ? (
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4 text-sm text-zinc-300">
                            The execution console is disabled for this frontend build. Set{" "}
                            <code>NEXT_PUBLIC_EXECUTION_CONSOLE_ENABLED=true</code> to expose
                            run, retry, cancel, and rollback controls.
                          </div>
                        ) : null}

                        <ExecutionTimeline
                          entries={buildExecutionTimeline(selectedExecution)}
                        />
                      </>
                    ) : (
                      <EmptyState
                        title="No execution selected"
                        summary="Choose an execution from the inbox to review approval state, results, and available controls."
                        actionLabel="Refresh inbox"
                        onAction={() => void loadExecutions(selectedCampaignId)}
                      />
                    )}
                  </section>
                </div>
              )}
            </section>
              </div>
            </details>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
