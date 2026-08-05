"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  OwnerDecisionPanel,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type SearchValueKeyword = {
  id: string;
  keyword: string;
  position?: number | null;
  target_position?: number | null;
  search_volume?: number | null;
  clicks?: number | null;
  click_method: "measured" | "modeled";
  cpc?: string | null;
  contribution?: string | null;
  contribution_lower?: string | null;
  contribution_upper?: string | null;
  possible_contribution?: string | null;
  source: string;
  source_date: string;
  service?: string | null;
  location?: string | null;
};

type SearchValueHistory = {
  run_id: string;
  saved_at: string;
  status: string;
  central?: string | null;
  lower?: string | null;
  upper?: string | null;
  coverage_percent: number;
  measured_share_percent: number;
  confidence: string;
  formula_version: string;
};

type ChangeSignal = {
  key: string;
  label: string;
  direction: "up" | "down" | "same";
  detail: string;
};

type SearchValuePayload = {
  campaign_id: string;
  status: "available" | "withheld" | "unavailable";
  formula_version: string;
  ctr_model_version: string;
  currency: string;
  scope: {
    business_location_id?: string | null;
    location_name?: string | null;
    language_code: string;
    device: string;
  };
  research: {
    run_id?: string | null;
    saved_at?: string | null;
    age_days?: number | null;
    freshness: string;
    source: string;
    new_paid_check_required: boolean;
  };
  estimate: {
    status: string;
    central?: string | null;
    lower?: string | null;
    upper?: string | null;
    possible_central?: string | null;
    possible_lower?: string | null;
    possible_upper?: string | null;
    upside?: string | null;
    change_from_previous?: string | null;
    change_percent?: number | null;
  };
  coverage: {
    confirmed_phrases: number;
    valued_phrases: number;
    percent: number;
    missing_market_data: number;
  };
  confidence: {
    level: string;
    score: number;
    reasons: string[];
  };
  source_split: {
    measured_value?: string | null;
    modeled_value?: string | null;
    measured_share_percent: number;
    modeled_share_percent: number;
    measured_phrase_count: number;
    modeled_phrase_count: number;
  };
  comparison?: {
    previous_run_id: string;
    previous_saved_at: string;
    previous_value?: string | null;
    change?: string | null;
    change_percent?: number | null;
    signals: ChangeSignal[];
    formula_changed: boolean;
  } | null;
  history: SearchValueHistory[];
  keywords: SearchValueKeyword[];
  input_hash?: string | null;
  explanation: string;
  caveats: string[];
};

function money(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(number);
}

function moneyPrecise(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(number);
}

