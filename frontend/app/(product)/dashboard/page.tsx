"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
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
  OnboardingWizard,
  type NavItem,
  type TrustSignal,
} from "../components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", active: true },
  { href: "/locations", label: "Locations", disabled: true, hidden: true },
  { href: "/rankings", label: "Rankings", disabled: true },
  { href: "/local-visibility", label: "Local Visibility", disabled: true, hidden: true },
  { href: "/site-health", label: "Site Health", badge: "3", disabled: true, hidden: true },
  { href: "/competitors", label: "Competitors", disabled: true, hidden: true },
  { href: "/opportunities", label: "Opportunities", badge: "5", disabled: true },
  { href: "/reports", label: "Reports", disabled: true },
  { href: "/settings", label: "Settings", disabled: true },
];

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

type Report = {
  id?: string;
  month_number?: number | string;
  report_status?: string;
  created_at?: string;
  updated_at?: string;
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
  const [latestReports, setLatestReports] = useState<Report[]>([]);

  async function api(path: string, options: RequestInit = {}) {
    async function runRequest(token: string) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);

      try {
        return await fetch(`${API_BASE}${path}`, {
          ...options,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...(options.headers || {}),
          },
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error("Request timed out. Please try again.");
        }

        throw err;
      } finally {
        clearTimeout(timeout);
      }
    }

    let token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      throw new Error("No token found. Login first.");
    }

    let response = await runRequest(token);

    if (response.status === 401) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_id");
        router.push("/login");
        throw new Error("Session expired. Please log in again.");
      }

      const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      const refreshJson = await refreshResponse.json().catch(() => ({}));

      if (!refreshResponse.ok || !refreshJson?.data?.access_token) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_id");
        router.push("/login");
        throw new Error("Session expired. Please log in again.");
      }

      localStorage.setItem("access_token", refreshJson.data.access_token);
      token = refreshJson.data.access_token;
      response = await runRequest(token);
    }

    let json: any = {};
    try {
      json = await response.json();
    } catch {
      json = {};
    }

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_id");
        router.push("/login");
      }

      throw new Error(json?.error?.message || `Request failed (${response.status})`);
    }

    return json.data;
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
    setLatestTrends((trendsData?.items || []) as RankTrend[]);
    setLatestReports((reportsData?.items || []) as Report[]);
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
      setNotice("Crawl scheduled.");
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

      setNotice("Rank snapshot scheduled.");
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

      setNotice(`Report generated for month ${safeMonth}.`);
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

      setNotice("Latest report marked as delivered.");
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
      {
        label: "Rank sync",
        value: latestTrends.length > 0 ? `${latestTrends.length} keywords tracked` : "No keywords yet",
        tone: latestTrends.length > 0 ? "success" : "warning",
      },
    ],
    [campaigns.length, latestRuns, latestTrends.length],
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
            time: formatRelativeTime(latestTrends[0].updated_at || latestTrends[0].created_at),
            detail: `${latestTrends[0].keyword || "Top keyword"} is currently at position ${coerceNumber(latestTrends[0].position, 0)}.`,
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
    [latestReports, latestRuns, latestTrends, selectedCampaign],
  );

  const topKeyword = latestTrends[0];
  const topReport = latestReports[0];
  const topRun = latestRuns[0];

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
        <div className="max-w-4xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Dashboard
          </p>
          <h1 className="mt-2 text-4xl font-bold tracking-[-0.05em] text-white md:text-[3.25rem]">
            Your Local Search Dashboard
          </h1>
          <p className="mt-2.5 text-sm leading-6 text-zinc-300 md:text-base">
            See how customers find your business online, what changed, and what to do next.
          </p>
        </div>

        {loading ? (
          <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 text-sm text-zinc-300 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
            Loading your latest results...
          </section>
        ) : null}

        {error ? (
          <section className="border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}

        {notice ? (
          <section className="border border-accent-500/20 bg-accent-500/10 p-4 text-sm text-zinc-100">
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
            onComplete={() => {
              setShowWizard(false);
              void loadCampaigns().then((items) => {
                if (items.length > 0) {
                  void loadLatest(items[0].id);
                }
              });
            }}
          />
        ) : null}

        <div className="grid gap-4 xl:grid-cols-4">
          <KpiCard
            label="Campaigns"
            value={String(campaigns.length)}
            changeLabel={selectedCampaign ? "Active" : "Awaiting setup"}
            summary={
              selectedCampaign
                ? `Current workspace: ${selectedCampaign.name || "Unnamed campaign"} on ${selectedCampaign.domain || "no domain"}.`
                : "Create a campaign to begin crawl, rank, and reporting workflows."
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
            label="Latest Crawl"
            value={topRun?.status ? toTitleCase(topRun.status) : "None"}
            changeLabel={topRun?.crawl_type ? toTitleCase(topRun.crawl_type) : undefined}
            summary={
              topRun
                ? `Most recent crawl was updated ${formatRelativeTime(topRun.updated_at || topRun.created_at)}.`
                : "No crawl runs are available for the selected campaign yet."
            }
            visual={
              <MiniSpark
                bars={[18, 26, 38, 44, 58, 68, topRun ? 84 : 20]}
                color="#FF6A1A"
              />
            }
          />
          <KpiCard
            label="Tracked Keywords"
            value={String(latestTrends.length)}
            changeLabel={
              topKeyword?.position ? `Top pos ${coerceNumber(topKeyword.position)}` : undefined
            }
            summary={
              topKeyword
                ? `${topKeyword.keyword || "Top keyword"} is leading the current trend set.`
                : "No ranking snapshots exist yet for this campaign."
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
                ? `Latest report status is ${toTitleCase(topReport.report_status)}.`
                : "Generate a report when you are ready to package the latest work."
            }
            visual={
              <MiniSpark
                bars={[20, 28, 36, 48, 54, 62, Math.min(90, latestReports.length * 20 || 14)]}
                color="#FF7F3F"
              />
            }
          />
        </div>

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

        <div className="grid gap-5 xl:grid-cols-3">
          <InsightCard
            insight={{
              title: selectedCampaign ? "Your business is set up." : "Business setup required.",
              body: selectedCampaign
                ? `${selectedCampaign.name || "Your business"} is ready for website scans, search position checks, and reports.`
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
                ? `"${topKeyword.keyword || "Your top term"}" is at position ${coerceNumber(topKeyword.position)} in search results.`
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
                ? `Your ${toTitleCase(topReport.report_status)} report for month ${topReport.month_number} is ready to view or send.`
                : "Create a report once you have search position data.",
              tone: topReport ? "success" : "warning",
              action: {
                label: topReport ? "View reports" : "Create report",
                onClick: () => document.getElementById("report-form")?.scrollIntoView({ behavior: "smooth" }),
              },
            }}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
          <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
            <SectionHeading
              eyebrow="Actions"
              title="Run checks and reports"
              summary="Use these tools to scan your website, check search positions, and create reports."
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
          </section>

          <ActionDrawer
            title={
              selectedCampaign
                ? `Recommended next step for ${selectedCampaign.name || "your business"}`
                : "Add your business to get started"
            }
            summary={
              selectedCampaign
                ? "Run a website scan, check your search positions, or create a report."
                : "Add your business details so we can start tracking how customers find you online."
            }
            evidence={[
              topRun
                ? `Website scan: ${toTitleCase(topRun.status)}.`
                : "No website scans have been run yet.",
              topKeyword
                ? `"${topKeyword.keyword || "Top search term"}" is at position ${coerceNumber(topKeyword.position)} in search results.`
                : "No search position data yet.",
              topReport
                ? `Your month ${topReport.month_number} report is ${toTitleCase(topReport.report_status)}.`
                : "No reports created yet.",
            ]}
            actions={
              <>
                <button
                  onClick={scheduleCrawl}
                  disabled={busyAction !== ""}
                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Run website scan
                </button>
                <button
                  onClick={generateReport}
                  disabled={busyAction !== ""}
                  className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Create report
                </button>
              </>
            }
          />
        </div>

        <TimelineCard recentActivity={recentActivity} />

        {me ? (
          <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Tenant context
            </p>
            <p className="mt-2 text-sm leading-5 text-zinc-300">
              Signed in as tenant admin. user_id={me.id || "unknown"} | tenant_id=
              {me.tenant_id || "unknown"}
            </p>
          </section>
        ) : null}
      </section>
    </AppShell>
  );
}
