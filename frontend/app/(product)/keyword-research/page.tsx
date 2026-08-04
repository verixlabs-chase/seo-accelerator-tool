"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  EmptyState,
  LoadingCard,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type ResearchRun = {
  id: string;
  status: "complete" | "partial" | "unavailable" | "running";
  location_name: string;
  sources: string[];
  warnings: string[];
  suggestion_count: number;
  completed_at?: string | null;
};

type SearchSuggestion = {
  id: string;
  keyword: string;
  source_types: string[];
  search_volume?: number | null;
  cpc?: number | null;
  competition_level?: string | null;
  keyword_difficulty?: number | null;
  current_position?: number | null;
  gsc_impressions?: number | null;
  gsc_position?: number | null;
  intent: string;
  opportunity_group: "quick_win" | "new_opportunity" | "already_found" | "tracked";
  relevance_score: number;
  opportunity_score: number;
  recommended_action: string;
  recommendation_reason: string;
  tracked_at?: string | null;
};

type ResearchResponse = {
  run: ResearchRun | null;
  items: SearchSuggestion[];
  summary: {
    total: number;
    quick_wins: number;
    new_opportunities: number;
    already_found: number;
    tracked: number;
  };
};

const FILTERS = [
  { id: "all", label: "Best first" },
  { id: "quick_win", label: "Close to the top" },
  { id: "new_opportunity", label: "New opportunities" },
  { id: "already_found", label: "Already found" },
  { id: "tracked", label: "Already tracking" },
] as const;

function groupLabel(group: SearchSuggestion["opportunity_group"]) {
  return {
    quick_win: "Close to the top",
    new_opportunity: "New opportunity",
    already_found: "Google already finds you",
    tracked: "Already tracking",
  }[group];
}

function groupTone(group: SearchSuggestion["opportunity_group"]) {
  if (group === "quick_win") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (group === "new_opportunity") return "border-accent-500/25 bg-accent-500/10 text-accent-100";
  if (group === "already_found") return "border-sky-500/25 bg-sky-500/10 text-sky-100";
  return "border-[#303137] bg-[#18191c] text-zinc-300";
}

function positionLabel(item: SearchSuggestion) {
  const position = item.current_position ?? item.gsc_position;
  if (position) return `About #${Math.round(position)}`;
  if ((item.gsc_impressions ?? 0) > 0) return "Showing, but low";
  return "Not found yet";
}

function demandLabel(value?: number | null) {
  if (value === null || value === undefined) return "Not measured";
  if (value === 0) return "Very low";
  return `About ${value.toLocaleString()}/month`;
}

function sourceLabel(source: string) {
  return {
    google_search_console: "Search Console",
    dataforseo_ranked: "Live rankings",
    dataforseo_ideas: "Related searches",
    dataforseo_volume: "Local demand",
    tracked_rankings: "Your tracked list",
    website_content: "Your website",
  }[source] ?? source;
}