function shortDate(value?: string | null) {
  if (!value) return "No saved date";
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function rangeLabel(payload?: SearchValuePayload | null) {
  if (!payload || payload.status !== "available") return "Not available yet";
  return `${money(payload.estimate.lower)}–${money(payload.estimate.upper)}/month`;
}

function movementLabel(change?: string | null, percent?: number | null) {
  if (!change) return "No comparison yet";
  const numeric = Number(change);
  const arrow = numeric > 0 ? "↑" : numeric < 0 ? "↓" : "→";
  const percentText = percent === null || percent === undefined ? "" : ` (${Math.abs(percent).toFixed(1)}%)`;
  return `${arrow} ${money(Math.abs(numeric))}${percentText}`;
}

function movementTone(change?: string | null) {
  const numeric = Number(change || 0);
  if (numeric > 0) return "text-emerald-300";
  if (numeric < 0) return "text-rose-300";
  return "text-zinc-400";
}

function signalTone(direction: ChangeSignal["direction"]) {
  if (direction === "up") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  if (direction === "down") return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  return "border-[#2a2b30] bg-[#111214] text-zinc-300";
}

export default function SearchValuePage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [payload, setPayload] = useState<SearchValuePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadSearchValue = useCallback(async (campaignId: string, quiet = false) => {
    if (!campaignId) return;
    if (!quiet) setLoading(true);
    setError("");
    try {
      const response = (await platformApi(`/campaigns/${campaignId}/search-value`, {
        method: "GET",
      })) as SearchValuePayload;
      setPayload(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search Value could not be loaded.");
      setPayload(null);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    async function loadCampaigns() {
      try {
        await platformApi("/auth/me", { method: "GET" });
        const response = await platformApi("/campaigns", { method: "GET" });
        const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
        if (!active) return;
        setCampaigns(items);
        setSelectedCampaignId((current) =>
          current && items.some((item) => item.id === current) ? current : items[0]?.id || "",
        );
        if (items.length === 0) setLoading(false);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Search Value could not be loaded.");
        setLoading(false);
      }
    }
    void loadCampaigns();
    return () => {
      active = false;
    };
  }, [setSelectedCampaignId]);

  useEffect(() => {
    if (selectedCampaignId) void loadSearchValue(selectedCampaignId);
  }, [selectedCampaignId, loadSearchValue]);

  async function refreshSavedValue() {
    if (!selectedCampaignId) return;
    setRefreshing(true);
    await loadSearchValue(selectedCampaignId, true);
    setRefreshing(false);
  }

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const history = useMemo(
    () =>
      (payload?.history || []).map((item) => ({
        ...item,
        date: new Date(item.saved_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        centralValue: item.central === null || item.central === undefined ? null : Number(item.central),
        lowerValue: item.lower === null || item.lower === undefined ? null : Number(item.lower),
        upperValue: item.upper === null || item.upper === undefined ? null : Number(item.upper),
      })),
    [payload],
  );
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Estimated replacement cost",
        value: rangeLabel(payload),
        tone: payload?.status === "available" ? "success" : "warning",
      },
      {
        label: "Data coverage",
        value: payload ? `${payload.coverage.percent.toFixed(0)}%` : "Waiting",
        tone: payload && payload.coverage.percent >= 70 ? "success" : "warning",
      },
      {
        label: "Measured share",
        value: payload ? `${payload.source_split.measured_share_percent.toFixed(0)}%` : "Waiting",
        tone: payload && payload.source_split.measured_share_percent >= 50 ? "success" : "info",
      },
      {
        label: "Research date",
        value: shortDate(payload?.research.saved_at),
        tone: payload?.research.freshness === "current" ? "success" : "warning",
      },
    ],
    [payload],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No website"}`
          : "No location selected"
      }
      dateRangeLabel="Saved research history"
      topBarActions={
        <>
          <button
            onClick={() => void refreshSavedValue()}
            disabled={!selectedCampaignId || refreshing}
            className="rounded-md border border-[#2a2b30] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Reloading…" : "Reload saved results"}
          </button>
          <button
            onClick={() => router.push("/keyword-research")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            Find customer searches
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Search value"
          title="What similar visibility could cost in paid search"
          summary="See a researched monthly range, what comes from real Google clicks, and which customer searches contribute to it."
        />

        <TruthNotice title="This is replacement cost—not business revenue.">
          Search Value estimates what similar visibility might cost through paid search. It does not
          estimate sales, profit, leads, or guaranteed results.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Building the Search Value estimate"
            summary="Using this location’s saved customer-search research and Search Console results."
          />
        ) : null}

        {error ? (
          <section className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a location first"
            summary="Search Value needs one business location and its saved customer-search research."
            actionLabel="Open setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && payload?.status === "unavailable" ? (
          <EmptyState
            title="There is not enough saved information yet"
            summary="Confirm useful customer searches, then refresh their rankings and local demand. Search Value will reuse that saved work automatically."
            actionLabel="Find customer searches"
            onAction={() => router.push("/keyword-research")}
          />
        ) : null}

        {!loading && payload?.status === "withheld" ? (
          <OwnerDecisionPanel
            title="The saved research is too old for a trustworthy dollar estimate"
            summary={`The latest research for ${payload.scope.location_name || "this location"} is ${payload.research.age_days ?? "more than 90"} days old.`}
            nextStep="Refresh customer-search research before using Search Value for a decision."
            actionLabel="Refresh customer searches"
            onAction={() => router.push("/keyword-research")}
            tone="warning"
          />
        ) : null}

        {!loading && payload?.status === "available" ? (
          <>
            <OwnerDecisionPanel
              title={`Similar visibility could cost ${rangeLabel(payload)} in paid search`}
              summary={`The central estimate is ${money(payload.estimate.central)} per month for ${payload.scope.location_name || "this location"}. ${payload.source_split.measured_share_percent.toFixed(0)}% is based on measured Search Console clicks; the rest is clearly labeled modeled.`}
              nextStep="Open the phrase list below to see exactly what contributes to the estimate."
              actionLabel="Review phrase details"
              onAction={() => document.getElementById("phrase-contributions")?.scrollIntoView({ behavior: "smooth" })}
              tone="positive"
            />

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Researched monthly range"
                value={`${money(payload.estimate.lower)}–${money(payload.estimate.upper)}`}
                summary={`Central estimate: ${money(payload.estimate.central)}.`}
                tone="highlight"
              />
              <KpiCard
                label="If priority phrases improve"
                value={`${money(payload.estimate.possible_lower)}–${money(payload.estimate.possible_upper)}`}
                summary={`Modeled upside: ${money(payload.estimate.upside)}. This is not a promised result.`}
              />
              <KpiCard
                label="Data coverage"
                value={`${payload.coverage.percent.toFixed(0)}%`}
                summary={`${payload.coverage.valued_phrases} of ${payload.coverage.confirmed_phrases} confirmed phrases have enough information.`}
              />
              <KpiCard
                label="Change from the last saved date"
                value={movementLabel(payload.estimate.change_from_previous, payload.estimate.change_percent)}
                summary={payload.comparison ? `Compared with ${shortDate(payload.comparison.previous_saved_at)}.` : "A comparison appears after the next saved research date."}
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
              <section className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Saved history
                </p>
                <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold text-white">How the estimate has changed</h2>
                    <p className="mt-1 text-sm text-zinc-400">
                      The center line is the central estimate. The outer lines show the conservative range.
                    </p>
                  </div>
                  <span className={`text-sm font-semibold ${movementTone(payload.estimate.change_from_previous)}`}>
                    {movementLabel(payload.estimate.change_from_previous, payload.estimate.change_percent)}
                  </span>
                </div>
                {history.length > 1 ? (
                  <div className="mt-5 h-72" aria-label="Estimated search value by scenario">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={history} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                        <CartesianGrid stroke="#28292e" vertical={false} />
                        <XAxis dataKey="date" stroke="#8b8d96" fontSize={11} tickLine={false} axisLine={false} />
                        <YAxis stroke="#8b8d96" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(value) => `$${Number(value).toLocaleString()}`} />
                        <Tooltip
                          contentStyle={{ background: "#111214", border: "1px solid #2a2b30", borderRadius: 8 }}
                          formatter={(value, name) => [money(Number(value)), name === "centralValue" ? "Central estimate" : name === "lowerValue" ? "Low end" : "High end"]}
                        />
                        <Line type="monotone" dataKey="upperValue" stroke="#71717a" strokeDasharray="4 4" dot={false} connectNulls={false} />
                        <Line type="monotone" dataKey="centralValue" stroke="#ff6b1a" strokeWidth={3} dot={{ r: 3 }} connectNulls={false} />
                        <Line type="monotone" dataKey="lowerValue" stroke="#71717a" strokeDasharray="4 4" dot={false} connectNulls={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="mt-5 border-y border-[#2a2b30] py-8 text-sm text-zinc-400">
                    One saved date is available. The trend appears after the next research refresh.
                  </div>
                )}
              </section>

              <section className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  What the number uses
                </p>
                <h2 className="mt-1 text-xl font-semibold text-white">Measured clicks vs. modeled gaps</h2>
                <div className="mt-6 overflow-hidden rounded-full bg-[#27282d]" role="img" aria-label={`${payload.source_split.measured_share_percent}% measured clicks and ${payload.source_split.modeled_share_percent}% modeled clicks`}>
                  <div className="flex h-4 w-full">
                    <div className="bg-emerald-500" style={{ width: `${payload.source_split.measured_share_percent}%` }} />
                    <div className="bg-sky-500" style={{ width: `${payload.source_split.modeled_share_percent}%` }} />
                  </div>
                </div>
                <div className="mt-5 space-y-4">
                  <div className="border-l-2 border-emerald-500 pl-3">
                    <p className="text-sm font-semibold text-white">Measured from Google clicks</p>
                    <p className="mt-1 text-2xl font-semibold text-emerald-300">{money(payload.source_split.measured_value)}</p>
                    <p className="mt-1 text-sm text-zinc-400">{payload.source_split.measured_phrase_count} phrases · {payload.source_split.measured_share_percent.toFixed(0)}% of the estimate</p>
                  </div>
                  <div className="border-l-2 border-sky-500 pl-3">
                    <p className="text-sm font-semibold text-white">Filled with the position model</p>
                    <p className="mt-1 text-2xl font-semibold text-sky-300">{money(payload.source_split.modeled_value)}</p>
                    <p className="mt-1 text-sm text-zinc-400">{payload.source_split.modeled_phrase_count} phrases · {payload.source_split.modeled_share_percent.toFixed(0)}% of the estimate</p>
                  </div>
                </div>
              </section>
            </div>

            {payload.comparison ? (
              <section className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Why it changed</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Five things checked on every comparison</h2>
                <p className="mt-1 text-sm text-zinc-400">These signals explain the movement without pretending one change caused the whole result.</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  {payload.comparison.signals.map((signal) => (
                    <div key={signal.key} className={`rounded-md border p-4 ${signalTone(signal.direction)}`}>
                      <p className="text-sm font-semibold">{signal.direction === "up" ? "↑" : signal.direction === "down" ? "↓" : "→"} {signal.label}</p>
                      <p className="mt-2 text-sm leading-5 opacity-80">{signal.detail}</p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            <section id="phrase-contributions" className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Phrase details</p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Every dollar can be traced to a customer search</h2>
                  <p className="mt-1 text-sm text-zinc-400">Sorted by current monthly contribution. Open Search Rankings to work on a phrase.</p>
                </div>
                <button onClick={() => router.push("/rankings")} className="rounded-md border border-[#2a2b30] px-3 py-2 text-sm text-zinc-200">Open Search Rankings</button>
              </div>
              <div className="mt-5 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-[#2a2b30] text-[11px] uppercase tracking-[0.16em] text-zinc-500">
                    <tr>
                      <th className="px-3 py-3 font-semibold">Customer search</th>
                      <th className="px-3 py-3 font-semibold">Position</th>
                      <th className="px-3 py-3 font-semibold">Monthly clicks used</th>
                      <th className="px-3 py-3 font-semibold">Typical ad cost</th>
                      <th className="px-3 py-3 font-semibold">Monthly contribution</th>
                      <th className="px-3 py-3 font-semibold">Source and date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#24252a]">
                    {payload.keywords.map((keyword) => (
                      <tr key={keyword.id} className="align-top text-zinc-300">
                        <td className="px-3 py-4">
                          <p className="font-semibold text-white">{keyword.keyword}</p>
                          <p className="mt-1 text-xs text-zinc-500">{keyword.service || "Confirmed service"} · {keyword.location || payload.scope.location_name}</p>
                        </td>
                        <td className="px-3 py-4">{keyword.position ? `#${keyword.position}` : "Not measured"}</td>
                        <td className="px-3 py-4">
                          <p>{keyword.clicks?.toFixed(1) ?? "—"}</p>
                          <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${keyword.click_method === "measured" ? "bg-emerald-500/10 text-emerald-200" : "bg-sky-500/10 text-sky-200"}`}>
                            {keyword.click_method === "measured" ? "Measured" : "Modeled"}
                          </span>
                        </td>
                        <td className="px-3 py-4">{moneyPrecise(keyword.cpc)}/click</td>
                        <td className="px-3 py-4">
                          <p className="font-semibold text-white">{money(keyword.contribution)}</p>
                          <p className="mt-1 text-xs text-zinc-500">{money(keyword.contribution_lower)}–{money(keyword.contribution_upper)}</p>
                        </td>
                        <td className="px-3 py-4">
                          <p>{keyword.source}</p>
                          <p className="mt-1 text-xs text-zinc-500">{shortDate(keyword.source_date)}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="grid gap-5 xl:grid-cols-2">
              <section className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Confidence</p>
                <h2 className="mt-1 text-xl font-semibold text-white">{payload.confidence.level} confidence · {payload.confidence.score}/100</h2>
                <div className="mt-4 space-y-2 text-sm text-zinc-300">
                  {payload.confidence.reasons.map((reason) => <p key={reason}>• {reason}</p>)}
                </div>
              </section>
              <section className="rounded-md border border-[#2a2b30] bg-[#141518] p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Saved calculation</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Reproducible from the same inputs</h2>
                <div className="mt-4 space-y-2 text-sm text-zinc-300">
                  <p>Location: {payload.scope.location_name || "Not recorded"}</p>
                  <p>Research date: {shortDate(payload.research.saved_at)}</p>
                  <p>Formula: {payload.formula_version}</p>
                  <p>Click model: {payload.ctr_model_version}</p>
                  <p className="break-all text-xs text-zinc-500">Input record: {payload.input_hash}</p>
                </div>
              </section>
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
