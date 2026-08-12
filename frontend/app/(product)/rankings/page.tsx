"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  ChartCard,
  ChartEmptyState,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  buildRuntimeTruthSignal,
} from "../truth/runtimeTruth.mjs";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
  business_location_id?: string | null;
};

type Me = {
  organization_id?: string;
};

type TrackedKeyword = {
  id: string;
  campaign_id: string;
  keyword: string;
  cluster: string;
  location_code: string;
  created_at?: string;
};

type PortfolioLocation = {
  business_location_id?: string | null;
  location_name: string;
  primary_city?: string | null;
  status: string;
  campaign_ids: string[];
  campaign_names: string[];
  domains: string[];
  tracked_keywords: number;
  ranked_keywords: number;
  average_position?: number | null;
  top_10_keywords: number;
  improved_keywords: number;
  declined_keywords: number;
  latest_captured_at?: string | null;
};

type PortfolioSummary = {
  locations: number;
  campaigns: number;
  tracked_keywords: number;
  ranked_keywords: number;
  average_position?: number | null;
  top_10_keywords: number;
  improved_keywords: number;
  declined_keywords: number;
  latest_captured_at?: string | null;
};

type RankTrend = {
  keyword_id?: string;
  keyword?: string;
  cluster?: string;
  location_code?: string;
  position?: number | string | null;
  delta?: number | null;
  confidence?: number | null;
};

type RankTrendResponse = {
  items?: RankTrend[];
  tracked_keywords?: number;
  latest_captured_at?: string | null;
  truth?: RuntimeTruth;
};

type RankingSnapshot = {
  id: string;
  keyword_id: string;
  position: number;
  confidence?: number | null;
  captured_at: string;
};

