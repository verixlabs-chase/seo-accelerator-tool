"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  DataState,
  EmptyState,
  LoadingCard,
  OwnerDecisionPanel,
  PageSection,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type ProductIconName,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type AiSearchEngine = {
  id: string;
  code: string;
  name: string;
  availability: "available";
  supported_geographies: string[];
  supported_languages: string[];
  supported_devices: string[];
  limitations: string[];
};

type FrozenQuestion = {
  id: string;
  text: string;
  service_id: string;
  service_name: string;
  service_area_id: string;
  service_area_name: string;
  checked?: boolean;
  mentioned?: boolean;
  recommended?: boolean;
  cited?: boolean;
  linked?: boolean;
};

type QuestionSet = {
  id: string;
  campaign_id: string;
  business_location_id?: string | null;
  version: number | string;
  generator_version: string;
  question_count: number;
  questions: FrozenQuestion[];
  context_hash: string;
  question_set_hash: string;
  status: string;
  created_at: string;
};

type AiSearchSummary = {
  campaign_id: string;
  business_location_id?: string | null;
  truth: {
    state: string;
    label: string;
    detail: string;
    last_observed_at?: string | null;
    comparison_ready: boolean;
  };
  setup: {
    ready: boolean;
    confirmed_services: number;
    confirmed_service_areas: number;
    missing: string[];
    question_set_ready: boolean;
  };
  summary: {
    checked: number;
    mentioned: number;
    recommended: number;
    cited: number;
    linked: number;
    unavailable: number;
    sample_size: number;
    coverage: {
      mentioned: FactCoverage;
      recommended: FactCoverage;
      cited: FactCoverage;
      linked: FactCoverage;
    };
  };
  engines: {
    approved_count: number;
    items: AiSearchEngine[];
    unavailable_reason?: string | null;
  };
  questions: {
    current: QuestionSet | null;
    count: number;
    frozen: boolean;
    generator_version?: string | null;
    current_context: boolean;
  };
  history: {
    items: unknown[];
    total_runs: number;
    comparable_runs: number;
    status: string;
  };
  competitors: {
    items: unknown[];
    mentioned_count: number;
    status: string;
  };
  next_action: {
    code: string;
    label: string;
    detail: string;
    href?: string | null;
  };
  limitations: string[];
};

type FactCoverage = {
  observed: number;
  measured: number;
  not_measured: number;
  unavailable: number;
};

type PrepareQuestionSetResponse = {
  created: boolean;
  question_set: QuestionSet;
  collection_state: string;
  next_action?: {
    code: string;
    label: string;
    detail: string;
    href?: string | null;
  };
  limitations: string[];
};

type Fact = {
  id: string;
  label: string;
  value: string;
  summary: string;
  icon: ProductIconName;
};

const SAFE_ACTION_PATHS = new Set(["/keyword-research", "/opportunities", "/settings"]);

function numberOrNull(value: unknown) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
}

function formatSavedDate(value?: string | null) {
  if (!value) return "No saved checks";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Saved date unavailable";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function observedValue(value: unknown, measured: number | null) {
  if (measured === null || measured <= 0) return "Not checked";
  const numeric = numberOrNull(value);
  return numeric === null ? "Not available" : numeric.toLocaleString();
}

function missingContextLabel(value: string) {
  const normalized = value.toLowerCase().replaceAll("_", " ");
  if (normalized.includes("service area") || normalized.includes("location")) {
    return "a confirmed service area";
  }
  if (normalized.includes("service")) return "a confirmed service";
  return "confirmed business details";
}

function actionPath(value?: string | null) {
  return value && SAFE_ACTION_PATHS.has(value) ? value : null;
}

function compactCoverage(values: string[] | undefined, fallback: string) {
  if (!values?.length) return fallback;
  if (values.length <= 3) return values.join(", ");
  return `${values.slice(0, 3).join(", ")} +${values.length - 3} more`;
}

function EvidenceFacts({ facts }: { facts: Fact[] }) {
  return (
    <section
      aria-label="Saved AI search facts"
      className="divide-y divide-[#26272c] border-y border-[#26272c] sm:grid sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5"
    >
      {facts.map((fact) => (
        <div key={fact.id} className="flex min-w-0 gap-3 px-2 py-4 sm:px-4 first:sm:pl-2">
          <ProductIcon name={fact.icon} size={19} className="mt-0.5 shrink-0 text-accent-400" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-zinc-400">{fact.label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-white">{fact.value}</p>
            <p className="mt-1 text-xs leading-5 text-zinc-500">{fact.summary}</p>
          </div>
        </div>
      ))}
    </section>
  );
}

