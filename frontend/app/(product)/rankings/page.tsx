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
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

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
      return;
    }

    const response = await platformApi(
      `/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    );
    setTrends(Array.isArray(response?.items) ? (response.items as RankTrend[]) : []);
  }

  async function refreshRankings(campaignId: string) {
    if (!campaignId) {
      return;
    }

    setRefreshing(true);
    setError("");

    try {
      await loadTrends(campaignId);
      setNotice("Rankings refreshed.");
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
    strongestPosition,
  ]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Tracked searches",
        value: trackedTerms > 0 ? `${trackedTerms} active` : "None yet",
        tone: trackedTerms > 0 ? "success" : "warning",
      },
      {
        label: "Page-one terms",
        value: pageOneCount > 0 ? `${pageOneCount} on page one` : "No page-one terms",
        tone: pageOneCount > 0 ? "success" : "warning",
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
    [droppedTerms, improvedTerms, pageOneCount, trackedTerms],
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
      dateRangeLabel="Live ranking data"
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
          summary="Use this page to see your current positions, what moved up or down, and which search terms need attention next."
        />

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
                summary="Start your first ranking check from the dashboard. Once searches are tracked, this page will show current positions and movement."
                actionLabel="Go to dashboard"
                onAction={() => router.push("/dashboard")}
              />
            ) : (
              <>
                <div className="grid gap-4 xl:grid-cols-4">
                  <KpiCard
                    label="Tracked searches"
                    value={String(trackedTerms)}
                    summary="These are the search terms currently being watched for the active business."
                  />
                  <KpiCard
                    label="Page-one terms"
                    value={String(pageOneCount)}
                    changeLabel={pageOneCount > 0 ? "Visible now" : undefined}
                    summary="These searches are already showing on page one and should be protected."
                    tone="highlight"
                  />
                  <KpiCard
                    label="Improved"
                    value={String(improvedTerms)}
                    changeLabel={biggestWinner ? formatDelta(biggestWinner.delta) : undefined}
                    summary={
                      biggestWinner?.keyword
                        ? `Biggest winner: ${biggestWinner.keyword}.`
                        : "No upward movement is showing yet."
                    }
                  />
                  <KpiCard
                    label="Dropped"
                    value={String(droppedTerms)}
                    changeLabel={biggestDrop ? formatDelta(biggestDrop.delta) : undefined}
                    summary={
                      biggestDrop?.keyword
                        ? `Biggest drop: ${biggestDrop.keyword}.`
                        : "No drops are showing in the latest ranking set."
                    }
                  />
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                  <ChartCard
                    eyebrow="Visibility"
                    title="Best current positions"
                    summary="Lower positions are better. This highlights the search terms with the strongest current visibility."
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
                    summary="Positive numbers mean a term moved up. Negative numbers mean it slipped and may need review."
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
                      Start with the dropped terms, then review the rising terms that are getting closer to page one.
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
