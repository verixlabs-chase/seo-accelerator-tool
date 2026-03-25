"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  TruthNotice,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  buildRuntimeTruthSignal,
  getRuntimeTruthSummary,
} from "../truth/runtimeTruth.mjs";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type BaselineMetric = {
  amount?: string | null;
  ratio?: string | null;
  net_amount?: string | null;
  currency?: string;
  status: string;
  source_type: string;
  label: string;
};

type BaselineScenario = {
  key: string;
  label: string;
  projected_value: string;
  upside_value: string;
  percentage_lift: string;
  target_rank_rule: string;
  roi_baseline: BaselineMetric;
};

type BaselineAssumption = {
  key: string;
  label: string;
  value?: string | null;
  status: string;
  source_type: string;
  note?: string | null;
};

type BaselineKeywordDriver = {
  keyword_id: string;
  keyword?: string | null;
  current_value?: string | null;
  projected_value?: string | null;
  upside_value?: string | null;
  current_rank?: number | null;
  projected_rank?: number | null;
  ctr_model_version?: string | null;
};

type BaselineConfidence = {
  level: string;
  score: string;
  reasons: string[];
};

type OrganicValueBaseline = {
  campaign_id: string;
  feature: string;
  currency: string;
  as_of?: string | null;
  current_value: BaselineMetric;
  upside_opportunity: BaselineMetric;
  roi_baseline: BaselineMetric;
  scenarios: BaselineScenario[];
  assumptions: BaselineAssumption[];
  confidence: BaselineConfidence;
  top_keywords_by_value: BaselineKeywordDriver[];
  opportunity_drivers: BaselineKeywordDriver[];
  caveats: string[];
  truth?: RuntimeTruth;
};

function formatMetric(metric?: BaselineMetric | null) {
  if (!metric || metric.status !== "available") {
    return "Unavailable";
  }
  return metric.amount ? `$${metric.amount}` : "Available";
}

function formatRatio(metric?: BaselineMetric | null) {
  if (!metric?.ratio) {
    return "Unavailable";
  }
  return `${metric.ratio}x`;
}

function formatDate(value?: string | null) {
  if (!value) {
    return "No economics snapshot yet";
  }
  return value;
}

function getConfidenceTone(level: string) {
  if (level === "high") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (level === "medium") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  return "border-rose-500/20 bg-rose-500/10 text-rose-100";
}