function QuestionResult({ question }: { question: FrozenQuestion }) {
  if (question.checked !== true) {
    return <span className="text-zinc-500">Not checked</span>;
  }

  const states = [
    question.mentioned ? "Mentioned" : null,
    question.recommended ? "Recommended" : null,
    question.cited ? "Cited" : null,
    question.linked ? "Linked" : null,
  ].filter(Boolean) as string[];

  if (states.length === 0) {
    return <span className="text-zinc-300">Not found in the saved answer</span>;
  }

  return (
    <span className="flex flex-wrap gap-1.5">
      {states.map((state) => (
        <span
          key={state}
          className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-100"
        >
          {state}
        </span>
      ))}
    </span>
  );
}

function stateForEmptyEvidence(summary: AiSearchSummary) {
  const state = summary.truth?.state?.toLowerCase() || "not_measured";
  if (state === "unavailable" || state === "unsupported") return "unsupported" as const;
  if (state === "partial") return "partial" as const;
  if (state === "stale") return "stale" as const;
  if (state === "error") return "error" as const;
  return "empty" as const;
}

function decisionFor(summary: AiSearchSummary) {
  const checked = numberOrNull(summary.summary?.checked) ?? 0;
  const mentioned = numberOrNull(summary.summary?.mentioned) ?? 0;
  const mentionMeasured =
    numberOrNull(summary.summary?.coverage?.mentioned?.measured) ?? 0;
  const missing = (summary.setup?.missing || []).map(missingContextLabel);

  if (mentionMeasured > 0) {
    return {
      tone: mentioned > 0 ? ("positive" as const) : ("warning" as const),
      title:
        mentioned > 0
          ? `Your business appeared in ${mentioned} of ${mentionMeasured} answers checked for mentions`
          : `Your business was not found in the ${mentionMeasured} answers checked for mentions`,
      summary:
        "This result covers only the frozen customer questions and AI search services shown below.",
      nextStep:
        summary.next_action?.detail ||
        "Review the saved question evidence before choosing any website or profile work.",
      progress: {
        label: "Answers that mentioned this business",
        value: mentioned,
        total: mentionMeasured,
        valueLabel: `${mentioned} of ${mentionMeasured}`,
        summary: "A mention is not automatically a recommendation, citation, or link.",
      },
    };
  }

  if (checked > 0) {
    return {
      tone: "neutral" as const,
      title: "Saved AI search details are available, but mentions were not checked",
      summary:
        "This sample checked other details, such as recommendations, citations, or links. It cannot show whether the business appeared.",
      nextStep:
        "Review each saved fact below on its own. Do not treat an unchecked mention as a missing mention.",
    };
  }

  if (summary.questions?.current && summary.setup?.question_set_ready === false) {
    return {
      tone: "warning" as const,
      title: "Saved customer questions need an update",
      summary:
        "The earlier questions remain saved, but this location’s confirmed services or service areas have changed.",
      nextStep:
        "Prepare an updated frozen set before any later AI search checks. The older questions will remain in saved history.",
    };
  }

  if (summary.truth?.state === "unavailable") {
    return {
      tone: "neutral" as const,
      title: "AI search checks are not available for this location yet",
      summary:
        "No AI search result has been measured, so this page does not report a zero or guess at visibility.",
      nextStep:
        summary.next_action?.detail || "There is nothing to fix until saved AI search checks are available.",
    };
  }

  if (summary.questions?.current) {
    return {
      tone: "neutral" as const,
      title: "Customer questions are ready, but no answers have been checked",
      summary:
        "The saved question set can support consistent checks later. It is not evidence that the business appears today.",
      nextStep:
        summary.next_action?.detail || "Keep the questions unchanged so later saved checks can be compared fairly.",
    };
  }

  if (summary.setup?.ready === true) {
    return {
      tone: "neutral" as const,
      title: "Prepare the customer questions worth checking",
      summary:
        "InsightOS can use this location’s confirmed services and service areas to prepare a fixed question set.",
      nextStep:
        "Prepare the questions now. This saves the questions only and does not run an AI search check.",
    };
  }

  return {
    tone: "warning" as const,
    title: "Confirm what this location does and where it works",
    summary: missing.length
      ? `The question set still needs ${Array.from(new Set(missing)).join(" and ")}.`
      : "The question set needs confirmed services and service areas.",
    nextStep:
      summary.next_action?.detail || "Confirm the services and service areas before preparing customer questions.",
  };
}

