"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  ChartCard,
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
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [trends, setTrends] = useState<RankTrend[]>([]);
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
      return;
    }

    const [response, keywordsResponse] = await Promise.all([
      platformApi(
        `/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      ) as Promise<RankTrendResponse>,
      platformApi(
        `/rank/keywords?campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      ),
    ]);
    setTrends(Array.isArray(response?.items) ? (response.items as RankTrend[]) : []);
    setTrackedKeywords(
      Array.isArray(keywordsResponse?.items)
        ? (keywordsResponse.items as TrackedKeyword[])
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

  async function refreshRankings(campaignId: string) {
    if (!campaignId) {
      return;
    }

    setRefreshing(true);
    setError("");

    try {
      await Promise.all([loadTrends(campaignId), loadPortfolio()]);
      setNotice("Stored ranking rows reloaded. This does not force a new live provider check by itself.");
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
          : "No ranking snapshots were created. Check the provider setup and location keywords below.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run the live ranking check.");
    } finally {
      setBusyAction("");
    }
  }

  async function connectDataForSeo(event: FormEvent) {
    event.preventDefault();
    if (!me?.organization_id || !providerLogin.trim() || !providerPassword) {
      setError("DataForSEO login and password are required.");
      return;
    }
    setBusyAction("provider");
    setError("");
    setNotice("");
    try {
      await platformApi(
        `/organizations/${me.organization_id}/provider-credentials/dataforseo`,
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
      setNotice("DataForSEO credentials saved securely. You can run the first live check now.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save DataForSEO credentials.");
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

  const biggestWinner = useMemo(
    () =>
      [...trends]
        .filter((item) => (item.delta ?? 0) > 0)
        .sort((left, right) => (right.delta ?? 0) - (left.delta ?? 0))[0] ?? null,
    [trends],
  );

  const biggestDrop = useMemo(
    () =>
      [...trends]
        .filter((item) => (item.delta ?? 0) < 0)
        .sort((left, right) => (left.delta ?? 0) - (right.delta ?? 0))[0] ?? null,
    [trends],
  );

  const strongestPosition = rankedTrends[0] ?? null;

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

  const summary = useMemo(() => {
    if (!selectedCampaign) {
      return {
        title: "No business is selected yet",
        body: "Set up a business first so InsightOS can show where you appear in search.",
        focus: "Return to the dashboard to finish setup and start your first ranking check.",
      };
    }

    if (rankingsTruth?.classification === "unavailable") {
      return {
        title: `${selectedCampaign.name || "This business"} does not have reliable live ranking collection yet`,
        body: getRuntimeTruthSummary(
          rankingsTruth,
          "The current runtime cannot provide trustworthy live rank collection.",
        ),
        focus: "Treat any older stored positions as historical context only until provider setup and fresh collection are confirmed.",
      };
    }

    if (rankingsTruth?.classification === "synthetic") {
      return {
        title: "These rankings are synthetic test data",
        body: "The current runtime is using a fixture provider, so positions are useful for workflow testing, not real search intelligence.",
        focus: "Do not treat gains, drops, or page-one counts here as market truth.",
      };
    }

    if (rankingsTruth?.freshness_state === "stale") {
      return {
        title: "The latest ranking snapshot is stale",
        body: getRuntimeTruthSummary(
          rankingsTruth,
          "Ranking coverage exists, but it is not current enough to read as live movement.",
        ),
        focus: "Run a fresh ranking check before using movement or page-one counts for decisions.",
      };
    }

    if (trackedTerms === 0) {
      return {
        title: `${selectedCampaign.name || "This business"} has no ranking data yet`,
        body: "Ranking results will appear here after your first tracked search and ranking check run.",
        focus: "Go back to the dashboard and start the first ranking check for this business.",
      };
    }

    if (droppedTerms > improvedTerms && biggestDrop?.keyword) {
      return {
        title: `${droppedTerms} tracked searches dropped in the latest update`,
        body: `The biggest drop was "${biggestDrop.keyword}" at ${formatDelta(biggestDrop.delta)}. This is the first term to review.`,
        focus: "Check the dropped terms first, then refresh rankings after any page or content updates.",
      };
    }

    if (biggestWinner?.keyword) {
      return {
        title: `${improvedTerms} tracked searches improved`,
        body: `The strongest gain was "${biggestWinner.keyword}" at ${formatDelta(biggestWinner.delta)}.`,
        focus: pageOneCount > 0
          ? "Protect the terms already on page one and watch any rising terms that are close behind."
          : "Keep watching the rising terms that are moving closer to page one.",
      };
    }

    return {
      title: `${pageOneCount} tracked searches are on page one`,
      body: strongestPosition?.keyword
        ? `"${strongestPosition.keyword}" is your strongest visible term right now at position ${coerceNumber(strongestPosition.position, 0)}.`
        : "Your ranking set is stable right now.",
      focus: "Watch for drops on page-one terms first, then review the terms just outside the top 10.",
    };
  }, [
    selectedCampaign,
    trackedTerms,
    droppedTerms,
    improvedTerms,
    biggestDrop,
    biggestWinner,
    pageOneCount,
    rankingsTruth,
    strongestPosition,
  ]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Runtime truth",
        rankingsTruth,
        "Rankings can be synthetic, stale, or unavailable depending on provider setup and snapshot freshness.",
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
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed campaign"} / ${selectedCampaign.domain || "No domain"}`
          : "No campaign selected"
      }
      dateRangeLabel="Stored ranking snapshots"
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
            onClick={() => void runLiveCheck()}
            disabled={busyAction !== "" || trackedKeywords.length === 0 || !selectedCampaignId}
            className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busyAction === "run" ? "Checking..." : "Run live check"}
          </button>
          <button
            onClick={() => void refreshRankings(selectedCampaignId)}
            disabled={refreshing || !selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Refreshing..." : "Refresh"}
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
          eyebrow="Rankings"
          title="Where your business shows up in search"
          summary="Use this page to review stored ranking snapshots, source quality, and which search terms need attention next without overreading thin or stale data."
        />

        <TruthNotice title="Stored ranking rows are not proof of live search intelligence.">
          Ranking movement is only as trustworthy as the provider setup and freshness behind it.
          Synthetic, stale, or setup-thin ranking states should be treated as directional or historical, not live market truth.
        </TruthNotice>

        {rankingsTruth ? (
          <TruthNotice title="Current runtime truth" tone="warning">
            {getRuntimeTruthSummary(
              rankingsTruth,
              "Ranking runtime status is not available yet.",
            )}
          </TruthNotice>
        ) : null}

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
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Multi-location portfolio
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    Compare every location at a glance
                  </h2>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                    These totals roll up the latest stored ranking for each tracked search.
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
                          <p className="text-sm font-medium text-white">{location.location_name}</p>
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

            <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
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
                onSubmit={connectDataForSeo}
                className="rounded-md border border-[#3a2a20] bg-[#171518] p-5"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Live ranking provider
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Connect DataForSEO
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
                  {busyAction === "provider" ? "Saving..." : "Save provider credentials"}
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

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Summary
              </p>
              <div className="mt-3 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <div>
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                    {summary.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{summary.body}</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What to watch next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{summary.focus}</p>
                </div>
              </div>
            </section>

            {trackedTerms === 0 ? (
              <EmptyState
                title="No tracked searches yet"
                summary="Start your first ranking check from the dashboard. Configured terms and fresh provider-backed snapshots are both required before this page should be treated as live ranking intelligence."
                actionLabel="Go to dashboard"
                onAction={() => router.push("/dashboard")}
              />
            ) : (
              <>
                <div className="grid gap-4 xl:grid-cols-4">
                  <KpiCard
                    label="Tracked searches"
                    value={String(trackedTerms)}
                    summary="These are configured tracked searches. Configuration alone does not prove fresh live ranking coverage."
                  />
                  <KpiCard
                    label="Page-one terms"
                    value={String(pageOneCount)}
                    changeLabel={pageOneCount > 0 ? "Visible now" : undefined}
                    summary="These counts come from the latest stored snapshot and should only be treated as live when provider truth is current."
                    tone="highlight"
                  />
                  <KpiCard
                    label="Improved"
                    value={String(improvedTerms)}
                    changeLabel={biggestWinner ? formatDelta(biggestWinner.delta) : undefined}
                    summary={
                      biggestWinner?.keyword
                        ? `Biggest winner: ${biggestWinner.keyword}.`
                        : "No upward movement is showing in the latest stored snapshot."
                    }
                  />
                  <KpiCard
                    label="Dropped"
                    value={String(droppedTerms)}
                    changeLabel={biggestDrop ? formatDelta(biggestDrop.delta) : undefined}
                    summary={
                      biggestDrop?.keyword
                        ? `Biggest drop: ${biggestDrop.keyword}.`
                        : "No drops are showing in the latest stored ranking set."
                    }
                  />
                </div>

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
      </section>
    </AppShell>
  );
}
