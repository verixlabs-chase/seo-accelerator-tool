"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  ActionDrawer,
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

const EXECUTION_CONSOLE_ENABLED =
  process.env.NEXT_PUBLIC_EXECUTION_CONSOLE_ENABLED !== "false";
const WORDPRESS_EXECUTION_SETUP_UI_ENABLED =
  process.env.NEXT_PUBLIC_WORDPRESS_EXECUTION_SETUP_UI !== "false";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type Recommendation = {
  id: string;
  recommendation_type?: string;
  rationale?: string;
  confidence?: number;
  confidence_score?: number;
  evidence?: string[];
  risk_tier?: number;
  status?: string;
  created_at?: string;
};

type RecommendationSummary = {
  total_count?: number;
  counts_by_state?: Record<string, number>;
  counts_by_risk_tier?: Record<string, number>;
  average_confidence_score?: number;
};

type IntelligenceScoreResponse = {
  score_value?: number;
  latest_score?: {
    score_value?: number;
    captured_at?: string;
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
    return "Expected impact: strong";
  }

  if (confidenceScore >= 0.6) {
    return "Expected impact: moderate";
  }

  return "Expected impact: exploratory";
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
    return "Fix technical visibility issues";
  }

  if (normalized.includes("foundation")) {
    return "Stabilize the foundation first";
  }

  if (normalized.includes("growth")) {
    return "Push growth on stronger terms";
  }

  return toTitleCase(type);
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
      summary: "Use this when you agree the recommendation deserves to stay in the active queue.",
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
      summary: "Use this when the recommendation should move from planned to queued.",
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

export default function OpportunitiesPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedRecommendationId, setSelectedRecommendationId] = useState("");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState("");
  const [executionStatusFilter, setExecutionStatusFilter] = useState("all");
  const [dryRunPreview, setDryRunPreview] = useState<DryRunPreview | null>(null);
  const [summary, setSummary] = useState<RecommendationSummary | null>(null);
  const [score, setScore] = useState<IntelligenceScoreResponse | null>(null);
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
      setSelectedRecommendationId("");
      return;
    }

    const [recommendationsResponse, summaryResponse, scoreResponse] = await Promise.all([
      platformApi(`/intelligence/recommendations?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/recommendations/summary?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/intelligence/score?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
    ]);

    const items = Array.isArray(recommendationsResponse?.items)
      ? (recommendationsResponse.items as Recommendation[])
      : [];

    setRecommendations(items);
    setSummary((summaryResponse as RecommendationSummary) || null);
    setScore((scoreResponse as IntelligenceScoreResponse) || null);
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
      setNotice(successNotice);
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
      setNotice(successNotice);
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
      body: selectedRecommendation.rationale || "This is the clearest next opportunity the system has identified.",
      next:
        nextActionForStatus(selectedRecommendation.status)?.summary ||
        "Review the evidence first, then decide whether this action should stay active or be dismissed.",
    };
  }, [selectedCampaign, selectedRecommendation]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Open opportunities",
        value: summary?.total_count ? `${summary.total_count} active` : "None yet",
        tone: (summary?.total_count || 0) > 0 ? "info" : "warning",
      },
      {
        label: "High priority",
        value: highPriorityCount > 0 ? `${highPriorityCount} urgent` : "No urgent items",
        tone: highPriorityCount > 0 ? "warning" : "success",
      },
      {
        label: "Execution inbox",
        value: executions.length > 0 ? `${executions.length} items` : "Inbox clear",
        tone: executions.length > 0 ? "info" : "success",
      },
      {
        label: "Score",
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
    [executions.length, highPriorityCount, score?.score_value, summary?.total_count],
  );

  const primaryAction = selectedRecommendation
    ? nextActionForStatus(selectedRecommendation.status)
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

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed campaign"} / ${selectedCampaign.domain || "No domain"}`
          : "No campaign selected"
      }
      dateRangeLabel="Live recommendation data"
      topBarActions={
        <>
          <select
            value={selectedCampaignId}
            onChange={(event) => {
              setSelectedCampaignId(event.target.value);
              setNotice("");
            }}
            disabled={campaigns.length === 0}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-100 outline-none"
          >
            {campaigns.map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.name || campaign.domain || "Unnamed campaign"}
              </option>
            ))}
          </select>
          <button
            onClick={() => void refreshCampaignData(selectedCampaignId)}
            disabled={!selectedCampaignId || busyAction !== ""}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            onClick={() => router.push("/dashboard")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            Open dashboard
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Opportunities"
          title="What needs attention next"
          summary="Use the Action Center to see the most important recommended actions, why they matter, and which one should happen next."
        />

        {loading ? (
          <LoadingCard
            title="Loading opportunities"
            summary="Pulling the latest recommended actions, priority signals, and next-step guidance for the active business."
          />
        ) : null}

        {error ? (
          <section className="border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}

        {notice ? (
          <section className="border border-accent-500/20 bg-accent-500/10 p-4 text-sm text-zinc-100">
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
                                {recommendation.rationale || "No explanation was provided for this recommendation."}
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
                            Opportunity detail
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
                        </div>
                      </div>

                      <div className="mt-5 grid gap-4 md:grid-cols-3">
                        <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            What needs attention
                          </p>
                          <p className="mt-2 text-sm leading-6 text-zinc-300">
                            {selectedRecommendation.rationale || "This recommendation needs review."}
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
                        </div>
                      </div>

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                          Evidence
                        </p>
                        {selectedRecommendation.evidence?.length ? (
                          <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                            {selectedRecommendation.evidence.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-3 text-sm leading-6 text-zinc-300">
                            No supporting evidence was attached to this recommendation yet.
                          </p>
                        )}
                      </div>

                      <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <div className="grid gap-4 md:grid-cols-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Expected impact
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
                              Status
                            </p>
                            <p className="mt-2 text-sm text-zinc-200">
                              {getStatusLabel(selectedRecommendation.status)}
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
                            </div>

                            <p className="mt-3 text-sm leading-6 text-zinc-300">
                              {execution.last_error
                                ? `Latest error: ${execution.last_error.replace(/_/g, " ")}`
                                : getExecutionSummary(execution)}
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

                        <div className="grid gap-4 md:grid-cols-3">
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
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Mutation count
                            </p>
                            <p className="mt-2 text-sm leading-6 text-zinc-300">
                              {getMutationCount(selectedExecution)} tracked changes
                            </p>
                          </div>
                        </div>

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
                            Live execution is disabled: {liveExecutionDisabledReason}
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
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