export default function AiSearchVisibilityPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { campaigns, selectedCampaign, selectedCampaignId, loadingLocations } = useLocationContext();
  const [payload, setPayload] = useState<AiSearchSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadSummary = useCallback(async (campaignId: string, preserveSaved = false) => {
    if (!campaignId) return;
    if (preserveSaved) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const response = (await platformApi(
        `/ai-search/summary?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      )) as AiSearchSummary;
      setPayload(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saved AI search results could not be loaded.");
      if (!preserveSaved) setPayload(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    setPayload(null);
    setNotice("");
    setError("");
    if (selectedCampaignId) void loadSummary(selectedCampaignId);
  }, [loadSummary, selectedCampaignId]);

  async function prepareQuestions() {
    if (
      !selectedCampaignId ||
      payload?.setup?.ready !== true ||
      payload.setup.question_set_ready !== false
    ) return;
    setPreparing(true);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/ai-search/question-sets?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST", body: JSON.stringify({}) },
      )) as PrepareQuestionSetResponse;
      setNotice(
        response.created
          ? "Customer questions are saved. No AI search answers have been checked yet."
          : "The current customer questions were already saved. No AI search answers have been checked yet.",
      );
      await loadSummary(selectedCampaignId, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Customer questions could not be prepared.");
    } finally {
      setPreparing(false);
    }
  }

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const checked = numberOrNull(payload?.summary?.checked);
  const hasObservedEvidence = checked !== null && checked > 0;
  const lastSavedAt = payload?.truth?.last_observed_at || null;
  const decision = payload ? decisionFor(payload) : null;
  const nextActionHref = payload ? actionPath(payload.next_action?.href) : null;
  const questionSet = payload?.questions?.current || null;
  const questionSetNeedsUpdate =
    questionSet !== null && payload?.setup?.question_set_ready === false;
  const canPrepareQuestions =
    payload?.setup?.ready === true && payload.setup.question_set_ready === false;
  const prepareActionLabel = questionSetNeedsUpdate
    ? "Update customer questions"
    : "Prepare customer questions";

  const facts = useMemo<Fact[]>(
    () => [
      {
        id: "checked",
        label: "Answers checked",
        value: checked && checked > 0 ? checked.toLocaleString() : "Not checked",
        summary: "Saved answers in this exact sample.",
        icon: "check",
      },
      {
        id: "mentioned",
        label: "Mentioned",
        value: observedValue(
          payload?.summary?.mentioned,
          numberOrNull(payload?.summary?.coverage?.mentioned?.measured),
        ),
        summary: "The business name appeared in the answer.",
        icon: "spark",
      },
      {
        id: "recommended",
        label: "Recommended",
        value: observedValue(
          payload?.summary?.recommended,
          numberOrNull(payload?.summary?.coverage?.recommended?.measured),
        ),
        summary: "The answer suggested the business as an option.",
        icon: "arrow-up",
      },
      {
        id: "cited",
        label: "Cited as a source",
        value: observedValue(
          payload?.summary?.cited,
          numberOrNull(payload?.summary?.coverage?.cited?.measured),
        ),
        summary: "A business page supported the answer.",
        icon: "reports",
      },
      {
        id: "linked",
        label: "Linked",
        value: observedValue(
          payload?.summary?.linked,
          numberOrNull(payload?.summary?.coverage?.linked?.measured),
        ),
        summary: "The saved answer included a clickable link.",
        icon: "connections",
      },
    ],
    [checked, payload],
  );

  const trustSignals = useMemo<TrustSignal[]>(() => {
    if (!payload) return [];
    if (payload.truth?.state === "unavailable") {
      return [{ label: "AI search checks", value: "Not available yet", tone: "warning" }];
    }
    if (payload.truth?.state === "stale") {
      return [{ label: "Saved AI search results", value: "Needs a newer check", tone: "warning" }];
    }
    if (payload.truth?.state === "partial") {
      return [{ label: "Saved AI search results", value: "Some coverage is missing", tone: "warning" }];
    }
    return [];
  }, [payload]);

  const engines = payload?.engines?.items || [];
  const questionPreview = questionSet?.questions?.slice(0, 12) || [];
  const remainingQuestions = questionSet?.questions?.slice(12) || [];
  const emptyEvidenceState = payload ? stateForEmptyEvidence(payload) : "empty";

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No website"}`
          : "No location selected"
      }
      dateRangeLabel={formatSavedDate(lastSavedAt)}
      topBarActions={
        <button
          type="button"
          onClick={() => selectedCampaignId && void loadSummary(selectedCampaignId, true)}
          disabled={!selectedCampaignId || loading || refreshing}
          className="rounded-md border border-[#2a2b30] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshing ? "Reloading…" : "Reload saved results"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="AI search"
          title="See where AI answers mention your business"
          summary="Check the customer questions, sources, and competitors found in saved AI search results for this location."
        />

        <TruthNotice title="AI search results are a saved sample.">
          Answers can change by question, place, date, and AI search service. A missing result here
          does not prove the business never appears elsewhere.
        </TruthNotice>

        {loading || loadingLocations ? (
          <LoadingCard
            title="Loading saved AI search results"
            summary="Checking this location for saved questions, supported services, and measured answers."
          />
        ) : null}

        {!loading && !loadingLocations && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a location first"
            summary="AI search evidence stays separate for every business location. Add a location before preparing customer questions."
            actionLabel="Open setup"
            onAction={() => router.push("/dashboard")}
            icon="locations"
          />
        ) : null}

        {error ? (
          <section role="alert" className="border-y border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            <p className="font-semibold">
              {payload ? "The latest reload did not finish" : "Saved AI search results could not be loaded"}
            </p>
            <p className="mt-1 leading-5 text-rose-100/80">
              {payload
                ? `The saved results from ${formatSavedDate(lastSavedAt)} are still shown below.`
                : "Try again later. No result is being reported as zero while the saved evidence is unavailable."}
            </p>
          </section>
        ) : null}

        {notice ? (
          <section role="status" className="border-y border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {notice}
          </section>
        ) : null}

        {!loading && payload && decision ? (
          <OwnerDecisionPanel
            eyebrow="Current saved result"
            title={decision.title}
            summary={decision.summary}
            nextStep={decision.nextStep}
            tone={decision.tone}
            progress={decision.progress}
            actionLabel={
              canPrepareQuestions
                ? preparing
                  ? "Preparing questions…"
                  : prepareActionLabel
                : nextActionHref
                  ? payload.next_action.label
                  : undefined
            }
            onAction={
              canPrepareQuestions
                ? () => void prepareQuestions()
                : nextActionHref
                  ? () => router.push(nextActionHref)
                  : undefined
            }
          />
        ) : null}

        {!loading && payload ? <EvidenceFacts facts={facts} /> : null}

        {!loading && payload && !hasObservedEvidence ? (
          <DataState
            state={emptyEvidenceState}
            title={
              payload.truth?.state === "unavailable"
                ? "AI search checks are not available yet"
                : questionSet
                  ? "No saved answers have been checked"
                  : "No customer questions have been prepared"
            }
            summary={
              payload.truth?.state === "unavailable"
                ? "This page will not turn missing coverage into a zero result. Supported services and saved evidence will appear here when they are available."
                : questionSet
                  ? "The frozen questions are ready for consistent checks later. Saving questions does not measure an AI answer."
                  : payload.setup?.ready
                    ? "Prepare a fixed set from the confirmed services and service areas below. This does not run a search check."
                    : "Confirm at least one service and one service area before preparing questions."
            }
          />
        ) : null}

        {!loading && payload?.truth?.state === "partial" && hasObservedEvidence ? (
          <section className="border-y border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            Some saved coverage is missing. The measured answers remain visible, while missing services are not counted as zero.
          </section>
        ) : null}

        {!loading && payload?.truth?.state === "stale" && hasObservedEvidence ? (
          <section className="border-y border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            These are older saved results from {formatSavedDate(lastSavedAt)}. They remain visible, but they should not be treated as current.
          </section>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="AI answer services included"
            summary="Only AI answer services that passed evidence and location checks can appear here. Missing services are not counted as zero."
            icon="ai-search"
          >
            {engines.length === 0 ? (
              <DataState
                state="unsupported"
                title="No AI search services are available for this location yet"
                summary="The business has not been measured on an approved service. InsightOS does not estimate results for unavailable coverage."
              />
            ) : (
              <div className="overflow-x-auto border-y border-[#26272c]">
                <table className="min-w-full border-collapse text-left">
                  <thead className="bg-[#111214]">
                    <tr>
                      <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Service</th>
                      <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Coverage</th>
                      <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Availability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {engines.map((engine) => (
                      <tr key={engine.id} className="border-t border-[#26272c]">
                        <td className="px-4 py-3">
                          <p className="font-medium text-zinc-100">{engine.name}</p>
                        </td>
                        <td className="px-4 py-3 text-sm text-zinc-300">
                          <p>
                            Places: {compactCoverage(engine.supported_geographies, "approved areas only")}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500">
                            Languages: {compactCoverage(engine.supported_languages, "approved languages only")}
                            {" · "}
                            Devices: {compactCoverage(engine.supported_devices, "approved devices only")}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-sm text-zinc-300">
                          {engine.availability === "available"
                            ? "Available for supported checks"
                            : "Not available for saved checks"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PageSection>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="Customer questions saved for consistent checks"
            summary="These exact questions stay frozen within this version so a later result can be compared fairly."
            icon="keyword-research"
            action={
              canPrepareQuestions && questionSet ? (
                <button
                  type="button"
                  onClick={() => void prepareQuestions()}
                  disabled={preparing}
                  className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3.5 py-2 text-sm font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {preparing ? "Updating questions…" : "Update customer questions"}
                </button>
              ) : undefined
            }
          >
            {!questionSet ? (
              <DataState
                state="empty"
                title={payload.setup?.ready ? "No questions have been prepared" : "Business context is incomplete"}
                summary={
                  payload.setup?.ready
                    ? "Prepare questions from the confirmed services and service areas. This saves questions only."
                    : "Confirm the work this location sells and the places it serves before preparing questions."
                }
                action={
                  payload.setup?.ready ? (
                    <button
                      type="button"
                      onClick={() => void prepareQuestions()}
                      disabled={preparing}
                      className="rounded-md bg-accent-500 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {preparing ? "Preparing questions…" : prepareActionLabel}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => router.push("/keyword-research")}
                      className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3.5 py-2 text-sm font-semibold text-zinc-100"
                    >
                      Confirm services and areas
                    </button>
                  )
                }
              />
            ) : (
              <div>
                {payload.setup?.question_set_ready === false ? (
                  <section className="border-y border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    These questions are still saved, but they no longer match the current confirmed services and service areas. Update them before a later check.
                  </section>
                ) : null}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-[#26272c] px-3 py-2.5 text-xs text-zinc-400">
                  <span>Saved question list {String(questionSet.version)}</span>
                  <span>{questionSet.question_count} frozen questions</span>
                  <span>Saved {formatSavedDate(questionSet.created_at)}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-[#26272c]">
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Customer question</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Service and area</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Saved result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {questionPreview.map((question) => (
                        <tr key={question.id} className="border-b border-[#26272c] align-top">
                          <td className="max-w-2xl px-4 py-4 text-sm font-medium leading-6 text-zinc-100">{question.text}</td>
                          <td className="px-4 py-4 text-sm text-zinc-300">
                            <p>{question.service_name}</p>
                            <p className="mt-1 text-xs text-zinc-500">{question.service_area_name}</p>
                          </td>
                          <td className="px-4 py-4 text-sm"><QuestionResult question={question} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {remainingQuestions.length > 0 ? (
                  <details className="border-b border-[#26272c] bg-[#111214] px-4 py-3">
                    <summary className="cursor-pointer text-sm font-semibold text-zinc-200">
                      Show {remainingQuestions.length} more saved questions
                    </summary>
                    <ul className="mt-3 divide-y divide-[#26272c] border-t border-[#26272c]">
                      {remainingQuestions.map((question) => (
                        <li key={question.id} className="grid gap-2 py-3 md:grid-cols-[minmax(0,1.5fr)_minmax(12rem,0.7fr)]">
                          <div>
                            <p className="text-sm font-medium leading-6 text-zinc-100">{question.text}</p>
                            <p className="mt-1 text-xs text-zinc-500">
                              {question.service_name} · {question.service_area_name}
                            </p>
                          </div>
                          <div className="text-sm md:text-right"><QuestionResult question={question} /></div>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            )}
          </PageSection>
        ) : null}

        {!loading && payload?.limitations?.length ? (
          <details className="border-y border-[#26272c] bg-[#111214] px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-200">What these saved results do not prove</summary>
            <ul className="mt-3 space-y-2 text-sm leading-5 text-zinc-400">
              {payload.limitations.map((limitation) => (
                <li key={limitation}>• {limitation}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>
    </AppShell>
  );
}
