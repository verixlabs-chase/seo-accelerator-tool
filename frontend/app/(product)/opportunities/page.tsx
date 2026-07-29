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
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type RuntimeTruth,
  type TimelineEntry,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  getExecutionStateSummary,
  getRecommendationStateSummary,
  getSetupBlockerSummary,
} from "../truth/opportunitiesTruth.mjs";
import {
  buildRuntimeTruthSignal,
  getOwnerFriendlyTruthSummary,
  pickPrimaryRuntimeTruth,
} from "../truth/runtimeTruth.mjs";

const EXECUTION_CONSOLE_ENABLED =
  process.env.NEXT_PUBLIC_EXECUTION_CONSOLE_ENABLED !== "false";
const WORDPRESS_EXECUTION_SETUP_UI_ENABLED =
  process.env.NEXT_PUBLIC_WORDPRESS_EXECUTION_SETUP_UI !== "false";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
  setup_state?: string;
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

type ExecutionResult = {
  status?: string;
  notes?: string;
  message?: string;
  reason_code?: string;
  mutations?: unknown[];
  rolled_back_mutations?: unknown[];
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
  breaker_state?: string;
  last_error_code?: string | null;
  last_error_at?: string | null;
  last_success_at?: string | null;
  status_summary: string;
  disabled_reason?: string | null;
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
    return "Likely benefit: strong";
  }

  if (confidenceScore >= 0.6) {
    return "Likely benefit: moderate";
  }

  return "Possible benefit — more evidence needed";
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
    return "Reviewed";
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

function describeRecommendationReason(reason?: string | null) {
  if (!reason) {
    return "InsightOS identified this as a useful improvement to review.";
  }

  const normalized = reason.toLowerCase();
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

  return reason
    .replace(/Google Business Profile/gi, "Google business listing")
    .replace(/review acquisition velocity/gi, "new review activity")
    .replace(/acquisition velocity/gi, "new activity")
    .replace(/content throughput/gi, "new content");
}

function getEngineSourceLabel(source?: string) {
  if (source === "orchestrator_v1") {
    return "Advanced recommendation review";
  }
  if (source === "mixed_v1") {
    return "Combined recommendation review";
  }
  if (source === "heuristic_score_v1") {
    return "Basic saved-data review";
  }
  if (source === "heuristic_threshold_v1") {
    return "Basic starting-point review";
  }
  return "Recommendation review not run yet";
}

function formatEvidence(value: string) {
  if (/^[a-z0-9_:.-]+$/i.test(value) && value.includes("_")) {
    return toTitleCase(value);
  }
  return value;
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
      label: "Mark reviewed",
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

function canRejectExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled";
}

function canRunExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled" || execution.status === "failed";
}

function canRetryExecution(execution: Execution) {
  return execution.status === "failed";
}

function canCancelExecution(execution: Execution) {
  return execution.status === "pending" || execution.status === "scheduled";
}