function coerceNumber(value: number | string | null | undefined, fallback = 0) {
  if (typeof value === "number") {
    return value;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatDelta(value?: number | null) {
  if (value === null || value === undefined) {
    return "New";
  }

  if (value > 0) {
    return `Up ${value}`;
  }

  if (value < 0) {
    return `Down ${Math.abs(value)}`;
  }

  return "No change";
}

function getMovementTone(value?: number | null) {
  if (value === null || value === undefined) {
    return "text-sky-200 border-sky-500/20 bg-sky-500/10";
  }

  if (value > 0) {
    return "text-emerald-100 border-emerald-500/20 bg-emerald-500/10";
  }

  if (value < 0) {
    return "text-rose-100 border-rose-500/20 bg-rose-500/10";
  }

  return "text-zinc-200 border-[#26272c] bg-[#141518]";
}

function describeWatchItem(trend: RankTrend) {
  const position = coerceNumber(trend.position, 100);
  const delta = trend.delta;

  if (delta === null || delta === undefined) {
    return "This is a new tracked search. Watch where it settles after the next check.";
  }

  if (delta > 0 && position <= 10) {
    return "This search is already on page one. Keep an eye on it and defend the gain.";
  }

  if (delta > 0) {
    return "This search improved. It is a good candidate to keep monitoring for page-one progress.";
  }

  if (delta < 0) {
    return "This search slipped. Check the related page first and confirm the next ranking update.";
  }

  if (position <= 10) {
    return "This search is stable on page one. Watch for any drop in the next update.";
  }

  return "This search is steady. It may need more content or page work before it moves.";
}

function RankingsTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; name?: string; color?: string }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-2.5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">{label}</p>
      <div className="mt-2 space-y-1.5">
        {payload.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2 text-sm text-zinc-200">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span>{entry.name}</span>
            <span className="ml-auto font-medium text-white">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RankingsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const lastSelectedCampaignId = useRef("");
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [viewMode, setViewMode] = useState<"portfolio" | "location">("portfolio");
  const [trends, setTrends] = useState<RankTrend[]>([]);
  const [snapshots, setSnapshots] = useState<RankingSnapshot[]>([]);
  const [trackedKeywords, setTrackedKeywords] = useState<TrackedKeyword[]>([]);
  const [portfolioLocations, setPortfolioLocations] = useState<PortfolioLocation[]>([]);
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [rankingsTruth, setRankingsTruth] = useState<RuntimeTruth | null>(null);
  const [trackedKeywordCount, setTrackedKeywordCount] = useState(0);
  const [latestCapturedAt, setLatestCapturedAt] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [clusterName, setClusterName] = useState("Core services");
  const [locationTarget, setLocationTarget] = useState("");
  const [providerLogin, setProviderLogin] = useState("");
  const [providerPassword, setProviderPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadCampaigns() {
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
  }

  async function loadTrends(campaignId: string) {
    if (!campaignId) {
      setTrends([]);
      setRankingsTruth(null);
      setTrackedKeywordCount(0);
      setLatestCapturedAt("");
      setTrackedKeywords([]);
      setSnapshots([]);
      return;
    }

    const [response, keywordsResponse, snapshotsResponse] = await Promise.all([
      platformApi(
        `/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      ) as Promise<RankTrendResponse>,
      platformApi(
        `/rank/keywords?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      ),
      platformApi(
        `/rank/snapshots?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      ),
    ]);
    setTrends(Array.isArray(response?.items) ? (response.items as RankTrend[]) : []);
    setTrackedKeywords(
      Array.isArray(keywordsResponse?.items)
        ? (keywordsResponse.items as TrackedKeyword[])
        : [],
    );
    setSnapshots(
      Array.isArray(snapshotsResponse?.items)
        ? (snapshotsResponse.items as RankingSnapshot[])
        : [],
    );
    setRankingsTruth((response?.truth as RuntimeTruth) || null);
    setTrackedKeywordCount(Number(response?.tracked_keywords || 0));
    setLatestCapturedAt(response?.latest_captured_at || "");
  }

  async function loadPortfolio() {
    const response = await platformApi("/rank/portfolio", { method: "GET" });
    setPortfolioLocations(
      Array.isArray(response?.items) ? (response.items as PortfolioLocation[]) : [],
    );
    setPortfolioSummary((response?.summary as PortfolioSummary) || null);
    if (response?.truth) {
      setRankingsTruth((current) => current || (response.truth as RuntimeTruth));
    }
  }

  async function refreshRankings(campaignId?: string) {
    setRefreshing(true);
    setError("");

    try {
      await Promise.all([
        campaignId ? loadTrends(campaignId) : Promise.resolve(),
        loadPortfolio(),
      ]);
      setNotice(
        "Saved ranking data reloaded. Use “Run live check” when you want fresh provider results.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh rankings.");
    } finally {
      setRefreshing(false);
    }
  }

  function parseKeywordInput(value: string) {
    return Array.from(
      new Set(
        value
          .split(/[\n,]/)
          .map((item) => item.trim())
          .filter(Boolean),
      ),
    );
  }

  async function addTrackedKeywords(event: FormEvent) {
    event.preventDefault();
    const keywords = parseKeywordInput(keywordInput);
    if (!selectedCampaignId || keywords.length === 0) {
      setError("Add at least one search term first.");
      return;
    }
    setBusyAction("keywords");
    setError("");
    setNotice("");
    try {
      const response = await platformApi("/rank/keywords/bulk", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          cluster_name: clusterName.trim() || "Core services",
          keywords,
          location_code: locationTarget.trim() || null,
        }),
      });
      setKeywordInput("");
      await Promise.all([loadTrends(selectedCampaignId), loadPortfolio()]);
      const created = Number(response?.created_count || 0);
      const skipped = Number(response?.skipped_count || 0);
      setNotice(
        `${created} search term${created === 1 ? "" : "s"} added for ${response?.location_code || "this location"}${
          skipped ? `; ${skipped} duplicate${skipped === 1 ? " was" : "s were"} skipped` : ""
        }.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add tracked searches.");
    } finally {
      setBusyAction("");
    }
  }

  async function removeTrackedKeyword(keywordId: string) {
    if (!selectedCampaignId) return;
    setBusyAction(`delete-${keywordId}`);
    setError("");
    try {
      await platformApi(`/rank/keywords/${keywordId}`, { method: "DELETE" });
      await Promise.all([loadTrends(selectedCampaignId), loadPortfolio()]);
      setNotice("Tracked search removed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove tracked search.");
    } finally {
      setBusyAction("");
    }
  }

  async function runLiveCheck() {
    if (!selectedCampaignId) return;
    setBusyAction("run");
    setError("");
    setNotice("");
    try {
      const response = await platformApi("/rank/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          location_code: locationTarget.trim() || null,
        }),
      });
      await Promise.all([loadTrends(selectedCampaignId), loadPortfolio()]);
      const created = Number(response?.snapshots_created || 0);
      setNotice(
        created > 0
          ? `Live ranking check complete. ${created} fresh position${created === 1 ? "" : "s"} stored.`
          : "No ranking snapshots were created. Check the search data connection and location searches below.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run the live ranking check.");
    } finally {
      setBusyAction("");
    }
  }

  async function connectSearchData(event: FormEvent) {
    event.preventDefault();
    if (!me?.organization_id || !providerLogin.trim() || !providerPassword) {
      setError("The search data login and password are required.");
      return;
    }
    setBusyAction("provider");
    setError("");
    setNotice("");
    try {
      await platformApi(
        `/organizations/${me.organization_id}/search-data-credentials`,
        {
          method: "PUT",
          body: JSON.stringify({
            auth_mode: "basic",
            credentials: {
              login: providerLogin.trim(),
              password: providerPassword,
            },
          }),
        },
      );
      setProviderLogin("");
      setProviderPassword("");
      await Promise.all([
        selectedCampaignId ? loadTrends(selectedCampaignId) : Promise.resolve(),
        loadPortfolio(),
      ]);
      setNotice("Search data connection saved securely. You can run the first live check now.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the search data connection.");
    } finally {
      setBusyAction("");
    }
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        const currentUser = (await platformApi("/auth/me", { method: "GET" })) as Me;
        setMe(currentUser);
        const [items] = await Promise.all([loadCampaigns(), loadPortfolio()]);
        if (items[0]?.id) {
          await loadTrends(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load rankings.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, []);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void loadTrends(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load rankings.");
    });
  }, [selectedCampaignId, loading]);

  useEffect(() => {
    if (!selectedCampaignId) {
      return;
    }
    if (!lastSelectedCampaignId.current) {
      lastSelectedCampaignId.current = selectedCampaignId;
      return;
    }
    if (lastSelectedCampaignId.current !== selectedCampaignId) {
      lastSelectedCampaignId.current = selectedCampaignId;
      setViewMode("location");
      setNotice("");
    }
  }, [selectedCampaignId]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const selectedPortfolioLocation =
    portfolioLocations.find((item) => item.campaign_ids.includes(selectedCampaignId)) ?? null;

  useEffect(() => {
    setLocationTarget(
      selectedPortfolioLocation?.primary_city
        ? `${selectedPortfolioLocation.primary_city}, United States`
        : "",
    );
  }, [selectedPortfolioLocation?.business_location_id, selectedPortfolioLocation?.primary_city]);

  const rankedTrends = useMemo(
    () =>
      [...trends].sort((left, right) => {
        const leftPosition = coerceNumber(left.position, 999);
        const rightPosition = coerceNumber(right.position, 999);
        return leftPosition - rightPosition;
      }),
    [trends],
  );

  const trackedTerms = trackedKeywordCount;
  const pageOneCount = trends.filter((item) => coerceNumber(item.position, 999) <= 10).length;
  const improvedTerms = trends.filter((item) => (item.delta ?? 0) > 0).length;
  const droppedTerms = trends.filter((item) => (item.delta ?? 0) < 0).length;

  const strongestPosition = rankedTrends[0] ?? null;
  const weakestPosition = rankedTrends[rankedTrends.length - 1] ?? null;
  const nextOpportunity =
    rankedTrends.find((trend) => {
      const position = coerceNumber(trend.position, 999);
      return position > 10 && position <= 30;
    }) ?? null;

  const rankingDistributionData = useMemo(() => {
    const buckets = [
      { label: "Top 3", minimum: 1, maximum: 3, count: 0 },
      { label: "4–10", minimum: 4, maximum: 10, count: 0 },
      { label: "11–20", minimum: 11, maximum: 20, count: 0 },
      { label: "21–50", minimum: 21, maximum: 50, count: 0 },
      { label: "51+", minimum: 51, maximum: Number.POSITIVE_INFINITY, count: 0 },
    ];

    trends.forEach((trend) => {
      const position = coerceNumber(trend.position, 999);
      const bucket = buckets.find(
        (item) => position >= item.minimum && position <= item.maximum,
      );
      if (bucket) {
        bucket.count += 1;
      }
    });

    return buckets;
  }, [trends]);

  const rankingHistory = useMemo(() => {
    const keywordById = new Map(
      trackedKeywords.map((keyword) => [keyword.id, keyword.keyword]),
    );
    const buckets = new Map<
      string,
      { timestamp: number; label: string; positions: Record<string, number> }
    >();

    snapshots.forEach((snapshot) => {
      const capturedAt = new Date(snapshot.captured_at);
      if (Number.isNaN(capturedAt.getTime())) {
        return;
      }
      capturedAt.setSeconds(0, 0);
      const key = capturedAt.toISOString();
      const existing = buckets.get(key) ?? {
        timestamp: capturedAt.getTime(),
        label: capturedAt.toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }),
        positions: {},
      };
      existing.positions[snapshot.keyword_id] = snapshot.position;
      buckets.set(key, existing);
    });

    const keywordIds = Array.from(
      new Set(snapshots.map((snapshot) => snapshot.keyword_id)),
    ).slice(0, 5);
    const data = [...buckets.values()]
      .sort((left, right) => left.timestamp - right.timestamp)
      .slice(-12)
      .map((bucket) => ({
        label: bucket.label,
        ...bucket.positions,
      }));

    return {
      data,
      series: keywordIds.map((keywordId) => ({
        id: keywordId,
        label: keywordById.get(keywordId) || "Tracked phrase",
      })),
    };
  }, [snapshots, trackedKeywords]);

  const portfolioChartData = useMemo(
    () =>
      portfolioLocations
        .filter((location) => location.average_position !== null)
        .map((location) => ({
          label:
            location.location_name.length > 20
              ? `${location.location_name.slice(0, 20)}…`
              : location.location_name,
          position: location.average_position ?? 0,
        })),
    [portfolioLocations],
  );

  const positionChartData = useMemo(
    () =>
      rankedTrends.slice(0, 8).map((trend, index) => ({
        label: trend.keyword?.slice(0, 14) || `Term ${index + 1}`,
        position: coerceNumber(trend.position, 100),
      })),
    [rankedTrends],
  );

  const movementChartData = useMemo(
    () =>
      [...trends]
        .sort((left, right) => Math.abs(right.delta ?? 0) - Math.abs(left.delta ?? 0))
        .slice(0, 8)
        .map((trend, index) => ({
          label: trend.keyword?.slice(0, 14) || `Term ${index + 1}`,
          movement: trend.delta ?? 0,
        })),
    [trends],
  );

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Updates",
        rankingsTruth,
        "Search positions may be older or unavailable until a fresh check finishes.",
      ),
      {
        label: "Tracked searches",
        value: trackedKeywordCount > 0 ? `${trackedKeywordCount} configured` : "None yet",
        tone: trackedKeywordCount > 0 ? "info" : "warning",
      },
      {
        label: "Latest snapshot",
        value: latestCapturedAt || "No snapshot yet",
        tone: latestCapturedAt ? (rankingsTruth?.freshness_state === "stale" ? "warning" : "info") : "warning",
      },
      {
        label: "Improved",
        value: improvedTerms > 0 ? `${improvedTerms} moving up` : "No gains yet",
        tone: improvedTerms > 0 ? "info" : "warning",
      },
      {
        label: "Dropped",
        value: droppedTerms > 0 ? `${droppedTerms} need review` : "No drops flagged",
        tone: droppedTerms > 0 ? "warning" : "success",
      },
    ],
    [droppedTerms, improvedTerms, latestCapturedAt, rankingsTruth, trackedKeywordCount],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        viewMode === "portfolio"
          ? "All locations portfolio"
          : selectedCampaign
          ? `${selectedCampaign.name || "Unnamed campaign"} / ${selectedCampaign.domain || "No domain"}`
          : "No campaign selected"
      }
      dateRangeLabel={
        viewMode === "portfolio" ? "Location comparison" : "Saved ranking snapshots"
      }
      topBarActions={
        <>
          {viewMode === "location" ? (
            <button
              onClick={() => void runLiveCheck()}
              disabled={busyAction !== "" || trackedKeywords.length === 0 || !selectedCampaignId}
              className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busyAction === "run" ? "Checking..." : "Run live check"}
            </button>
          ) : null}
          <button
            onClick={() =>
              void refreshRankings(
                viewMode === "location" ? selectedCampaignId : undefined,
              )
            }
            disabled={refreshing || (viewMode === "location" && !selectedCampaignId)}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Reloading..." : "Reload saved data"}
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
          compact
          eyebrow="Search rankings"
          title="Where your business shows up in search"
          summary="See which customer searches bring up each location, whether you are moving up or down, and which search phrase to work on next."
        />

        <section className="flex flex-col gap-3 rounded-md border border-[#303137] bg-[#111214] p-3 sm:flex-row sm:items-center sm:justify-between">
          <div
            className="inline-flex w-full rounded-md border border-[#26272c] bg-[#0d0e10] p-1 sm:w-auto"
            role="group"
            aria-label="Choose rankings view"
          >
            <button
              type="button"
              onClick={() => {
                setViewMode("portfolio");
                setNotice("");
              }}
              aria-pressed={viewMode === "portfolio"}
              className={`flex-1 rounded px-4 py-2 text-sm font-semibold transition sm:flex-none ${
                viewMode === "portfolio"
                  ? "bg-accent-500 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              All locations
            </button>
            <button
              type="button"
              onClick={() => {
                setViewMode("location");
                setNotice("");
              }}
              disabled={!selectedCampaignId}
              aria-pressed={viewMode === "location"}
              className={`flex-1 rounded px-4 py-2 text-sm font-semibold transition disabled:opacity-40 sm:flex-none ${
                viewMode === "location"
                  ? "bg-accent-500 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Selected location
            </button>
          </div>
          <p className="text-sm text-zinc-400">
            {viewMode === "portfolio"
              ? "Compare performance across the portfolio."
              : `Showing ${selectedCampaign?.name || selectedCampaign?.domain || "the selected location"}.`}
          </p>
        </section>

        <TruthNotice title="Check the update status before making a decision.">
          Saved search positions may be older than what customers see today. Use <strong>Run live
          check</strong> when you need fresh results for this location.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading rankings"
            summary="Pulling the latest tracked search positions and movement for the active business."
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
            title="No business is ready for rankings yet"
            summary="Set up your business first so InsightOS can track where you appear in search."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            {viewMode === "portfolio" ? (
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    All business locations
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    Compare every location at a glance
                  </h2>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                    This compares the latest saved search positions for every location.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => router.push("/locations")}
                  className="rounded-md border border-[#303137] bg-[#17181b] px-3 py-1.5 text-xs font-medium text-zinc-200"
                >
                  Manage locations
                </button>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <KpiCard
                  label="Locations"
                  value={String(portfolioSummary?.locations || 0)}
                  summary="Physical locations with assigned campaigns."
                />
                <KpiCard
                  label="Tracked searches"
                  value={String(portfolioSummary?.tracked_keywords || 0)}
                  summary="Searches configured across the portfolio."
                />
                <KpiCard
                  label="Average position"
                  value={
                    portfolioSummary?.average_position === null ||
                    portfolioSummary?.average_position === undefined
                      ? "—"
                      : `#${portfolioSummary.average_position}`
                  }
                  summary="Weighted across searches with a stored result."
                  tone="highlight"
                />
                <KpiCard
                  label="Page-one searches"
                  value={String(portfolioSummary?.top_10_keywords || 0)}
                  summary="Latest positions from 1 through 10."
                />
                <KpiCard
                  label="Needs attention"
                  value={String(portfolioSummary?.declined_keywords || 0)}
                  summary="Searches that declined in the latest comparison."
                />
              </div>

              <div className="mt-4">
                <ChartCard
                  eyebrow="Location comparison"
                  title="Average search position by location"
                  summary="Lower position numbers are better. Use this comparison to see which location is currently closest to page one."
                  chart={
                    portfolioChartData.length > 0 ? (
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={portfolioChartData}>
                            <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                            <XAxis
                              dataKey="label"
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#a1a1aa", fontSize: 12 }}
                            />
                            <YAxis
                              reversed
                              domain={[100, 1]}
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#71717a", fontSize: 12 }}
                              width={36}
                            />
                            <Tooltip content={<RankingsTooltip />} />
                            <Bar
                              dataKey="position"
                              name="Average position"
                              fill="#FF6A1A"
                              radius={[6, 6, 0, 0]}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <ChartEmptyState
                        title="No location comparison yet"
                        summary="Run at least one live ranking check for a location to add it to this chart."
                      />
                    )
                  }
                  footer={
                    <p className="text-sm text-zinc-400">
                      Select a location in the table below to see its individual phrases and history.
                    </p>
                  }
                />
              </div>

              <div className="mt-4 overflow-x-auto rounded-md border border-[#26272c]">
                <table className="w-full border-collapse text-left">
                  <thead className="bg-[#111214]">
                    <tr>
                      {["Location", "Tracked", "Avg. position", "Top 10", "Movement", "Latest check"].map(
                        (label) => (
                          <th
                            key={label}
                            className="px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500"
                          >
                            {label}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {portfolioLocations.map((location) => (
                      <tr
                        key={location.business_location_id || location.campaign_ids.join("-")}
                        className="border-t border-[#26272c]"
                      >
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => {
                              const campaignId = location.campaign_ids[0];
                              if (campaignId) {
                                setSelectedCampaignId(campaignId);
                                setViewMode("location");
                                setNotice("");
                              }
                            }}
                            className="text-left text-sm font-semibold text-white underline decoration-accent-500/50 underline-offset-4 transition hover:text-accent-200"
                          >
                            {location.location_name}
                          </button>
                          <p className="mt-0.5 text-xs text-zinc-500">
                            {location.primary_city || location.domains[0] || "Location details pending"}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-sm text-zinc-200">
                          {location.tracked_keywords}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-zinc-100">
                          {location.average_position === null ||
                          location.average_position === undefined
                            ? "—"
                            : `#${location.average_position}`}
                        </td>
                        <td className="px-4 py-3 text-sm text-zinc-200">
                          {location.top_10_keywords}
                        </td>
                        <td className="px-4 py-3 text-xs">
                          <span className="text-emerald-200">
                            {location.improved_keywords} up
                          </span>
                          <span className="mx-1.5 text-zinc-600">/</span>
                          <span className="text-rose-200">
                            {location.declined_keywords} down
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-zinc-400">
                          {location.latest_captured_at
                            ? new Date(location.latest_captured_at).toLocaleString()
                            : "Not run yet"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            ) : null}

            {viewMode === "location" ? (
            <>
            <section className="rounded-md border border-[#3a2a20] bg-[linear-gradient(135deg,rgba(255,106,26,0.12),rgba(20,21,24,0.96)_48%)] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">
                Your ranking story
              </p>
              <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                    {strongestPosition?.keyword
                      ? `${strongestPosition.keyword} is currently your strongest phrase`
                      : "Run a ranking check to establish your strongest phrase"}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    {nextOpportunity?.keyword
                      ? `Focus next on “${nextOpportunity.keyword}” at position ${coerceNumber(nextOpportunity.position, 0)}. It is the closest tracked phrase outside page one.`
                      : pageOneCount > 0
                        ? `${pageOneCount} tracked phrase${pageOneCount === 1 ? " is" : "s are"} already on page one. Protect those positions and watch for declines.`
                        : "Add tracked phrases and run a live check before making ranking decisions."}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void runLiveCheck()}
                  disabled={busyAction !== "" || trackedKeywords.length === 0}
                  className="shrink-0 rounded-md border border-accent-500/40 bg-accent-500 px-4 py-2 text-sm font-semibold text-white shadow-[0_0_18px_rgba(255,106,26,0.16)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "run" ? "Checking..." : "Run live check"}
                </button>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard
                  label="Strongest phrase"
                  value={
                    strongestPosition
                      ? `#${coerceNumber(strongestPosition.position, 0)}`
                      : "—"
                  }
                  summary={
                    strongestPosition?.keyword ||
                    "No stored ranking is available for this location."
                  }
                  tone="highlight"
                />
                <KpiCard
                  label="Weakest phrase"
                  value={
                    weakestPosition
                      ? `#${coerceNumber(weakestPosition.position, 0)}`
                      : "—"
                  }
                  summary={
                    weakestPosition?.keyword ||
                    "No stored ranking is available for this location."
                  }
                />
                <KpiCard
                  label="Page one"
                  value={`${pageOneCount}/${trackedTerms}`}
                  summary={
                    pageOneCount > 0
                      ? "Tracked phrases currently appearing in positions 1–10."
                      : "No tracked phrases are on page one yet."
                  }
                />
                <KpiCard
                  label="Latest check"
                  value={latestCapturedAt ? "Stored" : "Not run"}
                  summary={
                    latestCapturedAt
                      ? new Date(latestCapturedAt).toLocaleString()
                      : "Run a live check to create the first ranking snapshot."
                  }
                />
              </div>
            </section>

            <div className="grid gap-5 xl:grid-cols-2">
              <ChartCard
                eyebrow="History"
                title="How tracked phrases changed over time"
                summary="Each line is one tracked phrase. Lower position numbers are better, and the newest check appears on the right."
                chart={
                  rankingHistory.data.length >= 2 && rankingHistory.series.length > 0 ? (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={rankingHistory.data}>
                          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                          <XAxis
                            dataKey="label"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#71717a", fontSize: 12 }}
                          />
                          <YAxis
                            reversed
                            domain={[100, 1]}
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#71717a", fontSize: 12 }}
                            width={36}
                          />
                          <Tooltip content={<RankingsTooltip />} />
                          {rankingHistory.series.map((series, index) => (
                            <Line
                              key={series.id}
                              type="monotone"
                              dataKey={series.id}
                              name={series.label}
                              stroke={["#FF6A1A", "#38bdf8", "#22c55e", "#f59e0b", "#a78bfa"][index]}
                              strokeWidth={2.5}
                              dot={{ r: 3 }}
                              connectNulls
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <ChartEmptyState
                      title="One check is not a trend"
                      summary="Run another live check later to see whether each phrase improved, declined, or stayed stable."
                    />
                  )
                }
                footer={
                  <div className="flex flex-wrap gap-3">
                    {rankingHistory.series.map((series, index) => (
                      <span key={series.id} className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{
                            backgroundColor: ["#FF6A1A", "#38bdf8", "#22c55e", "#f59e0b", "#a78bfa"][index],
                          }}
                        />
                        {series.label}
                      </span>
                    ))}
                  </div>
                }
              />

              <ChartCard
                eyebrow="Position distribution"
                title="How close your phrases are to page one"
                summary="This groups current positions so you can see whether the next opportunity is close or still needs substantial work."
                chart={
                  trends.length > 0 ? (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={rankingDistributionData}>
                          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                          <XAxis
                            dataKey="label"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#a1a1aa", fontSize: 12 }}
                          />
                          <YAxis
                            allowDecimals={false}
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#71717a", fontSize: 12 }}
                            width={28}
                          />
                          <Tooltip content={<RankingsTooltip />} />
                          <Bar dataKey="count" name="Tracked phrases" radius={[6, 6, 0, 0]}>
                            {rankingDistributionData.map((entry, index) => (
                              <Cell
                                key={entry.label}
                                fill={
                                  index <= 1
                                    ? "#22c55e"
                                    : index === 2
                                      ? "#FF6A1A"
                                      : "#52525b"
                                }
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <ChartEmptyState
                      title="No positions to group yet"
                      summary="Run the first live ranking check to see how many phrases are on page one or close behind."
                    />
                  )
                }
                footer={
                  <p className="text-sm text-zinc-400">
                    {nextOpportunity?.keyword
                      ? `Best near-term opportunity: “${nextOpportunity.keyword}” at #${coerceNumber(nextOpportunity.position, 0)}.`
                      : "No tracked phrase is currently between positions 11 and 30."}
                  </p>
                }
              />
            </div>

            <details
              id="ranking-setup"
              className="rounded-md border border-[#26272c] bg-[#111214] p-4"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-zinc-100">
                Ranking setup and tracked phrases
                <span className="text-xs font-normal text-zinc-500">
                  {trackedKeywords.length} configured · expand to manage
                </span>
              </summary>
              <div className="mt-5 space-y-5 border-t border-[#26272c] pt-5">
            <section
              id="keyword-onboarding"
              className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]"
            >
              <form
                onSubmit={addTrackedKeywords}
                className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Location keyword onboarding
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Add the searches customers use in {selectedPortfolioLocation?.location_name || "this location"}
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Paste one search per line or separate them with commas. Duplicates are skipped automatically.
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Keyword group
                    <input
                      value={clusterName}
                      onChange={(event) => setClusterName(event.target.value)}
                      placeholder="Core services"
                      className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm normal-case tracking-normal text-white outline-none placeholder:text-zinc-600"
                    />
                  </label>
                  <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Search location
                    <input
                      value={locationTarget}
                      onChange={(event) => setLocationTarget(event.target.value)}
                      placeholder="Reno, Nevada, United States"
                      className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm normal-case tracking-normal text-white outline-none placeholder:text-zinc-600"
                    />
                  </label>
                </div>
                <label className="mt-3 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  Search terms
                  <textarea
                    value={keywordInput}
                    onChange={(event) => setKeywordInput(event.target.value)}
                    rows={5}
                    placeholder={"junk removal reno\nsame day junk removal\nappliance removal near me"}
                    className="mt-1.5 w-full resize-y rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm normal-case leading-6 tracking-normal text-white outline-none placeholder:text-zinc-600"
                  />
                </label>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-zinc-500">
                    {trackedKeywords.length} currently configured for this campaign.
                  </p>
                  <button
                    type="submit"
                    disabled={busyAction !== "" || parseKeywordInput(keywordInput).length === 0}
                    className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "keywords" ? "Adding..." : "Add tracked searches"}
                  </button>
                </div>
              </form>

              <form
                onSubmit={connectSearchData}
                className="rounded-md border border-[#3a2a20] bg-[#171518] p-5"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Search data connection
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Connect search data
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Credentials are encrypted for this organization and never returned to the browser.
                </p>
                <label className="mt-4 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  API login
                  <input
                    value={providerLogin}
                    onChange={(event) => setProviderLogin(event.target.value)}
                    autoComplete="username"
                    className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm normal-case tracking-normal text-white outline-none"
                  />
                </label>
                <label className="mt-3 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  API password
                  <input
                    type="password"
                    value={providerPassword}
                    onChange={(event) => setProviderPassword(event.target.value)}
                    autoComplete="current-password"
                    className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm normal-case tracking-normal text-white outline-none"
                  />
                </label>
                <button
                  type="submit"
                  disabled={busyAction !== "" || !providerLogin.trim() || !providerPassword}
                  className="mt-4 w-full rounded-md border border-accent-500/35 bg-accent-500/12 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "provider" ? "Saving..." : "Save connection"}
                </button>
              </form>
            </section>

            {trackedKeywords.length > 0 ? (
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Configured searches
                    </p>
                    <h2 className="mt-1 text-lg font-semibold text-white">
                      {selectedCampaign?.name || "Selected campaign"}
                    </h2>
                  </div>
                  <button
                    type="button"
                    onClick={() => void runLiveCheck()}
                    disabled={busyAction !== ""}
                    className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3.5 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {busyAction === "run" ? "Checking..." : "Run live ranking check"}
                  </button>
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-2">
                  {trackedKeywords.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between gap-3 rounded-md border border-[#26272c] bg-[#111214] px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">{item.keyword}</p>
                        <p className="mt-0.5 truncate text-xs text-zinc-500">
                          {item.cluster} · {item.location_code}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void removeTrackedKeyword(item.id)}
                        disabled={busyAction !== ""}
                        className="rounded-md border border-[#303137] px-2 py-1 text-xs text-zinc-400 transition hover:text-rose-200 disabled:opacity-50"
                      >
                        {busyAction === `delete-${item.id}` ? "Removing..." : "Remove"}
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
              </div>
            </details>

            {trackedTerms === 0 ? (
              <EmptyState
                title="No tracked searches yet"
                summary="Add the searches customers use for this location, then run a fresh check to see real positions."
                actionLabel="Add tracked searches"
                onAction={() => {
                  const setup = document.getElementById(
                    "ranking-setup",
                  ) as HTMLDetailsElement | null;
                  if (setup) {
                    setup.open = true;
                  }
                  document
                    .getElementById("keyword-onboarding")
                    ?.scrollIntoView({ behavior: "smooth" });
                }}
              />
            ) : (
              <>
                <div className="grid gap-5 xl:grid-cols-2">
                  <ChartCard
                    eyebrow="Visibility"
                    title="Best current positions"
                    summary="Lower positions are better. This chart reflects the latest stored snapshot, not guaranteed live search visibility."
                    chart={
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={positionChartData}>
                            <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                            <XAxis
                              dataKey="label"
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#71717a", fontSize: 12 }}
                            />
                            <YAxis
                              reversed
                              domain={[100, 1]}
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#71717a", fontSize: 12 }}
                              width={36}
                            />
                            <Tooltip content={<RankingsTooltip />} />
                            <Bar dataKey="position" name="Position" radius={[6, 6, 0, 0]}>
                              {positionChartData.map((entry) => (
                                <Cell
                                  key={entry.label}
                                  fill={entry.position <= 10 ? "#FF6A1A" : "#52525b"}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    }
                  />

                  <ChartCard
                    eyebrow="Movement"
                    title="Largest gains and drops"
                    summary="Positive numbers mean a term moved up in the latest stored comparison. Treat stale or synthetic movement as directional only."
                    chart={
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={movementChartData}>
                            <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                            <XAxis
                              dataKey="label"
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#71717a", fontSize: 12 }}
                            />
                            <YAxis
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#71717a", fontSize: 12 }}
                              width={36}
                            />
                            <Tooltip content={<RankingsTooltip />} />
                            <Bar dataKey="movement" name="Movement" radius={[6, 6, 0, 0]}>
                              {movementChartData.map((entry) => (
                                <Cell
                                  key={entry.label}
                                  fill={entry.movement >= 0 ? "#22c55e" : "#f43f5e"}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    }
                  />
                </div>

                <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Search terms
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Which search terms improved or dropped
                    </h2>
                    <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                      Start with dropped terms, but only treat the table as current if the runtime truth above says ranking coverage is fresh enough.
                    </p>
                  </div>

                  <div className="overflow-x-auto rounded-md border border-[#26272c]">
                    <table className="w-full border-collapse text-left">
                      <thead className="bg-[#111214]">
                        <tr>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Search term
                          </th>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Position
                          </th>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Movement
                          </th>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Location
                          </th>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Cluster
                          </th>
                          <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            What to watch
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...trends]
                          .sort((left, right) => {
                            const leftDelta = left.delta ?? -999;
                            const rightDelta = right.delta ?? -999;
                            if (leftDelta !== rightDelta) {
                              return rightDelta - leftDelta;
                            }
                            return coerceNumber(left.position, 999) - coerceNumber(right.position, 999);
                          })
                          .map((trend) => (
                            <tr key={trend.keyword_id || trend.keyword} className="border-t border-[#26272c] align-top">
                              <td className="px-4 py-4 text-sm text-zinc-100">
                                <div>
                                  <p className="font-medium text-white">{trend.keyword || "Unnamed term"}</p>
                                  <p className="mt-1 text-xs text-zinc-500">
                                    Confidence {Math.round((trend.confidence ?? 0) * 100)}%
                                  </p>
                                </div>
                              </td>
                              <td className="px-4 py-4 text-sm text-zinc-200">
                                #{coerceNumber(trend.position, 0)}
                              </td>
                              <td className="px-4 py-4 text-sm">
                                <span
                                  className={`inline-flex rounded-md border px-2 py-1 text-xs font-medium ${getMovementTone(trend.delta)}`}
                                >
                                  {formatDelta(trend.delta)}
                                </span>
                              </td>
                              <td className="px-4 py-4 text-sm text-zinc-300">
                                {trend.location_code || "US"}
                              </td>
                              <td className="px-4 py-4 text-sm text-zinc-300">
                                {trend.cluster || "Core terms"}
                              </td>
                              <td className="px-4 py-4 text-sm leading-6 text-zinc-300">
                                {describeWatchItem(trend)}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
            </>
            ) : null}
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
