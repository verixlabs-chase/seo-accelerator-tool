"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
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
  InsightCard,
  KpiCard,
  LoadingCard,
  OnboardingWizard,
  TruthNotice,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { clearAuthSession } from "../../lib/authStorage";
import { platformApi } from "../../platform/api";
import {
  getCrawlWorkflowState,
  getRankingWorkflowState,
  getReportWorkflowState,
  getSetupWorkflowState,
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

function VisibilityTrendChart({
  data,
}: {
  data: Array<{ label: string; visibility: number; baseline: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="visibilityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#FF6A1A" stopOpacity={0.34} />
              <stop offset="95%" stopColor="#FF6A1A" stopOpacity={0.02} />
            </linearGradient>
          </defs>
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
          <Tooltip content={<TrendTooltip />} />
          <Area
            type="monotone"
            dataKey="visibility"
            stroke="#FF6A1A"
            strokeWidth={2.2}
            fill="url(#visibilityFill)"
            name="Visibility"
          />
          <Line
            type="monotone"
            dataKey="baseline"
            stroke="#FF944F"
            strokeWidth={1.75}
            strokeDasharray="4 5"
            dot={false}
            name="Baseline"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function RankingTrendChart({
  data,
}: {
  data: Array<{ label: string; momentum: number; benchmark: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
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
          <Tooltip content={<TrendTooltip />} />
          <Line
            type="monotone"
            dataKey="momentum"
            stroke="#FF6A1A"
            strokeWidth={2.2}
            dot={{ r: 0 }}
            activeDot={{ r: 4, fill: "#FF6A1A", stroke: "#0a0a0a", strokeWidth: 2 }}
            name="Momentum"
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#FF944F"
            strokeWidth={1.75}
            dot={false}
            strokeDasharray="5 6"
            name="Benchmark"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function MiniSpark({
  bars,
  color,
}: {
  bars: number[];
  color: string;
}) {
  return (
    <div className="flex h-16 items-end gap-1">
      {bars.map((bar, index) => (
        <span
          key={`${color}-${index}`}
          className="w-1.5"
          style={{
            height: `${bar}%`,
            background: color,
            opacity: 0.88,
          }}
        />
      ))}
    </div>
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
  const [loading, setLoading] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [crawlType, setCrawlType] = useState("deep");
  const [clusterName, setClusterName] = useState("Core Terms");
  const [keyword, setKeyword] = useState("local seo agency");
  const [locationCode, setLocationCode] = useState("US");
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

  async function loadLatest(campaignId: string) {
    if (!campaignId) {
      return;
    }

    const [runsData, trendsData, reportsData] = await Promise.all([
      api(`/crawl/runs?campaign_id=${encodeURIComponent(campaignId)}`),
      api(`/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`),
      api(`/reports?campaign_id=${encodeURIComponent(campaignId)}`),
    ]);

    setLatestRuns((runsData?.items || []) as CrawlRun[]);
    const normalizedTrends = (trendsData || {}) as RankTrendResponse;
    setLatestTrends((normalizedTrends?.items || []) as RankTrend[]);
    setLatestRankTruth((normalizedTrends?.truth as RuntimeTruth) || null);
    setLatestRankCapturedAt(normalizedTrends?.latest_captured_at || "");
    setTrackedKeywordCount(Number(normalizedTrends?.tracked_keywords || 0));
    setLatestReports((reportsData?.items || []) as Report[]);
    setLatestReportTruth((reportsData?.truth as RuntimeTruth) || null);
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
      setSelectedCampaignId(created.id);
      setSeedUrl(withScheme(created.domain || ""));
      setCampaignName("");
      setCampaignDomain("");
      setNotice("Campaign created.");
      await loadLatest(created.id);
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
          location_code: locationCode.trim() || "US",
        }),
      });

      await api("/rank/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          location_code: locationCode.trim() || "US",
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
        const items = await loadCampaigns();

        if (items.length > 0) {
          await loadLatest(items[0].id);
        }
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
    if (selected && !seedUrl) {
      setSeedUrl(withScheme(selected.domain || ""));
    }
  }, [campaigns, seedUrl, selectedCampaignId]);

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Rank truth",
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
        "Report truth",
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
    ],
    [campaigns.length, latestRankTruth, latestReportTruth, latestRuns, latestTrends.length, trackedKeywordCount],
  );

  const visibilityTrend = useMemo(
    () =>
      latestTrends.slice(0, 7).map((trend, index) => {
        const position = coerceNumber(trend.position, 0);
        const visibility = position > 0 ? Math.max(0, 101 - position) : 0;
        return {
          label: trend.keyword?.slice(0, 10) || `KW ${index + 1}`,
          visibility,
          baseline: Math.max(0, visibility - 8),
        };
      }),
    [latestTrends],
  );

  const rankingTrend = useMemo(
    () =>
      latestTrends.slice(0, 7).map((trend, index) => {
        const position = coerceNumber(trend.position, 100);
        return {
          label: trend.keyword?.slice(0, 10) || `KW ${index + 1}`,
          momentum: Math.max(1, 101 - position),
          benchmark: Math.max(1, 96 - position),
        };
      }),
    [latestTrends],
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
                setNotice("Latest results refreshed.");
              })
            }
            disabled={busyAction !== "" || !selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busyAction === "refresh" ? "Refreshing..." : "Refresh"}
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

        {!loading ? (
          <TruthNotice title="Results fill in over time, and manual tools are fallback controls.">
            The daily briefing and workflow cards are the primary source of truth. A queued scan,
            ranking check, or report request means the work started, not that the final results are
            complete. The advanced controls below are for retrying or manually nudging a workflow,
            not the normal first-value path.
          </TruthNotice>
        ) : null}

        {!loading && latestRankTruth ? (
          <TruthNotice title="Current ranking runtime truth" tone="warning">
            {getRuntimeTruthSummary(
              latestRankTruth,
              "Ranking runtime status is not available yet.",
            )}
          </TruthNotice>
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
                void loadLatest(campaignId);
              });
            }}
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

        <SectionHeading
          eyebrow="At a glance"
          title="Your current visibility summary"
          summary="These cards show the latest state of setup, website scans, tracked searches, and reporting for the active business."
        />
        <div className="grid gap-4 xl:grid-cols-4">
          <KpiCard
            label="Businesses"
            value={String(campaigns.length)}
            changeLabel={selectedCampaign ? "Active now" : "Needs setup"}
            summary={
              selectedCampaign
                ? `Current workspace: ${selectedCampaign.name || "Unnamed campaign"} on ${selectedCampaign.domain || "no domain"}.`
                : "Add your business to start scans, rankings, and reports."
            }
            visual={
              <MiniSpark
                bars={[24, 34, 42, 50, 62, 76, Math.min(96, campaigns.length * 18 || 14)]}
                color="#22c55e"
              />
            }
            tone="highlight"
          />
          <KpiCard
            label="Website scan"
            value={topRun?.status ? toTitleCase(topRun.status) : "None"}
            changeLabel={topRun?.crawl_type ? toTitleCase(topRun.crawl_type) : undefined}
            summary={
              topRun
                ? isFailedStatus(topRun.status)
                  ? `Most recent crawl ended as ${toTitleCase(topRun.status)} and needs attention.`
                  : isPendingStatus(topRun.status)
                    ? `Most recent crawl is ${toTitleCase(topRun.status)}. Results may still be filling in.`
                    : `Most recent crawl completed ${formatRelativeTime(topRun.updated_at || topRun.created_at)}.`
                : "No website scan has run for the active business yet."
            }
            visual={
              <MiniSpark
                bars={[18, 26, 38, 44, 58, 68, topRun ? 84 : 20]}
                color="#FF6A1A"
              />
            }
          />
          <KpiCard
            label="Tracked searches"
            value={String(latestTrends.length)}
            changeLabel={
              topKeyword?.position ? `Best ${coerceNumber(topKeyword.position)}` : undefined
            }
            summary={
              topKeyword
                ? `${topKeyword.keyword || "Top search"} is leading the current trend set.`
                : "No search position snapshots exist yet for this business."
            }
            visual={
              <MiniSpark
                bars={[
                  16,
                  22,
                  31,
                  40,
                  52,
                  66,
                  Math.min(92, latestTrends.length * 9 || 12),
                ]}
                color="#FF944F"
              />
            }
          />
          <KpiCard
            label="Reports"
            value={String(latestReports.length)}
            changeLabel={
              topReport?.month_number ? `Month ${topReport.month_number}` : undefined
            }
            summary={
              topReport
                ? topReport.report_status === "delivered"
                  ? Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("delivery_unverified")
                    ? `Latest report is marked delivered for month ${topReport.month_number || "current"}, but delivery is not externally verified.`
                    : `Latest report was delivered for month ${topReport.month_number || "current"}.`
                  : topReport.report_status === "generated"
                    ? Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("minimal_artifact")
                      ? "Latest report is a minimal local artifact that still needs review before sending."
                      : "Latest report is ready to review and send."
                    : isFailedStatus(topReport.report_status)
                      ? `Latest report needs attention after a ${toTitleCase(topReport.report_status)} result.`
                      : isPendingStatus(topReport.report_status)
                        ? `Latest report is ${toTitleCase(topReport.report_status)} and still being prepared.`
                        : `Latest report status is ${toTitleCase(topReport.report_status)}.`
                : "Create a report once your latest scan and ranking data are ready."
            }
            visual={
              <MiniSpark
                bars={[20, 28, 36, 48, 54, 62, Math.min(90, latestReports.length * 20 || 14)]}
                color="#FF7F3F"
              />
            }
          />
        </div>

        <SectionHeading
          eyebrow="Trends"
          title="How visibility is moving"
          summary="Use these charts to see how often your business appears in search and whether search positions are improving."
        />
        <div className="grid gap-5 xl:grid-cols-2">
          <ChartCard
            eyebrow="Trend"
            title="How often customers find you"
            summary="This shows your online visibility based on where you appear in search results."
            chart={
              visibilityTrend.length > 0 ? (
                <VisibilityTrendChart data={visibilityTrend} />
              ) : (
                <EmptyState
                  title="No visibility data yet"
                  summary="Run a search position check to populate this chart."
                  actionLabel="Check search positions"
                  onAction={() => document.getElementById("rank-form")?.scrollIntoView({ behavior: "smooth" })}
                />
              )
            }
            footer={
              <p className="text-sm leading-5 text-zinc-300">
                Updates automatically when new search position data arrives.
              </p>
            }
          />
          <ChartCard
            eyebrow="Trend"
            title="Search position movement"
            summary="Track whether your search positions are improving over time."
            chart={
              rankingTrend.length > 0 ? (
                <RankingTrendChart data={rankingTrend} />
              ) : (
                <EmptyState
                  title="No ranking history yet"
                  summary="Add a search term and run a position check to see your trends."
                  actionLabel="Add search term"
                  onAction={() => document.getElementById("rank-form")?.scrollIntoView({ behavior: "smooth" })}
                />
              )
            }
            footer={
              <p className="text-sm leading-5 text-zinc-300">
                Shows movement for your tracked search terms over time.
              </p>
            }
          />
        </div>

        <SectionHeading
          eyebrow="Highlights"
          title="The clearest takeaways right now"
          summary="These quick reads explain where the active business stands and where the next useful action lives."
        />
        <div className="grid gap-5 xl:grid-cols-3">
          <InsightCard
            insight={{
              title: selectedCampaign ? "Your business is connected." : "Business setup required.",
              body: selectedCampaign
                ? `${selectedCampaign.name || "Your business"} is ready for scans, tracked searches, and reporting.`
                : "Add your business to start tracking how customers find you online.",
              tone: selectedCampaign ? "success" : "warning",
              action: {
                label: selectedCampaign ? "View business" : "Set up business",
                onClick: () => document.getElementById("campaign-form")?.scrollIntoView({ behavior: "smooth" }),
              },
            }}
          />
          <InsightCard
            insight={{
              title: topKeyword ? "Search positions tracked." : "No search terms tracked yet.",
              body: topKeyword
                ? `"${topKeyword.keyword || "Your top term"}" is currently at position ${coerceNumber(topKeyword.position)} in search results.`
                : "Add a search term to see where your business shows up when customers search.",
              tone: topKeyword ? "info" : "warning",
              action: {
                label: topKeyword ? "View positions" : "Add search term",
                onClick: () => document.getElementById("rank-form")?.scrollIntoView({ behavior: "smooth" }),
              },
            }}
          />
          <InsightCard
            insight={{
              title: topReport ? "Reports available." : "No reports yet.",
              body: topReport
                ? topReport.report_status === "delivered"
                  ? Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("delivery_unverified")
                    ? `Your month ${topReport.month_number} report is marked delivered, but the current runtime does not verify inbox delivery.`
                    : `Your month ${topReport.month_number} report has already been sent and is the latest shared update.`
                  : topReport.report_status === "generated"
                    ? Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("minimal_artifact")
                      ? `Your month ${topReport.month_number} report is a minimal local artifact that still needs review before any send.`
                      : `Your month ${topReport.month_number} report is ready to review and send.`
                    : isFailedStatus(topReport.report_status)
                      ? "Your latest report needs attention before it can be treated as ready to share."
                      : `Your latest report is ${toTitleCase(topReport.report_status)} and still in progress.`
                : "Create a report once you have search position data.",
              tone: topReport
                ? topReport.report_status === "delivered"
                  ? "success"
                  : "info"
                : "warning",
              action: {
                label: topReport ? "View reports" : "Create report",
                onClick: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
              },
            }}
          />
        </div>

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
                    onChange={async (event) => {
                      const nextId = event.target.value;
                      setSelectedCampaignId(nextId);
                      const selected = campaigns.find((item) => item.id === nextId);
                      setSeedUrl(withScheme(selected?.domain || ""));
                      await runAction("refresh", async () => {
                        await loadLatest(nextId);
                      });
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

        <div className="grid gap-4 xl:grid-cols-[1fr_0.55fr]">
          <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
            <SectionHeading
              eyebrow="Visibility context"
              title="What this workspace is tracking"
              summary="Use this section to confirm the active business and make sure the current results belong to the right website."
            />
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <p className="text-sm leading-6 text-zinc-300">
                {selectedCampaign
                  ? `${selectedCampaign.name || "Unnamed campaign"} on ${selectedCampaign.domain || "no domain"} is the active workspace.`
                  : "No business is active yet."}
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Latest website scan
                  </p>
                  <p className="mt-2 text-sm text-zinc-200">
                    {topRun
                      ? `${toTitleCase(topRun.status)} ${formatRelativeTime(topRun.updated_at || topRun.created_at)}`
                      : "No website scan has run yet."}
                  </p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Latest report
                  </p>
                  <p className="mt-2 text-sm text-zinc-200">
                    {topReport
                      ? topReport.report_status === "delivered" && Array.isArray(latestReportTruth?.states) && latestReportTruth.states.includes("delivery_unverified")
                        ? `Marked delivered for month ${topReport.month_number || "current"}`
                        : `${toTitleCase(topReport.report_status)} for month ${topReport.month_number || "current"}`
                      : "No report has been created yet."}
                  </p>
                </div>
              </div>
            </div>
          </section>
        </div>

        {me ? (
          <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Account context
            </p>
            <p className="mt-2 text-sm leading-5 text-zinc-300">
              Signed in and connected to the active workspace. Advanced account identifiers stay out of the main flow so this page can focus on business status and next steps.
            </p>
          </section>
        ) : null}
      </section>
    </AppShell>
  );
}