function canRollbackExecution(execution: Execution) {
  return execution.status === "completed" && getMutationCount(execution) > 0;
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
  const [wordpressSetup, setWordpressSetup] = useState<WordPressExecutionSetup | null>(null);
  const [wordpressSetupError, setWordpressSetupError] = useState("");
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
      setSelectedRecommendationId("");
      return;
    }

    const [recommendationsResponse, summaryResponse, scoreResponse, outcomeResponse] = await Promise.all([
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
    setSelectedRecommendationId((current) => {
      if (current && items.some((item) => item.id === current)) {
        return current;
      }
      return items[0]?.id || "";
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

  const refreshCampaignData = useCallback(
    async (campaignId: string) => {
      await Promise.all([
        loadOpportunities(campaignId),
        loadExecutions(campaignId),
        loadWordPressExecutionSetup(campaignId),
      ]);
    },
    [loadExecutions, loadOpportunities, loadWordPressExecutionSetup],
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

  const sortedRecommendations = useMemo(
    () =>
      [...recommendations].sort((left, right) => {
        const riskDifference = (right.risk_tier ?? 0) - (left.risk_tier ?? 0);
        if (riskDifference !== 0) {
          return riskDifference;
        }

        return (right.confidence_score ?? 0) - (left.confidence_score ?? 0);
      }),
    [recommendations],
  );

  const selectedRecommendation =
    sortedRecommendations.find((item) => item.id === selectedRecommendationId) ??
    sortedRecommendations[0] ??
    null;

  const selectedExecution =
    executions.find((item) => item.id === selectedExecutionId) ?? executions[0] ?? null;

  const highPriorityCount = sortedRecommendations.filter((item) => (item.risk_tier ?? 0) >= 3).length;
  const readyCount = (summary?.counts_by_state?.VALIDATED || 0) + (summary?.counts_by_state?.APPROVED || 0);
  const queuedCount = summary?.counts_by_state?.SCHEDULED || 0;
  const archivedCount = summary?.counts_by_state?.ARCHIVED || 0;
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

    if (!selectedRecommendation) {
      return {
        title: `${selectedCampaign.name || "This business"} has no active opportunities yet`,
        body: "InsightOS has not surfaced a recommendation queue for this business yet.",
        next: "Refresh after more crawl, ranking, or local data is available.",
      };
    }

    return {
      title: `${describeType(selectedRecommendation.recommendation_type)} needs attention`,
      body: describeRecommendationReason(selectedRecommendation.rationale),
      next:
        nextActionForStatus(selectedRecommendation.status)?.summary ||
        "Review the evidence first, then decide whether this action should stay active or be dismissed.",
    };
  }, [selectedCampaign, selectedRecommendation]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Recommendation status",
        runtimeTruth,
        "Recommendations and scores are heuristic until execution setup is ready and a run succeeds.",
      ),
      {
        label: "Recommended actions",
        value: summary?.total_count ? `${summary.total_count} active` : "None yet",
        tone: (summary?.total_count || 0) > 0 ? "info" : "warning",
      },
      {
        label: "High priority",
        value: highPriorityCount > 0 ? `${highPriorityCount} urgent` : "No urgent items",
        tone: highPriorityCount > 0 ? "warning" : "success",
      },
      {
        label: "Recommendation method",
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
      summary?.total_count,
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
      dateRangeLabel="Saved recommendations"
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
          title="Your best next steps"
          summary="See the improvements most likely to help this location, why each one matters, and which action to take first."
        />

        <TruthNotice title="Nothing changes on your website without review.">
          These are recommendations. A suggested change is not complete until it has been reviewed,
          approved, and successfully carried out.
        </TruthNotice>

        {runtimeTruth ? (
          <TruthNotice title="How current are these recommendations?" tone="warning">
            {getOwnerFriendlyTruthSummary(runtimeTruth, "recommended next steps")}
          </TruthNotice>
        ) : null}

        {engineState ? (
          <details className="rounded-md border border-sky-500/20 bg-sky-500/10 p-4 text-sky-50">
            <summary className="cursor-pointer text-sm font-semibold text-white">
              How recommendations are created and kept safe
            </summary>
            <div className="mt-3 text-sm leading-6 text-sky-50/85">
              InsightOS reviews saved information for this location and suggests possible
              improvements. It cannot automatically change the customer&apos;s website in the
              current safety mode.
              <div className="mt-3 border-t border-sky-500/20 pt-3 text-xs text-sky-100/70">
                System details: {getEngineSourceLabel(engineState.guidance_source)}.
                {engineState.provider_checks_allowed === false
                  ? " Paid data checks are off."
                  : ""}
                {engineState.learning_state === "observation_only"
                  ? " Results are observed, but the system does not change its rules automatically."
                  : ""}
              </div>
            </div>
          </details>
        ) : null}

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
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Summary
              </p>
              <div className="mt-3 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <div>
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                    {topSummary.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.body}</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What to do next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.next}</p>
                </div>
              </div>
            </section>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Workflow status
              </p>
              <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                Exactly where the selected action stands
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                These cards separate recommendation state from execution state so you can see what is only recommended, what is approved, what is queued, what completed, what failed, and what to do next.
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
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Open opportunities"
                value={String(summary?.total_count || 0)}
                summary="These are the recommended actions currently surfaced for the active business."
              />
              <KpiCard
                label="High priority"
                value={String(highPriorityCount)}
                summary="These are the items most likely to need attention first."
                tone="highlight"
              />
              <KpiCard
                label="Ready next"
                value={String(readyCount)}
                summary="These recommendations are already reviewed or chosen as likely next steps."
              />
              <KpiCard
                label="Queued or dismissed"
                value={`${queuedCount + archivedCount}`}
                summary="This includes recommendations already queued or intentionally cleared from the active list."
              />
            </div>

            {sortedRecommendations.length === 0 ? (
              <EmptyState
                title="No opportunities are queued yet"
                summary="Refresh after more crawl, ranking, or local data is available for this business."
                actionLabel="Refresh opportunities"
                onAction={() => void refreshCampaignData(selectedCampaignId)}
              />
            ) : (
              <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
                <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Queue
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Recommended actions
                    </h2>
                    <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                      Start with the high-priority items first, then move through the reviewed queue.
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
                                {describeType(recommendation.recommendation_type)}
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
                            <span
                              className={`rounded-md border px-2 py-1 text-xs font-medium ${getStatusTone(recommendation.status)}`}
                            >
                              {getStatusLabel(recommendation.status)}
                            </span>
                            <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-1 text-xs font-medium text-zinc-200">
                              {getImpactLabel(recommendation.confidence_score || recommendation.confidence || 0)}
                            </span>
                            <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-100">
                              {getEngineSourceLabel(recommendation.engine_source)}
                            </span>
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
                            Recommendation details
                          </p>
                          <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                            {describeType(selectedRecommendation.recommendation_type)}
                          </h2>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${getPriorityTone(selectedRecommendation.risk_tier)}`}
                          >
                            {getPriorityLabel(selectedRecommendation.risk_tier)}
                          </span>
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${getStatusTone(selectedRecommendation.status)}`}
                          >
                            {getStatusLabel(selectedRecommendation.status)}
                          </span>
                          <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-100">
                            {getEngineSourceLabel(selectedRecommendation.engine_source)}
                          </span>
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
                            Why it matters
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                            {getImpactLabel(
                              selectedRecommendation.confidence_score ||
                                selectedRecommendation.confidence ||
                                0,
                            )}
                            . {selectedRecommendation.risk_tier && selectedRecommendation.risk_tier >= 3
                              ? "The system sees this as urgent enough to review first."
                              : "The system sees this as worth addressing, but not the most urgent item in the queue."}
                          </p>
                        </div>
                        <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            What to do next
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                            {primaryAction?.summary ||
                              "Review the evidence below, then decide whether to keep this recommendation active or clear it from the queue."}
                          </p>
                          <p className="mt-3 text-xs uppercase tracking-[0.14em] text-zinc-500">
                            {recommendationState
                              ? `${recommendationState.label}. ${recommendationState.detail}`
                              : "Review the current recommendation state before moving it forward."}
                          </p>
                        </div>
                      </div>

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                          Evidence
                        </p>
                        {selectedRecommendation.evidence?.length ? (
                          <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                            {selectedRecommendation.evidence.map((item) => (
                              <li key={item}>• {formatEvidence(item)}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-3 text-sm leading-6 text-zinc-300">
                            No supporting evidence was attached to this recommendation yet.
                          </p>
                        )}
                      </div>

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <div className="grid gap-4 md:grid-cols-4">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Likely benefit
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
                              How this was found
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
                                : "Measure saved-data progress"}
                            </button>
                          ) : null}

                          {shouldAllowArchive(selectedRecommendation.status) ? (
                            <button
                              onClick={() =>
                                void transitionRecommendation(
                                  selectedRecommendation.id,
                                  "ARCHIVED",
                                  `${describeType(selectedRecommendation.recommendation_type)} was cleared from the active queue.`,
                                )
                              }
                              disabled={busyAction !== ""}
                              className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {busyAction === `${selectedRecommendation.id}:ARCHIVED`
                                ? "Updating..."
                                : "Clear from queue"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </>
                  ) : (
                    <EmptyState
                      title="No recommendation selected"
                      summary="Choose an opportunity from the queue to see why it matters and what should happen next."
                      actionLabel="Return to dashboard"
                      onAction={() => router.push("/dashboard")}
                    />
                  )}
                </section>
              </div>
            )}

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
                        WordPress execution setup
                      </p>
                      <h3 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                        Provisioning and safety status
                      </h3>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                        {wordpressSetup?.status_summary ||
                          "WordPress execution status will appear here for the selected business."}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
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

                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Credential source
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup
                          ? toTitleCase(wordpressSetup.credential_source.replace(/_/g, " "))
                          : "Unknown"}
                      </p>
                    </div>
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Plugin health
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup?.plugin_version
                          ? `Version ${wordpressSetup.plugin_version}`
                          : "No plugin version reported yet"}
                      </p>
                    </div>
                    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Last issue
                      </p>
                      <p className="mt-2 text-sm text-zinc-200">
                        {wordpressSetup?.last_error_code
                          ? toTitleCase(wordpressSetup.last_error_code.replace(/_/g, " "))
                          : "No recent plugin error recorded"}
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

                        <ActionDrawer
                          title={describeExecutionType(selectedExecution.execution_type)}
                          summary={getExecutionSummary(selectedExecution)}
                          evidence={executionEvidence}
                          actions={
                            <>
                              {canApproveExecution(selectedExecution) ? (
                                <button
                                  onClick={() =>
                                    void transitionExecution(
                                      selectedExecution.id,
                                      "approve",
                                      `${describeExecutionType(selectedExecution.execution_type)} approved and kept in the execution queue.`,
                                    )
                                  }
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {busyAction === `${selectedExecution.id}:approve`
                                    ? "Approving..."
                                    : "Approve"}
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
                                    : "Dry run"}
                                </button>
                              ) : null}

                              {EXECUTION_CONSOLE_ENABLED && canRunExecution(selectedExecution) ? (
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
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Latest dry run preview
                            </p>
                            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-sm leading-6 text-zinc-300">
                              {JSON.stringify(dryRunPreview.result, null, 2)}
                            </pre>
                          </div>
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
