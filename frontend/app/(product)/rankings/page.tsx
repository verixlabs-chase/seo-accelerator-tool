"use client";

import { useEffect, useMemo, useState } from "react";
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
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [trends, setTrends] = useState<RankTrend[]>([]);
  const [rankingsTruth, setRankingsTruth] = useState<RuntimeTruth | null>(null);
  const [trackedKeywordCount, setTrackedKeywordCount] = useState(0);
  const [latestCapturedAt, setLatestCapturedAt] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
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
      return;
    }

    const response = (await platformApi(
      `/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    )) as RankTrendResponse;
    setTrends(Array.isArray(response?.items) ? (response.items as RankTrend[]) : []);
    setRankingsTruth((response?.truth as RuntimeTruth) || null);
    setTrackedKeywordCount(Number(response?.tracked_keywords || 0));
    setLatestCapturedAt(response?.latest_captured_at || "");
  }

  async function refreshRankings(campaignId: string) {
    if (!campaignId) {
      return;
    }

    setRefreshing(true);
    setError("");

    try {
      await loadTrends(campaignId);
      setNotice("Stored ranking rows reloaded. This does not force a new live provider check by itself.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh rankings.");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        await platformApi("/auth/me", { method: "GET" });
        const items = await loadCampaigns();
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

  const rankedTrends = useMemo(
    () =>
      [...trends].sort((left, right) => {
        const leftPosition = coerceNumber(left.position, 999);
        const rightPosition = coerceNumber(right.position, 999);
        return leftPosition - rightPosition;
      }),
    [trends],
  );

  const trackedTerms = trends.length;
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