function getSourceTone(sourceType: string, status: string) {
  if (status === "unavailable") {
    return "border-[#26272c] bg-[#111214] text-zinc-400";
  }
  if (sourceType === "user_provided") {
    return "border-sky-500/20 bg-sky-500/10 text-sky-100";
  }
  if (sourceType === "provider_derived") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function SourceChip({ sourceType, status }: { sourceType: string; status: string }) {
  const label = status === "unavailable" ? "Unavailable" : sourceType.replace(/_/g, " ");
  return (
    <span className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${getSourceTone(sourceType, status)}`}>
      {label}
    </span>
  );
}

export default function OrganicValuePage() {
  const pathname = usePathname();
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [monthlyInvestment, setMonthlyInvestment] = useState("");
  const [appliedMonthlyInvestment, setAppliedMonthlyInvestment] = useState("");
  const [baseline, setBaseline] = useState<OrganicValueBaseline | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
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

  const loadBaseline = useCallback(async (campaignId: string, investmentInput: string) => {
    if (!campaignId) {
      setBaseline(null);
      return;
    }

    const trimmed = investmentInput.trim();
    const response = (await platformApi(
      `/campaigns/${campaignId}/organic-value-baseline`,
      {
        method: "POST",
        body: JSON.stringify({
          monthly_seo_investment: trimmed ? trimmed : null,
        }),
      },
    )) as OrganicValueBaseline;
    setBaseline(response);
    const persistedInvestment =
      response.assumptions.find((item) => item.key === "monthly_seo_investment")?.value || "";
    setMonthlyInvestment(persistedInvestment);
    setAppliedMonthlyInvestment(persistedInvestment);
  }, []);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        const items = await loadCampaigns();
        if (items[0]?.id) {
          await loadBaseline(items[0].id, appliedMonthlyInvestment);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load organic value baseline.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadBaseline, loadCampaigns, appliedMonthlyInvestment]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void loadBaseline(selectedCampaignId, appliedMonthlyInvestment).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load organic value baseline.");
    });
  }, [selectedCampaignId, loading, loadBaseline, appliedMonthlyInvestment]);

  async function refreshBaseline() {
    if (!selectedCampaignId) {
      return;
    }
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      await loadBaseline(selectedCampaignId, appliedMonthlyInvestment);
      setNotice("Organic value baseline refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh the baseline.");
    } finally {
      setRefreshing(false);
    }
  }

  async function applyInvestmentBaseline() {
    if (!selectedCampaignId) {
      return;
    }
    setAppliedMonthlyInvestment(monthlyInvestment);
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      await loadBaseline(selectedCampaignId, monthlyInvestment);
      setNotice("Organic value baseline recalculated with the latest manual assumption.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to recalculate the baseline.");
    } finally {
      setRefreshing(false);
    }
  }

  async function clearSavedInvestment() {
    if (!selectedCampaignId) {
      return;
    }
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/campaigns/${selectedCampaignId}/organic-value-baseline`,
        {
          method: "POST",
          body: JSON.stringify({
            clear_monthly_seo_investment: true,
          }),
        },
      )) as OrganicValueBaseline;
      setBaseline(response);
      setMonthlyInvestment("");
      setAppliedMonthlyInvestment("");
      setNotice("Saved monthly SEO investment cleared for this campaign.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clear the saved assumption.");
    } finally {
      setRefreshing(false);
    }
  }

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const expectedScenario = baseline?.scenarios.find((item) => item.key === "expected") ?? null;
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Runtime truth",
        baseline?.truth || null,
        "Organic value is a modeled baseline, not direct revenue truth.",
      ),
      {
        label: "Current value",
        value: baseline ? formatMetric(baseline.current_value) : "Awaiting baseline",
        tone: baseline?.current_value.status === "available" ? "success" : "warning",
      },
      {
        label: "Upside",
        value: baseline ? formatMetric(baseline.upside_opportunity) : "Awaiting baseline",
        tone: baseline?.upside_opportunity.status === "available" ? "info" : "warning",
      },
      {
        label: "Confidence",
        value: baseline ? `${baseline.confidence.level} (${baseline.confidence.score})` : "Unavailable",
        tone:
          baseline?.confidence.level === "high"
            ? "success"
            : baseline?.confidence.level === "medium"
              ? "warning"
              : "danger",
      },
      {
        label: "ROI baseline",
        value: baseline ? formatRatio(baseline.roi_baseline) : "Unavailable",
        tone: baseline?.roi_baseline.status === "available" ? "info" : "warning",
      },
    ],
    [baseline],
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
      dateRangeLabel="Organic value baseline"
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
            onClick={() => void refreshBaseline()}
            disabled={!selectedCampaignId || refreshing}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
          <button
            onClick={() => router.push("/rankings")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            View rankings
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Organic Value + ROI Baseline"
          title="What your organic visibility is worth right now"
          summary="This V1 estimates paid-search-equivalent value from tracked keyword rankings, then shows near-term upside and a simple baseline against optional monthly SEO investment."
        />

        <TruthNotice title="This is a value baseline, not a revenue forecast.">
          Current value and scenario outputs are based on stored rankings, search volume, CPC, and
          CTR assumptions. They estimate what equivalent traffic may be worth in paid media, not
          actual revenue, margin, or guaranteed ROI.
        </TruthNotice>

        {baseline?.truth ? (
          <TruthNotice title="Current runtime truth" tone="warning">
            {getRuntimeTruthSummary(
              baseline.truth,
              "Organic value runtime status is not available yet.",
            )}
          </TruthNotice>
        ) : null}

        {loading ? (
          <LoadingCard
            title="Loading organic value baseline"
            summary="Pulling the latest economics rows, opportunity range, and assumption state for the active business."
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
            title="No business is ready for organic value yet"
            summary="Set up a business and collect keyword economics data before using the baseline."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 && baseline ? (
          <>
            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Current value"
                value={formatMetric(baseline.current_value)}
                summary="Estimated current paid-equivalent value from tracked organic visibility."
                tone="highlight"
              />
              <KpiCard
                label="Near-term upside"
                value={formatMetric(baseline.upside_opportunity)}
                summary="Estimated upside from the conservative one-step improvement path."
              />
              <KpiCard
                label="Expected scenario"
                value={expectedScenario ? `$${expectedScenario.projected_value}` : "Unavailable"}
                summary="Estimated value under the expected scenario, not an actual outcome promise."
              />
              <KpiCard
                label="ROI baseline"
                value={formatRatio(baseline.roi_baseline)}
                summary="Paid-equivalent value divided by optional monthly SEO investment."
              />
            </div>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Baseline summary
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
                    Estimated current value: {formatMetric(baseline.current_value)}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    As of {formatDate(baseline.as_of)}, the current keyword economics rows suggest{" "}
                    {formatMetric(baseline.current_value)} in monthly paid-equivalent value, with{" "}
                    {formatMetric(baseline.upside_opportunity)} in near-term upside from the current
                    tracked keyword set.
                  </p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Optional assumption
                  </p>
                  <label className="mt-3 block text-sm font-medium text-white">
                    Monthly SEO investment
                  </label>
                  <input
                    value={monthlyInvestment}
                    onChange={(event) => setMonthlyInvestment(event.target.value)}
                    placeholder="e.g. 2500"
                    className="mt-2 w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <p className="mt-2 text-sm leading-6 text-zinc-400">
                    Leave this blank if you do not want a paid-equivalent ROI baseline. No revenue
                    or conversion assumptions are guessed in this V1.
                  </p>
                  <button
                    onClick={() => void applyInvestmentBaseline()}
                    disabled={refreshing || !selectedCampaignId}
                    className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Recalculate baseline
                  </button>
                  <button
                    onClick={() => void clearSavedInvestment()}
                    disabled={refreshing || !selectedCampaignId}
                    className="mt-3 rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Clear saved assumption
                  </button>
                </div>
              </div>
            </section>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Scenario range
              </p>
              <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                Conservative, expected, and aggressive upside
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                These scenarios are bounded rank-improvement heuristics built from the current
                keyword economics rows. They are useful for demos and pilots, not for precision
                forecasting.
              </p>
              <div className="mt-4 grid gap-4 xl:grid-cols-3">
                {baseline.scenarios.map((scenario) => (
                  <div key={scenario.key} className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-white">{scenario.label}</p>
                        <p className="mt-1 text-sm text-zinc-400">{scenario.target_rank_rule}</p>
                      </div>
                      <SourceChip sourceType={scenario.roi_baseline.source_type} status={scenario.roi_baseline.status} />
                    </div>
                    <div className="mt-4 space-y-2 text-sm text-zinc-300">
                      <p>Projected value: <span className="font-medium text-white">${scenario.projected_value}</span></p>
                      <p>Upside: <span className="font-medium text-white">${scenario.upside_value}</span></p>
                      <p>Lift: <span className="font-medium text-white">{scenario.percentage_lift}%</span></p>
                      <p>ROI baseline: <span className="font-medium text-white">{formatRatio(scenario.roi_baseline)}</span></p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Assumptions
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  What drives this estimate
                </h2>
                <div className="mt-4 space-y-3">
                  {baseline.assumptions.map((assumption) => (
                    <div key={assumption.key} className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-white">{assumption.label}</p>
                          <p className="mt-1 text-sm text-zinc-300">
                            {assumption.value || "Not available in this V1"}
                          </p>
                        </div>
                        <SourceChip sourceType={assumption.source_type} status={assumption.status} />
                      </div>
                      {assumption.note ? (
                        <p className="mt-2 text-sm leading-6 text-zinc-400">{assumption.note}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Confidence
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  How trustworthy the baseline is today
                </h2>
                <div className={`mt-4 rounded-md border p-4 ${getConfidenceTone(baseline.confidence.level)}`}>
                  <p className="text-sm font-medium text-white">
                    {baseline.confidence.level.toUpperCase()} confidence ({baseline.confidence.score})
                  </p>
                  <div className="mt-3 space-y-2 text-sm">
                    {baseline.confidence.reasons.map((reason) => (
                      <p key={reason}>{reason}</p>
                    ))}
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {baseline.caveats.map((caveat) => (
                    <div key={caveat} className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
                      {caveat}
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Current drivers
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Top keywords by current value
                </h2>
                <div className="mt-4 space-y-3">
                  {baseline.top_keywords_by_value.length === 0 ? (
                    <EmptyState
                      title="No keyword economics rows yet"
                      summary="Run ranking collection and store market data before using the value baseline."
                    />
                  ) : (
                    baseline.top_keywords_by_value.map((keyword, index) => (
                      <div key={keyword.keyword_id} className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-sm font-medium text-white">
                          {keyword.keyword || `Keyword #${index + 1}`}
                        </p>
                        <p className="mt-2 text-sm text-zinc-300">Current value: ${keyword.current_value || "0.00"}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-zinc-500">
                          {keyword.keyword_id}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Opportunity drivers
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Keywords with the clearest upside
                </h2>
                <div className="mt-4 space-y-3">
                  {baseline.opportunity_drivers.length === 0 ? (
                    <EmptyState
                      title="No opportunity drivers yet"
                      summary="Opportunity drivers appear once keyword economics rows exist for this business."
                    />
                  ) : (
                    baseline.opportunity_drivers.map((keyword, index) => (
                      <div key={keyword.keyword_id} className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-sm font-medium text-white">
                          {keyword.keyword || `Keyword #${index + 1}`}
                        </p>
                        <p className="mt-2 text-sm text-zinc-300">
                          Upside: ${keyword.upside_value || "0.00"} from rank {keyword.current_rank ?? "?"} to {keyword.projected_rank ?? "?"}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-zinc-500">
                          {keyword.keyword_id}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </section>
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
