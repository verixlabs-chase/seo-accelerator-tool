"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ActionDrawer,
  AppShell,
  ChartCard,
  EmptyState,
  KpiCard,
  LoadingCard,
  OnboardingWizard,
  useLocationContext,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { clearAuthSession } from "../../lib/authStorage";
import { platformApi } from "../../platform/api";
import {
  getSearchConsoleOwnerSummary,
  getCrawlWorkflowState,
  getRankingWorkflowState,
  getReportWorkflowState,
  getSetupWorkflowState,
  isDashboardDataCurrent,
  isFailedStatus,
  isPendingStatus,
} from "../truth/dashboardTruth.mjs";
import {
  buildRuntimeTruthSignal,
  getRuntimeTruthSummary,
} from "../truth/runtimeTruth.mjs";

type Me = {
  id?: string;
  tenant_id?: string;
  organization_id?: string;
};

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type CrawlRun = {
  id?: string;
  status?: string;
  crawl_type?: string;
  created_at?: string;
  updated_at?: string;
};

type RankTrend = {
  id?: string;
  keyword?: string;
  position?: number | string;
  created_at?: string;
  updated_at?: string;
};

type RankTrendResponse = {
  items?: RankTrend[];
  tracked_keywords?: number;
  latest_captured_at?: string | null;
  truth?: RuntimeTruth;
};

type Report = {
  id?: string;
  month_number?: number | string;
  report_status?: string;
  created_at?: string;
  updated_at?: string;
};

type SearchConsolePoint = {
  date: string;
  clicks: number;
  impressions: number;
  ctr_percent: number;
  avg_position?: number | null;
};

type SearchConsoleMetrics = {
  campaign_id: string;
  data_status: "not_connected" | "no_data" | "ready";
  date_from?: string | null;
  date_to?: string | null;
  data_days: number;
  summary?: {
    clicks: number;
    impressions: number;
    ctr_percent: number;
    avg_position?: number | null;
  } | null;
  comparison?: {
    period_days: number;
    clicks_change_percent?: number | null;
    impressions_change_percent?: number | null;
    ctr_change_points?: number | null;
    position_improvement?: number | null;
  } | null;
  connection?: {
    status: string;
    last_success_at?: string | null;
    external_resource_name?: string | null;
    source_truth?: string;
  } | null;
  points: SearchConsolePoint[];
};

type WorkflowState = {
  label: string;
  status: string;
  tone: "success" | "warning" | "info" | "danger";
  detail: string;
  nextStep: string;
};

function toTitleCase(value?: string) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function withScheme(domain: string) {
  if (!domain) {
    return "";
  }

  if (domain.startsWith("http://") || domain.startsWith("https://")) {
    return domain;
  }

  return `https://${domain}`;
}

function formatRelativeTime(value?: string) {
  if (!value) {
    return "No recent activity";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No recent activity";
  }

  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const minutes = Math.round(diffMs / 60000);

  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }

  const hours = Math.round(diffMs / 3600000);
  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(diffMs / 86400000);
  return formatter.format(days, "day");
}

