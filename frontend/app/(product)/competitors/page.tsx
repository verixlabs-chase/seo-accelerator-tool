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
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type Competitor = {
  id: string;
  campaign_id: string;
  domain: string;
  label?: string | null;
  created_at: string;
};

type GapItem = {
  competitor_id: string;
  domain: string;
  gap_score: number;
  position: number;
};

type SnapshotItem = {
  competitor_id: string;
  domain: string;
  keyword: string;
  position: number;
  visibility_score: number;
  signal_key: string;
  signal_value: string;
  signal_score: number;
  captured_at: string;
};

type SnapshotResult = {
  job_id: string | null;
  summary: { snapshots_collected: number };
  items: SnapshotItem[];
};

function toTitleCase(value?: string) {
  if (!value) return "Unknown";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatRelativeTime(value?: string) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const hours = Math.round(diffMs / 3600000);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(diffMs / 86400000), "day");
}

function gapScoreColor(score: number) {
  if (score >= 70) return "text-rose-400";
  if (score >= 40) return "text-amber-400";
  return "text-emerald-400";
}

function gapBarColor(score: number) {
  if (score >= 70) return "bg-rose-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-emerald-500";
}

export default function CompetitorsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [snapshotResult, setSnapshotResult] = useState<SnapshotResult | null>(null);
  const [newDomain, setNewDomain] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
    const response = await platformApi("/campaigns", { method: "GET" });
    const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
    setCampaigns(items);
    setSelectedCampaignId((current) => {
      if (current && items.some((item) => item.id === current)) return current;
      return items[0]?.id || "";
    });
    return items;
  }, []);

  const loadCompetitors = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setCompetitors([]);
      return;
    }
    const response = await platformApi(
      `/competitors?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    );
    setCompetitors(Array.isArray(response?.items) ? (response.items as Competitor[]) : []);
  }, []);

  const loadGaps = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setGaps([]);
      return;
    }
    const response = await platformApi(
      `/competitors/gaps?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    );
    setGaps(Array.isArray(response?.items) ? (response.items as GapItem[]) : []);
  }, []);

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

  async function addCompetitor() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    if (!newDomain.trim()) {
      setError("Domain is required.");
      return;
    }
    await runAction("add", async () => {
      const domain = newDomain.trim();
      await platformApi("/competitors", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          domain,
          label: newLabel.trim() || null,
        }),
      });
      setNewDomain("");
      setNewLabel("");
      await loadCompetitors(selectedCampaignId);
      setNotice(`Competitor "${domain}" added.`);
    });
  }

  async function collectSnapshot() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    await runAction("snapshot", async () => {
      const response = await platformApi(
        `/competitors/snapshots?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "GET" },
      );
      const raw = response as SnapshotResult | null;
      setSnapshotResult({
        job_id: raw?.job_id ?? null,
        summary: { snapshots_collected: raw?.summary?.snapshots_collected ?? 0 },
        items: Array.isArray(raw?.items) ? (raw.items as SnapshotItem[]) : [],
      });
      await loadGaps(selectedCampaignId);
      setNotice(
        "Snapshot collection queued. Results below reflect the current database state. Gap data will update once the job completes.",
      );
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
          await loadCompetitors(items[0].id);
          await loadGaps(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load competitors.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadCampaigns, loadCompetitors, loadGaps]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setSnapshotResult(null);
    void Promise.all([
      loadCompetitors(selectedCampaignId),
      loadGaps(selectedCampaignId),
    ]).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load competitors.");
    });
  }, [loadCompetitors, loadGaps, selectedCampaignId, loading]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const topGap = gaps.length > 0 ? [...gaps].sort((a, b) => b.gap_score - a.gap_score)[0] : null;

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Competitors",
        value: competitors.length > 0 ? `${competitors.length} tracked` : "None added",
        tone: competitors.length > 0 ? "success" : "warning",
      },
      {
        label: "Gap entries",
        value: gaps.length > 0 ? `${gaps.length} gap${gaps.length === 1 ? "" : "s"} found` : "No data yet",
        tone: gaps.length > 0 ? "info" : "warning",
      },
      {
        label: "Top gap score",
        value: topGap ? `${topGap.gap_score} — ${topGap.domain}` : "Not available",
        tone: topGap ? "info" : "warning",
      },
      {
        label: "Snapshot data",
        value: snapshotResult
          ? `${snapshotResult.summary.snapshots_collected} with data`
          : "Not yet collected",
        tone: snapshotResult?.summary.snapshots_collected ? "success" : "warning",
      },
    ],
    [competitors.length, gaps, snapshotResult, topGap],
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
      dateRangeLabel="Live competitor data"
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
            onClick={() => router.push("/opportunities")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            View opportunities
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Competitors"
          title="Track competitors and find visibility gaps"
          summary="Add competitor domains to monitor, then collect a snapshot to pull ranking and signal data. Gap scores show where competitors outrank you so you can prioritise where to catch up."
        />

        <TruthNotice title="Competitor gaps are only as current as the last collected snapshot.">
          Adding a competitor does not create live coverage by itself. Gap scores and snapshot rows
          reflect the latest stored crawl of competitor data, and queued snapshot jobs may take time
          before the database catches up.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading competitors"
            summary="Pulling competitor list and gap analysis for the active business."
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
            title="No business is ready yet"
            summary="Set up a business first so InsightOS can collect competitor data."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Competitors tracked"
                value={String(competitors.length)}
                summary="Domains currently being tracked for this business."
              />
              <KpiCard
                label="Gap entries"
                value={String(gaps.length)}
                summary="Ranking gap records found across all tracked competitors."
                tone={gaps.length > 0 ? "highlight" : undefined}
              />
              <KpiCard
                label="Top gap score"
                value={topGap ? String(topGap.gap_score) : "—"}
                changeLabel={topGap ? topGap.domain : undefined}
                summary={
                  topGap
                    ? `Highest gap score belongs to ${topGap.domain} at position ${topGap.position}.`
                    : "Collect a snapshot to see gap scores."
                }
              />
              <KpiCard
                label="Snapshot status"
                value={
                  snapshotResult
                    ? `${snapshotResult.summary.snapshots_collected} collected`
                    : "Not run"
                }
                summary={
                  snapshotResult
                    ? "A snapshot job was queued this session. Gap data reflects the latest database state."
                    : "Use the collect button below to pull fresh competitor data."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Setup
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Add a competitor
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Enter a competitor domain to start tracking its rankings and signals. Use the label
                  field to give it a friendly name.
                </p>

                <div className="mt-4 space-y-3">
                  <div>
                    <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Domain
                    </label>
                    <input
                      value={newDomain}
                      onChange={(event) => setNewDomain(event.target.value)}
                      placeholder="example.com"
                      className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Label{" "}
                      <span className="normal-case text-zinc-600">(optional)</span>
                    </label>
                    <input
                      value={newLabel}
                      onChange={(event) => setNewLabel(event.target.value)}
                      placeholder="e.g. Main rival"
                      className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                    />
                  </div>

                  <button
                    onClick={() => void addCompetitor()}
                    disabled={busyAction !== "" || !newDomain.trim()}
                    className="w-full rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "add" ? "Adding..." : "Add competitor"}
                  </button>
                </div>
              </section>

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Tracked
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Competitors for this business
                </h2>

                {competitors.length === 0 ? (
                  <EmptyState
                    title="No competitors added yet"
                    summary="Add a competitor domain using the form on the left to start tracking."
                  />
                ) : (
                  <div className="mt-4 space-y-3">
                    {competitors.map((competitor) => (
                      <div
                        key={competitor.id}
                        className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-white">
                              {competitor.label || competitor.domain}
                            </p>
                            {competitor.label ? (
                              <p className="mt-0.5 text-sm text-zinc-400">{competitor.domain}</p>
                            ) : null}
                          </div>
                          <span className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                            Added {formatRelativeTime(competitor.created_at)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="mb-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Analysis
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Gap analysis
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Gap scores show where tracked competitors outrank you. A higher score means a
                  larger gap to close. Scores are sorted from largest to smallest. Collect a
                  snapshot first if this section is empty.
                </p>
              </div>

              {gaps.length === 0 ? (
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-sm leading-6 text-zinc-400">
                    {competitors.length === 0
                      ? "Add competitors first, then collect a snapshot to see gap data here."
                      : "No gap data is available yet. Use the collect button below to pull the latest competitor ranking data."}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {[...gaps].sort((a, b) => b.gap_score - a.gap_score).map((gap) => (
                    <div
                      key={gap.competitor_id}
                      className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-white">{gap.domain}</p>
                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                            Ranking at position {gap.position}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            Gap score
                          </p>
                          <p className={`mt-1 text-lg font-semibold ${gapScoreColor(gap.gap_score)}`}>
                            {gap.gap_score}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[#26272c]">
                        <div
                          className={`h-full rounded-full ${gapBarColor(gap.gap_score)}`}
                          style={{ width: `${Math.min(100, gap.gap_score)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="mb-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Data collection
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Collect competitor snapshot
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Collecting a snapshot queues a background job that pulls ranking positions, page
                  visibility scores, and competitive signals for all tracked competitors. Gap data
                  refreshes once the job completes. Results shown below reflect the current database
                  state.
                </p>
              </div>

              {competitors.length === 0 ? (
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-sm leading-6 text-zinc-400">
                    Add at least one competitor before collecting a snapshot.
                  </p>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => void collectSnapshot()}
                    disabled={busyAction !== ""}
                    className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "snapshot" ? "Queuing..." : "Collect latest data"}
                  </button>

                  {snapshotResult ? (
                    <div className="mt-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Last collection result
                      </p>
                      <p className="mt-2 text-sm leading-6 text-zinc-300">
                        {snapshotResult.summary.snapshots_collected > 0
                          ? `${snapshotResult.summary.snapshots_collected} competitor${snapshotResult.summary.snapshots_collected === 1 ? "" : "s"} with snapshot data found in the database.`
                          : "No snapshot data was found in the database. The background job may still be running, or the connected provider may not have returned data."}
                        {snapshotResult.job_id ? (
                          <span className="ml-2 text-zinc-500">
                            Job queued successfully.
                          </span>
                        ) : (
                          <span className="ml-2 text-zinc-500">
                            No background job was queued — the message broker may be unavailable.
                          </span>
                        )}
                      </p>

                      {snapshotResult.items.length > 0 ? (
                        <div className="mt-4 space-y-3">
                          {snapshotResult.items.map((item, index) => (
                            <div
                              key={`${item.competitor_id}-${item.keyword}-${index}`}
                              className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium text-white">{item.domain}</p>
                                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                                    Keyword: {item.keyword} · Position {item.position}
                                  </p>
                                </div>
                                <div className="text-right">
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                                    Visibility
                                  </p>
                                  <p className="mt-1 text-sm text-zinc-200">
                                    {item.visibility_score.toFixed(1)}
                                  </p>
                                </div>
                              </div>
                              <div className="mt-3 grid gap-3 text-sm text-zinc-300 md:grid-cols-3">
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                                    Signal
                                  </p>
                                  <p className="mt-1">{toTitleCase(item.signal_key)}</p>
                                </div>
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                                    Value
                                  </p>
                                  <p className="mt-1">{item.signal_value}</p>
                                </div>
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                                    Captured
                                  </p>
                                  <p className="mt-1">{formatRelativeTime(item.captured_at)}</p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