export default function KeywordResearchPage() {
  const pathname = usePathname();
  const router = useRouter();
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const { campaigns, selectedCampaign, selectedCampaignId, loadingLocations } =
    useLocationContext();
  const [data, setData] = useState<ResearchResponse>({
    run: null,
    items: [],
    summary: { total: 0, quick_wins: 0, new_opportunities: 0, already_found: 0, tracked: 0 },
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "discover" | "track">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const loadResearch = useCallback(async (campaignId: string) => {
    setLoading(true);
    setError("");
    try {
      const response = (await platformApi(
        `/keyword-research?campaign_id=${encodeURIComponent(campaignId)}`,
      )) as ResearchResponse;
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search ideas could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setSelectedIds(new Set());
    setNotice("");
    setFilter("all");
    if (!selectedCampaignId) {
      setLoading(false);
      setData({
        run: null,
        items: [],
        summary: { total: 0, quick_wins: 0, new_opportunities: 0, already_found: 0, tracked: 0 },
      });
      return;
    }
    void loadResearch(selectedCampaignId);
  }, [loadResearch, selectedCampaignId]);

  const runDiscovery = async () => {
    if (!selectedCampaignId) return;
    setBusy("discover");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/keyword-research/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, max_suggestions: 75 }),
      })) as ResearchResponse;
      setData(response);
      setSelectedIds(new Set());
      setNotice(
        response.items.length
          ? `Found ${response.items.length} searches worth reviewing for this location.`
          : "No useful searches were confirmed yet. Check the connected data sources below.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search discovery could not be completed.");
    } finally {
      setBusy("");
    }
  };

  const trackSelected = async () => {
    if (!selectedCampaignId || selectedIds.size === 0) return;
    setBusy("track");
    setError("");
    try {
      const response = await platformApi("/keyword-research/track", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [...selectedIds],
        }),
      });
      setNotice(
        `${response.created_count ?? 0} added to Search Rankings. ${response.already_tracked_count ?? 0} were already there.`,
      );
      setSelectedIds(new Set());
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The selected searches could not be tracked.");
    } finally {
      setBusy("");
    }
  };

  const filteredItems = useMemo(
    () =>
      filter === "all"
        ? data.items
        : data.items.filter((item) => item.opportunity_group === filter),
    [data.items, filter],
  );
  const chartData = useMemo(
    () =>
      data.items
        .filter((item) => (item.search_volume ?? 0) > 0)
        .slice(0, 8)
        .map((item) => ({
          name: item.keyword.length > 30 ? `${item.keyword.slice(0, 28)}…` : item.keyword,
          demand: item.search_volume ?? 0,
        }))
        .reverse(),
    [data.items],
  );
  const selectableVisible = filteredItems.filter((item) => !item.tracked_at);
  const trustSignals: TrustSignal[] = [];

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No domain"}`
          : "No location selected"
      }
      dateRangeLabel={data.run ? `Latest research: ${data.run.location_name}` : "No research yet"}
      topBarActions={
        <button
          type="button"
          onClick={() => void runDiscovery()}
          disabled={!selectedCampaignId || busy !== ""}
          className="rounded-md bg-accent-500 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "discover" ? "Finding searches…" : data.run ? "Refresh search ideas" : "Find search ideas"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Keyword research"
          title="Find searches customers use"
          summary="See what people search for near this location, where your business already appears, and which searches are worth tracking next."
        />

        <TruthNotice title="Demand is an estimate, not a promise of new jobs.">
          Search demand comes from DataForSEO. Existing visibility comes from Search Console and
          live ranking data. Confirm that a search matches a service you actually sell before you
          track it.
        </TruthNotice>

        {loading || loadingLocations ? (
          <LoadingCard
            title="Loading customer searches"
            summary="Checking the saved research for the selected location."
          />
        ) : null}

        {error ? (
          <section className="rounded-md border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}
        {notice ? (
          <section className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            {notice}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="Add a location before finding searches"
            summary="Keyword research needs a real business, website, and city so results can be matched to the right market."
            actionLabel="Manage locations"
            onAction={() => router.push("/locations")}
          />
        ) : null}

        {!loading && campaigns.length > 0 && !data.run ? (
          <section className="grid gap-6 border-y border-[#26272c] py-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                Ready for {selectedCampaign?.name || "this location"}
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">
                Find real searches without building a list by hand
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                InsightOS will combine your website, location, Search Console history, current
                rankings, and DataForSEO demand data. You only decide which services are relevant.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void runDiscovery()}
              disabled={busy !== ""}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-accent-500 px-5 py-3 font-semibold text-white disabled:opacity-50"
            >
              <ProductIcon name="keyword-research" size={19} />
              {busy === "discover" ? "Finding searches…" : "Find customer searches"}
            </button>
          </section>
        ) : null}

        {!loading && data.run ? (
          <>
            <section className="border-b border-[#26272c] pb-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    What matters now
                  </p>
                  <h2 className="mt-1 text-2xl font-bold tracking-tight text-white">
                    {data.summary.quick_wins > 0
                      ? `${data.summary.quick_wins} searches are already close to the top`
                      : `${data.summary.new_opportunities} new searches are worth reviewing`}
                  </h2>
                  <p className="mt-2 text-sm text-zinc-400">
                    Start with searches close to the top, then review new opportunities that match
                    profitable work.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void trackSelected()}
                  disabled={selectedIds.size === 0 || busy !== ""}
                  className="rounded-md bg-accent-500 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#232428] disabled:text-zinc-500"
                >
                  {busy === "track" ? "Adding…" : `Track selected${selectedIds.size ? ` (${selectedIds.size})` : ""}`}
                </button>
              </div>
              <dl className="mt-6 grid gap-4 sm:grid-cols-4">
                {[
                  ["Close to the top", data.summary.quick_wins],
                  ["New opportunities", data.summary.new_opportunities],
                  ["Google finds you", data.summary.already_found],
                  ["Already tracking", data.summary.tracked],
                ].map(([label, value]) => (
                  <div key={String(label)} className="border-l-2 border-[#303137] pl-4 first:border-accent-500">
                    <dt className="text-xs text-zinc-500">{label}</dt>
                    <dd className="mt-1 text-2xl font-bold text-white">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            {data.run.warnings.length ? (
              <section className="rounded-md border border-amber-500/20 bg-amber-500/8 p-4">
                <p className="text-sm font-semibold text-amber-100">Some data could not be refreshed</p>
                <ul className="mt-2 space-y-1 text-sm text-amber-50/80">
                  {data.run.warnings.map((warning) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            {chartData.length ? (
              <section className="grid gap-5 border-b border-[#26272c] pb-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.7fr)]">
                <div>
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      Local demand
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-white">What customers search most</h2>
                  </div>
                  <div className="h-[280px] min-w-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 25 }}>
                        <CartesianGrid stroke="#27282d" horizontal={false} />
                        <XAxis type="number" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} />
                        <YAxis
                          type="category"
                          dataKey="name"
                          width={170}
                          tick={{ fill: "#d4d4d8", fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip
                          cursor={{ fill: "rgba(255,255,255,0.035)" }}
                          contentStyle={{ background: "#141518", border: "1px solid #303137", borderRadius: 6 }}
                          formatter={(value) => [`About ${Number(value).toLocaleString()} searches/month`, "Demand"]}
                        />
                        <Bar dataKey="demand" fill="#ff6a1a" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="border-l border-[#26272c] pl-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    How to use this
                  </p>
                  <ol className="mt-4 space-y-4 text-sm text-zinc-300">
                    <li className="flex gap-3"><span className="font-bold text-accent-400">1</span><span>Choose searches that describe work you want.</span></li>
                    <li className="flex gap-3"><span className="font-bold text-accent-400">2</span><span>Give priority to searches where you already appear.</span></li>
                    <li className="flex gap-3"><span className="font-bold text-accent-400">3</span><span>Track them so movement shows on Search Rankings.</span></li>
                  </ol>
                </div>
              </section>
            ) : null}

            <section>
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Search list
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Choose what to track</h2>
                </div>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Filter customer searches">
                  {FILTERS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setFilter(option.id)}
                      aria-pressed={filter === option.id}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                        filter === option.id
                          ? "bg-accent-500 text-white"
                          : "bg-[#18191c] text-zinc-400 hover:text-white"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {selectableVisible.length ? (
                <label className="mt-5 inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-zinc-400 hover:text-white">
                  <input
                    type="checkbox"
                    checked={selectableVisible.every((item) => selectedIds.has(item.id))}
                    onChange={(event) => {
                      const next = new Set(selectedIds);
                      selectableVisible.forEach((item) =>
                        event.target.checked ? next.add(item.id) : next.delete(item.id),
                      );
                      setSelectedIds(next);
                    }}
                    className="accent-orange-500"
                  />
                  Select all shown
                </label>
              ) : null}

              <div className="mt-3 divide-y divide-[#26272c] border-y border-[#26272c]">
                {filteredItems.map((item) => (
                  <article key={item.id} className="grid gap-4 py-5 lg:grid-cols-[28px_minmax(220px,1.2fr)_0.65fr_0.55fr_minmax(260px,1fr)] lg:items-center">
                    <div>
                      {item.tracked_at ? (
                        <ProductIcon name="check" size={19} className="text-emerald-400" label="Already tracked" />
                      ) : (
                        <input
                          type="checkbox"
                          aria-label={`Track ${item.keyword}`}
                          checked={selectedIds.has(item.id)}
                          onChange={(event) => {
                            const next = new Set(selectedIds);
                            event.target.checked ? next.add(item.id) : next.delete(item.id);
                            setSelectedIds(next);
                          }}
                          className="h-4 w-4 accent-orange-500"
                        />
                      )}
                    </div>
                    <div>
                      <h3 className="font-semibold text-white">{item.keyword}</h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${groupTone(item.opportunity_group)}`}>
                          {groupLabel(item.opportunity_group)}
                        </span>
                        <span className="rounded-full bg-[#1a1b1e] px-2 py-0.5 text-[11px] text-zinc-400">
                          {item.intent}
                        </span>
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Local demand</p>
                      <p className="mt-1 text-sm font-semibold text-zinc-100">{demandLabel(item.search_volume)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Your position</p>
                      <p className="mt-1 text-sm font-semibold text-zinc-100">{positionLabel(item)}</p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">{item.recommended_action}</p>
                      <p className="mt-1 text-sm leading-5 text-zinc-400">{item.recommendation_reason}</p>
                      <details className="mt-2 text-xs text-zinc-500">
                        <summary className="cursor-pointer hover:text-zinc-300">See the supporting data</summary>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                          <span>Opportunity score: {item.opportunity_score}/100</span>
                          {item.keyword_difficulty !== null && item.keyword_difficulty !== undefined ? (
                            <span>Difficulty: {item.keyword_difficulty}/100</span>
                          ) : null}
                          {item.cpc ? <span>Ad cost: ${item.cpc.toFixed(2)}/click</span> : null}
                          <span>Sources: {item.source_types.map(sourceLabel).join(", ")}</span>
                        </div>
                      </details>
                    </div>
                  </article>
                ))}
              </div>

              {filteredItems.length === 0 ? (
                <p className="py-10 text-center text-sm text-zinc-500">No searches match this view.</p>
              ) : null}
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