function coerceNumber(value: number | string | undefined, fallback = 0) {
  if (typeof value === "number") {
    return value;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatMetricDate(value?: string | null) {
  if (!value) {
    return "No data yet";
  }
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(parsed);
}

function formatChange(value?: number | null, noun = "visits") {
  if (value === null || value === undefined) {
    return "New baseline";
  }
  if (value === 0) {
    return `No change in ${noun}`;
  }
  return `${value > 0 ? "Up" : "Down"} ${Math.abs(value).toFixed(1)}%`;
}

function getWorkflowToneClass(tone: string) {
  if (tone === "success") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }

  if (tone === "danger") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }

  if (tone === "info") {
    return "border-accent-500/20 bg-accent-500/10 text-zinc-100";
  }

  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function SectionHeading({
  eyebrow,
  title,
  summary,
}: {
  eyebrow: string;
  title: string;
  summary: string;
}) {
  return (
    <div className="mb-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {eyebrow}
      </p>
      <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
        {title}
      </h2>
      <p className="mt-1.5 max-w-3xl text-sm leading-5 text-zinc-300">{summary}</p>
    </div>
  );
}

function BriefingCard({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-white">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-300">{body}</p>
    </section>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ color?: string; value?: number; name?: string }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-2.5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {label}
      </p>
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

function SearchConsoleTrendChart({
  data,
}: {
  data: Array<{ label: string; clicks: number; impressions: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="searchImpressionsFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#FF944F" stopOpacity={0.28} />
              <stop offset="95%" stopColor="#FF944F" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            minTickGap={22}
          />
          <YAxis
            yAxisId="clicks"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            width={34}
            allowDecimals={false}
          />
          <YAxis
            yAxisId="impressions"
            orientation="right"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            width={46}
            allowDecimals={false}
          />
          <Tooltip content={<TrendTooltip />} />
          <Area
            yAxisId="impressions"
            type="monotone"
            dataKey="impressions"
            stroke="#FF944F"
            strokeWidth={1.8}
            fill="url(#searchImpressionsFill)"
            name="Times shown"
          />
          <Line
            yAxisId="clicks"
            type="monotone"
            dataKey="clicks"
            stroke="#FF6A1A"
            strokeWidth={2.4}
            dot={false}
            activeDot={{ r: 4, fill: "#FF6A1A", stroke: "#0a0a0a", strokeWidth: 2 }}
            name="Visits"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function SearchPositionTrendChart({
  data,
}: {
  data: Array<{ label: string; avgPosition: number | null }>;
}) {
  const positionData = data.filter((point) => point.avgPosition !== null);

  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={positionData}>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            minTickGap={22}
          />
          <YAxis
            reversed
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            width={42}
          />
          <Tooltip content={<TrendTooltip />} />
          <Line
            type="monotone"
            dataKey="avgPosition"
            stroke="#FF6A1A"
            strokeWidth={2.4}
            dot={false}
            activeDot={{ r: 4, fill: "#FF6A1A", stroke: "#0a0a0a", strokeWidth: 2 }}
            name="Average position"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function SearchPerformanceOverview({
  campaign,
  metrics,
  trend,
  onOpenSettings,
}: {
  campaign: Campaign;
  metrics: SearchConsoleMetrics | null;
  trend: Array<{
    label: string;
    clicks: number;
    impressions: number;
    avgPosition: number | null;
  }>;
  onOpenSettings: () => void;
}) {
  const isReady = metrics?.data_status === "ready" && Boolean(metrics.summary);

  return (
    <section id="performance-overview" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SectionHeading
          eyebrow="Performance overview"
          title={`How customers found ${campaign.name || "this location"} on Google`}
          summary={
            isReady
              ? `Real Google Search data from ${formatMetricDate(
                  metrics?.date_from,
                )} through ${formatMetricDate(metrics?.date_to)}.`
              : "Connect this location's Google website property to see search appearances, visits, and position trends."
          }
        />
        <span
          className={`mb-4 rounded-md border px-2.5 py-1 text-xs font-semibold ${
            isReady
              ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
              : "border-amber-500/25 bg-amber-500/10 text-amber-100"
          }`}
        >
          {isReady
            ? `Updated through ${formatMetricDate(metrics?.date_to)}`
            : metrics?.data_status === "not_connected"
              ? "Connection needed"
              : "Waiting for Google data"}
        </span>
      </div>

      {isReady && metrics?.summary ? (
        <div className="flex flex-col gap-4">
          <p className="order-3 border-l-2 border-accent-500/50 px-3 py-1 text-sm leading-6 text-zinc-300">
            {getSearchConsoleOwnerSummary(metrics, campaign.name || "This location")}
          </p>

          <div className="order-2 grid gap-4 xl:grid-cols-4">
            <KpiCard
              label="Visits from Google"
              value={metrics.summary.clicks.toLocaleString("en-US")}
              changeLabel={formatChange(
                metrics.comparison?.clicks_change_percent,
                "visits",
              )}
              summary="People who clicked from Google Search and reached your website."
              tone="highlight"
            />
            <KpiCard
              label="Times you appeared"
              value={metrics.summary.impressions.toLocaleString("en-US")}
              changeLabel={formatChange(
                metrics.comparison?.impressions_change_percent,
                "appearances",
              )}
              summary="How often your website appeared in Google search results."
            />
            <KpiCard
              label="Appearance-to-visit rate"
              value={`${metrics.summary.ctr_percent.toFixed(1)}%`}
              changeLabel={
                metrics.comparison?.ctr_change_points === null ||
                metrics.comparison?.ctr_change_points === undefined
                  ? "New baseline"
                  : `${
                      metrics.comparison.ctr_change_points >= 0 ? "Up " : "Down "
                    }${Math.abs(metrics.comparison.ctr_change_points).toFixed(1)} pts`
              }
              summary="The percentage of Google appearances that became website visits."
            />
            <KpiCard
              label="Average Google position"
              value={
                metrics.summary.avg_position === null ||
                metrics.summary.avg_position === undefined
                  ? "—"
                  : `#${metrics.summary.avg_position.toFixed(1)}`
              }
              changeLabel={
                metrics.comparison?.position_improvement === null ||
                metrics.comparison?.position_improvement === undefined
                  ? "New baseline"
                  : metrics.comparison.position_improvement === 0
                    ? "No change"
                    : metrics.comparison.position_improvement > 0
                      ? `Improved ${metrics.comparison.position_improvement.toFixed(1)}`
                      : `Dropped ${Math.abs(
                          metrics.comparison.position_improvement,
                        ).toFixed(1)}`
              }
              summary="Your average placement across Google searches. A smaller number is better."
            />
          </div>

          <div className="order-1 grid gap-5 xl:grid-cols-2">
            <ChartCard
              eyebrow="Customer discovery"
              title="Google appearances and website visits"
              summary="The light area shows how often you appeared. The orange line shows visits."
              chart={<SearchConsoleTrendChart data={trend} />}
              footer={
                <p className="text-sm leading-5 text-zinc-300">
                  Compared with the prior {metrics.comparison?.period_days || 14} available days.
                </p>
              }
            />
            <ChartCard
              eyebrow="Search position"
              title="Average Google position by day"
              summary="Lines moving upward are better because a smaller position number is closer to the top."
              chart={<SearchPositionTrendChart data={trend} />}
              footer={
                <p className="text-sm leading-5 text-zinc-300">
                  Search Console normally reports data a couple of days behind.
                </p>
              }
            />
          </div>

          <p className="order-4 text-xs leading-5 text-zinc-500">
            Source:{" "}
            {metrics.connection?.external_resource_name ||
              campaign.domain ||
              "Google Search Console"}
            . Last synced {formatRelativeTime(metrics.connection?.last_success_at || undefined)}.
          </p>
        </div>
      ) : metrics ? (
        <EmptyState
          title={
            metrics.data_status === "not_connected"
              ? "Connect Search Console for this location"
              : "Search Console is connected, but data has not arrived yet"
          }
          summary={
            metrics.data_status === "not_connected"
              ? "Choose this location's Google Search Console website property in Settings, then run the first sync."
              : "Open Settings to check the connection and run a sync."
          }
          actionLabel="Open connection settings"
          onAction={onOpenSettings}
        />
      ) : (
        <LoadingCard
          title="Loading Google performance"
          summary={`Checking the Search Console results saved for ${
            campaign.name || "this location"
          }.`}
        />
      )}
    </section>
  );
}

function TimelineCard({
  recentActivity,
}: {
  recentActivity: Array<{ title: string; time: string; detail: string }>;
}) {
  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <SectionHeading
        eyebrow="Recent activity"
        title="Execution timeline"
        summary="This feed keeps operators and owners aligned on what the system changed, checked, and completed."
      />
      <div className="space-y-4">
        {recentActivity.map((item, index) => (
          <div key={item.title} className="flex gap-4">
            <div className="flex flex-col items-center">
              <div className="mt-1 h-3 w-3 border border-accent-500/30 bg-accent-500/90" />
              {index < recentActivity.length - 1 ? (
                <div className="mt-2 h-full min-h-10 w-px bg-[#26272c]" />
              ) : null}
            </div>
            <div className="flex-1 rounded-md border border-[#26272c] bg-[#111214] px-3 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-sm font-semibold text-white">{item.title}</h3>
                <span className="rounded-md border border-[#26272c] bg-[#141518] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-zinc-400">
                  {item.time}
                </span>
              </div>
              <p className="mt-2 text-sm leading-5 text-zinc-300">{item.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DashboardPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const {
    selectedCampaignId,
    setSelectedCampaignId,
    reloadLocations,
  } = useLocationContext();
  const [loading, setLoading] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignName, setCampaignName] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [crawlType, setCrawlType] = useState("deep");
  const [clusterName, setClusterName] = useState("Core Terms");
  const [keyword, setKeyword] = useState("local seo agency");
  const [monthNumber, setMonthNumber] = useState("1");
  const [recipientEmail, setRecipientEmail] = useState("admin@local.dev");
  const [showWizard, setShowWizard] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [latestRuns, setLatestRuns] = useState<CrawlRun[]>([]);
  const [latestTrends, setLatestTrends] = useState<RankTrend[]>([]);
  const [latestRankTruth, setLatestRankTruth] = useState<RuntimeTruth | null>(null);
  const [latestRankCapturedAt, setLatestRankCapturedAt] = useState("");
  const [trackedKeywordCount, setTrackedKeywordCount] = useState(0);
  const [latestReports, setLatestReports] = useState<Report[]>([]);
  const [latestReportTruth, setLatestReportTruth] = useState<RuntimeTruth | null>(null);
  const [searchConsoleMetrics, setSearchConsoleMetrics] =
    useState<SearchConsoleMetrics | null>(null);
  const latestLoadRequestRef = useRef(0);
  const activeCampaignRef = useRef(selectedCampaignId);
  activeCampaignRef.current = selectedCampaignId;

  async function api(path: string, options: RequestInit = {}) {
    try {
      return await platformApi(path, options);
    } catch (err) {
      if (err instanceof Error && /Session expired|No active session|No token found/i.test(err.message)) {
        clearAuthSession();
        router.push("/login");
      } else if (err instanceof Error && err.name === "AbortError") {
        throw new Error("Request timed out. Please try again.");
      }
      throw err;
    }
  }

  async function loadCampaigns() {
    const data = await api("/campaigns");
    const items = (data?.items || []) as Campaign[];
    setCampaigns(items);

    if (!selectedCampaignId && items.length > 0) {
      setSelectedCampaignId(items[0].id);
      setSeedUrl(withScheme(items[0].domain || ""));
    }

    return items;
  }

  function clearLatestData() {
    setLatestRuns([]);
    setLatestTrends([]);
    setLatestRankTruth(null);
    setLatestRankCapturedAt("");
    setTrackedKeywordCount(0);
    setLatestReports([]);
    setLatestReportTruth(null);
    setSearchConsoleMetrics(null);
  }

  async function loadLatest(
    campaignId: string,
    organizationId = me?.organization_id || "",
  ) {
    if (!campaignId) {
      return false;
    }

    const requestSequence = latestLoadRequestRef.current + 1;
    latestLoadRequestRef.current = requestSequence;
    const [runsData, trendsData, reportsData, searchConsoleData] = await Promise.all([
      api(`/crawl/runs?campaign_id=${encodeURIComponent(campaignId)}`),
      api(`/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`),
      api(`/reports?campaign_id=${encodeURIComponent(campaignId)}`),
      organizationId
        ? api(
            `/organizations/${encodeURIComponent(organizationId)}/data-connections/` +
              `google-search-console/metrics/${encodeURIComponent(campaignId)}?days=28`,
          )
        : Promise.resolve(null),
    ]);

    if (
      !isDashboardDataCurrent(
        campaignId,
        activeCampaignRef.current,
        requestSequence,
        latestLoadRequestRef.current,
      )
    ) {
      return false;
    }

    setLatestRuns((runsData?.items || []) as CrawlRun[]);
    const normalizedTrends = (trendsData || {}) as RankTrendResponse;
    setLatestTrends((normalizedTrends?.items || []) as RankTrend[]);
    setLatestRankTruth((normalizedTrends?.truth as RuntimeTruth) || null);
    setLatestRankCapturedAt(normalizedTrends?.latest_captured_at || "");
    setTrackedKeywordCount(Number(normalizedTrends?.tracked_keywords || 0));
    setLatestReports((reportsData?.items || []) as Report[]);
    setLatestReportTruth((reportsData?.truth as RuntimeTruth) || null);
    setSearchConsoleMetrics((searchConsoleData as SearchConsoleMetrics | null) || null);
    return true;
  }

  async function runAction(label: string, fn: () => Promise<void>) {
    setBusyAction(label);
    setError("");
    setNotice("");

    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyAction("");
    }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignName.trim() || !campaignDomain.trim()) {
      setError("Campaign name and domain are required.");
      return;
    }

    await runAction("createCampaign", async () => {
      const created = await api("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          name: campaignName.trim(),
          domain: campaignDomain.trim(),
        }),
      });

      await loadCampaigns();
      await reloadLocations();
      setSelectedCampaignId(created.id);
      setSeedUrl(withScheme(created.domain || ""));
      setCampaignName("");
      setCampaignDomain("");
      setNotice("Campaign created.");
    });
  }

  async function scheduleCrawl() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }

    await runAction("crawl", async () => {
      const chosenCampaign = campaigns.find((item) => item.id === selectedCampaignId);
      const effectiveSeedUrl = seedUrl.trim() || withScheme(chosenCampaign?.domain || "");

      if (!effectiveSeedUrl) {
        throw new Error("Seed URL is required for crawl.");
      }

      await api("/crawl/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          crawl_type: crawlType,
          seed_url: effectiveSeedUrl,
        }),
      });

      setSeedUrl(effectiveSeedUrl);
      setNotice("Website scan requested. Check the workflow status below for queued, complete, or needs-attention updates.");
      await loadLatest(selectedCampaignId);
    });
  }

  async function addKeywordAndRunRank() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }

    if (!keyword.trim()) {
      setError("Keyword is required.");
      return;
    }

    await runAction("rank", async () => {
      await api("/rank/keywords", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          cluster_name: clusterName.trim() || "Core Terms",
          keyword: keyword.trim(),
        }),
      });

      await api("/rank/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
        }),
      });

      setNotice("Search tracking requested. The dashboard will show ranking progress once the first snapshot is available.");
      await loadLatest(selectedCampaignId);
    });
  }

  async function generateReport() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }

    await runAction("report", async () => {
      const parsedMonth = Number.parseInt(monthNumber, 10);
      const safeMonth = Number.isNaN(parsedMonth)
        ? 1
        : Math.min(12, Math.max(1, parsedMonth));

      await api("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          month_number: safeMonth,
        }),
      });

      setNotice(`Report request completed for month ${safeMonth}. Confirm below whether it is ready to review, still processing, or needs attention.`);
      await loadLatest(selectedCampaignId);
    });
  }

  async function deliverLatestReport() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }

    if (!recipientEmail.trim()) {
      setError("Recipient email is required.");
      return;
    }

    if (latestReports.length === 0 || !latestReports[0]?.id) {
      setError("Generate a report first.");
      return;
    }

    await runAction("deliver", async () => {
      await api(`/reports/${latestReports[0].id}/deliver`, {
        method: "POST",
        body: JSON.stringify({ recipient: recipientEmail.trim() }),
      });

      setNotice("Report delivery was requested. Confirm the latest report status on this page before treating it as sent.");
      await loadLatest(selectedCampaignId);
    });
  }

  /* eslint-disable react-hooks/exhaustive-deps */
  // The initial dashboard bootstrap should run once on mount.
  useEffect(() => {
    async function loadDashboard() {
      setLoading(true);
      setError("");

      try {
        const user = (await api("/auth/me", { method: "GET" })) as Me;
        setMe(user);
        await loadCampaigns();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Session invalid");
      } finally {
        setLoading(false);
      }
    }

    void loadDashboard();
  }, []);
  /* eslint-enable react-hooks/exhaustive-deps */

  useEffect(() => {
    const selected = campaigns.find((item) => item.id === selectedCampaignId);
    if (selected) {
      setSeedUrl(withScheme(selected.domain || ""));
    }
  }, [campaigns, selectedCampaignId]);

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    const organizationId = me?.organization_id || "";
    if (!selectedCampaignId || !organizationId) {
      if (!selectedCampaignId) {
        latestLoadRequestRef.current += 1;
        clearLatestData();
      }
      return;
    }

    const campaignId = selectedCampaignId;
    clearLatestData();
    setLoading(true);
    setError("");

    void loadLatest(campaignId, organizationId)
      .catch((err) => {
        if (activeCampaignRef.current === campaignId) {
          setError(err instanceof Error ? err.message : "Unable to load this location.");
        }
      })
      .finally(() => {
        if (activeCampaignRef.current === campaignId) {
          setLoading(false);
        }
      });

    return () => {
      latestLoadRequestRef.current += 1;
    };
  }, [me?.organization_id, selectedCampaignId]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Search data",
        latestRankTruth,
        "Ranking rows can be synthetic, stale, or unavailable depending on provider setup.",
      ),
      {
        label: "Freshness",
        value: latestRuns[0]?.updated_at
          ? `Updated ${formatRelativeTime(latestRuns[0].updated_at)}`
          : "Awaiting crawl data",
        tone: latestRuns.length > 0 ? "info" : "warning",
      },
      {
        label: "Campaigns",
        value: `${campaigns.length} configured`,
        tone: campaigns.length > 0 ? "success" : "warning",
      },
      {
        label: "Crawl sync",
        value: latestRuns[0]?.status ? toTitleCase(latestRuns[0].status) : "Not started",
        tone: latestRuns[0]?.status === "completed" ? "success" : "warning",
      },
      buildRuntimeTruthSignal(
        "Report status",
        latestReportTruth,
        "A stored report record is not the same as durable or verified delivery.",
      ),
      {
        label: "Search tracking",
        value:
          trackedKeywordCount > 0
            ? `${trackedKeywordCount} configured / ${latestTrends.length} with rows`
            : "No tracked keywords yet",
        tone:
          latestRankTruth?.classification === "unavailable"
            ? "danger"
            : trackedKeywordCount > 0
              ? "info"
              : "warning",
      },
      {
        label: "Google Search Console",
        value:
          searchConsoleMetrics?.data_status === "ready"
            ? `Through ${formatMetricDate(searchConsoleMetrics.date_to)}`
            : searchConsoleMetrics?.data_status === "not_connected"
              ? "Not connected"
              : "Awaiting Google data",
        tone:
          searchConsoleMetrics?.data_status === "ready"
            ? "success"
            : searchConsoleMetrics?.connection?.status === "failed"
              ? "danger"
              : "warning",
      },
    ],
    [
      campaigns.length,
      latestRankTruth,
      latestReportTruth,
      latestRuns,
      latestTrends.length,
      searchConsoleMetrics,
      trackedKeywordCount,
    ],
  );

  const searchConsoleTrend = useMemo(
    () =>
      (searchConsoleMetrics?.points || []).map((point) => ({
        label: formatMetricDate(point.date),
        clicks: Number(point.clicks || 0),
        impressions: Number(point.impressions || 0),
        avgPosition:
          point.avg_position === null || point.avg_position === undefined
            ? null
            : Number(point.avg_position),
      })),
    [searchConsoleMetrics],
  );

  const recentActivity = useMemo(
    () => [
      latestRuns[0]
        ? {
            title: `Crawl ${toTitleCase(latestRuns[0].status)}`,
            time: formatRelativeTime(latestRuns[0].updated_at || latestRuns[0].created_at),
            detail: `Latest ${latestRuns[0].crawl_type || "crawl"} run is ${latestRuns[0].status || "pending"} for ${selectedCampaign?.name || "the active campaign"}.`,
          }
        : null,
      latestTrends[0]
        ? {
            title: "Ranking snapshot updated",
            time: formatRelativeTime(latestRankCapturedAt || latestTrends[0].updated_at || latestTrends[0].created_at),
            detail:
              latestRankTruth?.classification === "synthetic" || latestRankTruth?.classification === "unavailable"
                ? getRuntimeTruthSummary(latestRankTruth, "Ranking runtime is not currently trustworthy.")
                : `${latestTrends[0].keyword || "Top keyword"} is currently at position ${coerceNumber(latestTrends[0].position, 0)}.`,
          }
        : null,
      latestReports[0]
        ? {
            title: "Report lifecycle",
            time: formatRelativeTime(latestReports[0].updated_at || latestReports[0].created_at),
            detail: `Month ${latestReports[0].month_number || "current"} report is ${toTitleCase(latestReports[0].report_status)}.`,
          }
        : null,
      selectedCampaign
        ? {
            title: "Campaign selected",
            time: "Now",
            detail: `${selectedCampaign.name || "Unnamed campaign"} on ${selectedCampaign.domain || "no domain"} is the active workspace.`,
          }
        : null,
    ].filter(Boolean) as Array<{ title: string; time: string; detail: string }>,
    [latestRankCapturedAt, latestRankTruth, latestReports, latestRuns, latestTrends, selectedCampaign],
  );

  const topKeyword = latestTrends[0];
  const topReport = latestReports[0];
  const topRun = latestRuns[0];
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const latestKeywordPosition = topKeyword?.position
    ? coerceNumber(topKeyword.position)
    : null;
  const workflowStates = useMemo(
    () => [
      getSetupWorkflowState(selectedCampaign, topRun),
      getCrawlWorkflowState(topRun, selectedCampaign, formatRelativeTime),
      getRankingWorkflowState(selectedCampaign, latestTrends, topKeyword, latestRankTruth),
      getReportWorkflowState(topReport, selectedCampaign, latestReportTruth),
    ],
    [latestRankTruth, latestReportTruth, latestTrends, selectedCampaign, topKeyword, topReport, topRun],
  );

  const summaryState = (() => {
    if (!selectedCampaign) {
      return {
        changeTitle: "No business is active yet",
        changeBody: "Start by adding your business so InsightOS can scan your website and begin tracking visibility.",
        impactTitle: "Why it matters",
        impactBody: "Until your business is set up, the dashboard cannot show ranking changes, reports, or recommended actions.",
        nextStepTitle: "Set up your business",
        nextStepBody: "Complete the guided setup to run your first check and unlock your first visibility summary.",
        primaryActionLabel: "Set up your business",
        primaryAction: () => setShowWizard(true),
        secondaryActionLabel: "Add business manually",
        secondaryAction: () => document.getElementById("campaign-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (!topRun) {
      return {
        changeTitle: "Your business is ready for its first website scan",
        changeBody: `${selectedCampaign.name || "This business"} has been added, but no website scan has been run yet.`,
        impactTitle: "Why it matters",
        impactBody: "The first scan finds technical issues and creates the baseline for visibility and reporting.",
        nextStepTitle: "Run your first website scan",
        nextStepBody: "Start with a website scan so the dashboard can explain what changed and what needs attention.",
        primaryActionLabel: "Run website scan",
        primaryAction: () => void scheduleCrawl(),
        secondaryActionLabel: "Review business details",
        secondaryAction: () => document.getElementById("campaign-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (isFailedStatus(topRun.status)) {
      return {
        changeTitle: "Latest website scan needs attention",
        changeBody: `The most recent ${topRun.crawl_type || "website"} scan ended as ${toTitleCase(topRun.status)} for ${selectedCampaign.name || "this business"}.`,
        impactTitle: "Why it matters",
        impactBody: "Until the scan succeeds, the dashboard may be missing technical issues and other follow-up guidance.",
        nextStepTitle: "Retry the website scan",
        nextStepBody: "Run the scan again from the manual tools below, then confirm the status changes to completed.",
        primaryActionLabel: "Retry website scan",
        primaryAction: () => void scheduleCrawl(),
        secondaryActionLabel: "Open scan tools",
        secondaryAction: () => document.getElementById("campaign-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (isPendingStatus(topRun.status)) {
      return {
        changeTitle: `Latest website scan is ${toTitleCase(topRun.status)}`,
        changeBody: `The most recent ${topRun.crawl_type || "website"} scan is still processing for ${selectedCampaign.name || "this business"}.`,
        impactTitle: "Why it matters",
        impactBody: "The newest technical findings and visibility summary may still be incomplete until this scan finishes.",
        nextStepTitle: "Wait for the scan to finish",
        nextStepBody: "Refresh the dashboard after a moment to confirm whether the scan completed or needs attention.",
        primaryActionLabel: "Refresh latest results",
        primaryAction: () =>
          void runAction("refresh", async () => {
            await loadLatest(selectedCampaignId);
            setNotice("Latest results refreshed.");
          }),
        secondaryActionLabel: "Review activity",
        secondaryAction: () => document.getElementById("activity-timeline")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (!topKeyword || latestKeywordPosition === null) {
      return {
        changeTitle: `Latest website scan is ${toTitleCase(topRun.status)}`,
        changeBody: `The most recent ${topRun.crawl_type || "website"} scan was updated ${formatRelativeTime(topRun.updated_at || topRun.created_at)}.`,
        impactTitle: "Why it matters",
        impactBody: "You need tracked searches to see whether customers can actually find your business in results.",
        nextStepTitle: "Track your first search term",
        nextStepBody: "Add a search term so the dashboard can start showing ranking movement and visibility trends.",
        primaryActionLabel: "Check search positions",
        primaryAction: () => void addKeywordAndRunRank(),
        secondaryActionLabel: "Open search setup",
        secondaryAction: () => document.getElementById("rank-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (!topReport) {
      return {
        changeTitle: `"${topKeyword.keyword || "Top search term"}" is now tracked at position ${latestKeywordPosition}`,
        changeBody: `Ranking data is flowing for ${selectedCampaign.name || "your business"}, but no report has been created yet.`,
        impactTitle: "Why it matters",
        impactBody: latestKeywordPosition <= 10
          ? "You are already visible on page one for at least one tracked search, which is worth packaging into a client-ready summary."
          : "This gives you a baseline to measure progress against in future checks and reports.",
        nextStepTitle: "Create your first report",
        nextStepBody: "Generate a report so you can package the latest scan and ranking results in one place.",
        primaryActionLabel: "Create report",
        primaryAction: () => void generateReport(),
        secondaryActionLabel: "Open reports controls",
        secondaryAction: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (isFailedStatus(topReport.report_status)) {
      return {
        changeTitle: "Latest report needs attention",
        changeBody: `Month ${topReport.month_number || "current"} report is ${toTitleCase(topReport.report_status)}.`,
        impactTitle: "Why it matters",
        impactBody: "Until the report is recreated successfully, you do not have a current summary ready to review or share.",
        nextStepTitle: "Recreate the latest report",
        nextStepBody: "Open report controls below and run the report again after confirming your latest checks are complete.",
        primaryActionLabel: "Create report",
        primaryAction: () => void generateReport(),
        secondaryActionLabel: "Open report controls",
        secondaryAction: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (isPendingStatus(topReport.report_status)) {
      return {
        changeTitle: `Latest report is ${toTitleCase(topReport.report_status)}`,
        changeBody: `Month ${topReport.month_number || "current"} report is still being prepared.`,
        impactTitle: "Why it matters",
        impactBody: "Until report generation finishes, the latest summary is not ready to review or send.",
        nextStepTitle: "Wait for the report to finish",
        nextStepBody: "Refresh the latest results shortly, then confirm whether the report is ready or needs attention.",
        primaryActionLabel: "Refresh latest results",
        primaryAction: () =>
          void runAction("refresh", async () => {
            await loadLatest(selectedCampaignId);
            setNotice("Latest results refreshed.");
          }),
        secondaryActionLabel: "Open report controls",
        secondaryAction: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
      };
    }

    if (topReport.report_status === "delivered" && Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("delivery_unverified")) {
      return {
        changeTitle: "Latest report delivery is not externally verified",
        changeBody: `Month ${topReport.month_number || "current"} is marked delivered, but this runtime does not verify real inbox delivery.`,
        impactTitle: "Why it matters",
        impactBody: "A delivered record alone is not strong enough to claim the latest update actually reached the recipient.",
        nextStepTitle: "Confirm delivery outside the product",
        nextStepBody: "Use the Reports page and external confirmation before treating this as a completed client send.",
        primaryActionLabel: "Open reports",
        primaryAction: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
        secondaryActionLabel: "Refresh latest results",
        secondaryAction: () =>
          void runAction("refresh", async () => {
            await loadLatest(selectedCampaignId);
            setNotice("Latest results refreshed.");
          }),
      };
    }

    return {
      changeTitle: `"${topKeyword.keyword || "Top search term"}" is at position ${latestKeywordPosition}`,
      changeBody: `Your latest report is ${toTitleCase(topReport.report_status)} and the most recent website scan is ${toTitleCase(topRun.status)}.`,
      impactTitle: "Why it matters",
      impactBody: latestKeywordPosition <= 10
        ? "You already have visible traction. The priority now is staying consistent and sharing progress clearly."
        : "Your tracked visibility is established, so the next gains come from consistent checks and targeted follow-up.",
      nextStepTitle: "Keep the latest update moving",
      nextStepBody: topReport.report_status === "generated"
        ? Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("minimal_artifact")
          ? "Review the local report artifact before sending it. Generated does not mean premium or durable."
          : "Send the latest report so the current progress is shared while it is still fresh."
        : "Refresh your website and ranking checks so the next summary reflects the newest changes.",
      primaryActionLabel: topReport.report_status === "generated" ? "Send latest report" : "Refresh latest results",
      primaryAction: topReport.report_status === "generated"
        ? () => void deliverLatestReport()
        : () =>
            void runAction("refresh", async () => {
              await loadLatest(selectedCampaignId);
              setNotice("Latest results refreshed.");
            }),
      secondaryActionLabel: topReport.report_status === "generated" ? "Open report controls" : "Review activity",
      secondaryAction: topReport.report_status === "generated"
        ? () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" })
        : () => document.getElementById("activity-timeline")?.scrollIntoView({ behavior: "smooth" }),
    };
  })();

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed campaign"} / ${selectedCampaign.domain || "No domain"}`
          : "No campaign selected"
      }
      dateRangeLabel="Live API data"
      topBarActions={
        <>
          <button
            onClick={() =>
              runAction("refresh", async () => {
                await loadLatest(selectedCampaignId);
                setNotice("Latest saved results reloaded.");
              })
            }
            disabled={busyAction !== "" || !selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busyAction === "refresh" ? "Reloading..." : "Reload latest results"}
          </button>
          <div className="flex h-9 min-w-9 items-center justify-center border border-accent-500/20 bg-accent-500/10 px-3 text-sm font-semibold text-zinc-100">
            {me?.tenant_id ? "TA" : "LS"}
          </div>
        </>
      }
    >
      <section className="space-y-6">
        <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="max-w-4xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Daily briefing
            </p>
            <h1 className="mt-2 text-4xl font-bold tracking-[-0.05em] text-white md:text-[3.25rem]">
              What changed for your business today
            </h1>
            <p className="mt-2.5 text-sm leading-6 text-zinc-300 md:text-base">
              Start here to see the latest visibility update, why it matters, and the
              next action InsightOS recommends.
            </p>
          </div>

          <ActionDrawer
            title={summaryState.nextStepTitle}
            summary={summaryState.nextStepBody}
            evidence={[
              summaryState.changeTitle,
              summaryState.impactBody,
              selectedCampaign
                ? `Active business: ${selectedCampaign.name || "Unnamed campaign"} on ${selectedCampaign.domain || "no domain"}.`
                : "No active business is selected yet.",
            ]}
            actions={
              <>
                <button
                  onClick={summaryState.primaryAction}
                  disabled={busyAction !== "" && summaryState.primaryActionLabel !== "Refresh latest results"}
                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {summaryState.primaryActionLabel}
                </button>
                <button
                  onClick={summaryState.secondaryAction}
                  className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200"
                >
                  {summaryState.secondaryActionLabel}
                </button>
              </>
            }
          />
        </div>

        {loading ? (
          <LoadingCard
            title="Loading dashboard"
            summary="Pulling the latest visibility summary, recommended action, and activity for your active business."
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

        {!loading && campaigns.length === 0 && !showWizard ? (
          <EmptyState
            title="Welcome to InsightOS"
            summary="Let's get your business set up so we can start tracking your online visibility."
            actionLabel="Set up your business"
            onAction={() => setShowWizard(true)}
          />
        ) : null}

        {showWizard ? (
          <OnboardingWizard
            onComplete={({ campaignId, campaignDomain, notice: completionNotice }) => {
              setShowWizard(false);
              setSelectedCampaignId(campaignId);
              setSeedUrl(withScheme(campaignDomain));
              setNotice(completionNotice);
              void loadCampaigns().then((items) => {
                const matchedCampaign = items.find((item) => item.id === campaignId);
                if (matchedCampaign) {
                  setSelectedCampaignId(matchedCampaign.id);
                  setSeedUrl(withScheme(matchedCampaign.domain || campaignDomain));
                }
              });
            }}
          />
        ) : null}

        {selectedCampaign ? (
          <SearchPerformanceOverview
            campaign={selectedCampaign}
            metrics={searchConsoleMetrics}
            trend={searchConsoleTrend}
            onOpenSettings={() => router.push("/settings")}
          />
        ) : null}

        {campaigns.length > 0 ? (
          <div className="grid gap-4 xl:grid-cols-3">
            <BriefingCard
              eyebrow="What changed"
              title={summaryState.changeTitle}
              body={summaryState.changeBody}
            />
            <BriefingCard
              eyebrow="Why it matters"
              title={summaryState.impactTitle}
              body={summaryState.impactBody}
            />
            <BriefingCard
              eyebrow="What to do next"
              title={summaryState.nextStepTitle}
              body={summaryState.nextStepBody}
            />
          </div>
        ) : null}

        <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
          <SectionHeading
            eyebrow="Workflow status"
            title="Exactly where things stand"
            summary="These cards translate system activity into user meaning: what is complete, what is still running, what needs attention, and what to do next."
          />
          <div className="grid gap-4 xl:grid-cols-4">
            {workflowStates.map((state) => (
              <div
                key={state.label}
                className="rounded-md border border-[#26272c] bg-[#111214] p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      {state.label}
                    </p>
                    <h3 className="mt-2 text-base font-semibold text-white">{state.status}</h3>
                  </div>
                  <span
                    className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${getWorkflowToneClass(
                      state.tone,
                    )}`}
                  >
                    {state.status}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-zinc-300">{state.detail}</p>
                <p className="mt-3 text-sm font-medium text-zinc-100">Next: {state.nextStep}</p>
              </div>
            ))}
          </div>
        </section>

        <details className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
          <summary className="cursor-pointer list-none">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Advanced controls
                </p>
                <h2 className="mt-1.5 text-lg font-semibold tracking-[-0.03em] text-white">
                  Manual setup and refresh tools
                </h2>
                <p className="mt-1.5 text-sm leading-5 text-zinc-300">
                  Use these when you need to retry setup, refresh results, or manually kick off a check. They are secondary to the daily briefing and workflow status above.
                </p>
              </div>
              <span className="rounded-md border border-[#26272c] bg-[#111214] px-3 py-1 text-sm text-zinc-300">
                Expand
              </span>
            </div>
          </summary>

          <div className="mt-5">
            <SectionHeading
              eyebrow="Manual tools"
              title="Run checks and reports"
              summary="Use these tools when you want to manually trigger a website scan, add tracked searches, or create a report."
            />

            <div className="grid gap-4 xl:grid-cols-2">
              <form
                id="campaign-form"
                onSubmit={createCampaign}
                className="rounded-md border border-[#26272c] bg-[#111214] p-4"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Your business
                </p>
                <div className="mt-4 space-y-3">
                  <input
                    value={campaignName}
                    onChange={(event) => setCampaignName(event.target.value)}
                    placeholder="Business name"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <input
                    value={campaignDomain}
                    onChange={(event) => setCampaignDomain(event.target.value)}
                    placeholder="Your website (example.com)"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <button
                    type="submit"
                    disabled={busyAction !== ""}
                    className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "createCampaign" ? "Adding..." : "Add your business"}
                  </button>
                </div>
                <div className="mt-5">
                  <label className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                    Active business
                  </label>
                  <select
                    value={selectedCampaignId}
                    onChange={(event) => {
                      const nextId = event.target.value;
                      setSelectedCampaignId(nextId);
                      const selected = campaigns.find((item) => item.id === nextId);
                      setSeedUrl(withScheme(selected?.domain || ""));
                    }}
                    className="mt-2 w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                  >
                    <option value="">Select campaign</option>
                    {campaigns.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} ({item.domain})
                      </option>
                    ))}
                  </select>
                </div>
              </form>

              <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Website scan
                </p>
                <div className="mt-4 space-y-3">
                  <input
                    value={seedUrl}
                    onChange={(event) => setSeedUrl(event.target.value)}
                    placeholder="Your website URL"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <button
                    onClick={scheduleCrawl}
                    disabled={busyAction !== ""}
                    className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "crawl" ? "Scanning..." : "Run website scan"}
                  </button>
                </div>
              </div>

              <div id="rank-form" className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Search position check
                </p>
                <div className="mt-4 space-y-3">
                  <input
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                    placeholder="What customers search for (e.g. plumber near me)"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <button
                    onClick={addKeywordAndRunRank}
                    disabled={busyAction !== ""}
                    className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "rank" ? "Checking..." : "Check search positions"}
                  </button>
                </div>
              </div>

              <div id="report-form" className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Reports
                </p>
                <div className="mt-4 space-y-3">
                  <input
                    type="number"
                    min="1"
                    max="12"
                    value={monthNumber}
                    onChange={(event) => setMonthNumber(event.target.value)}
                    placeholder="1"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <input
                    value={recipientEmail}
                    onChange={(event) => setRecipientEmail(event.target.value)}
                    placeholder="Email address to send report"
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={generateReport}
                      disabled={busyAction !== ""}
                      className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "report" ? "Creating..." : "Create report"}
                    </button>
                    <button
                      onClick={deliverLatestReport}
                      disabled={busyAction !== ""}
                      className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "deliver" ? "Sending..." : "Send to email"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </details>

        <div id="activity-timeline">
          <SectionHeading
            eyebrow="Activity"
            title="What the system updated most recently"
            summary="This timeline keeps the active business summary grounded in real scans, rankings, and reporting events."
          />
          <TimelineCard recentActivity={recentActivity} />
        </div>

      </section>
    </AppShell>
  );
}
