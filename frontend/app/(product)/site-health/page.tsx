"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  ComparisonTable,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
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

type CrawlRun = {
  id: string;
  crawl_type?: string;
  status?: string;
  seed_url?: string;
  pages_discovered?: number;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
};

type TechnicalIssue = {
  id: string;
  crawl_run_id?: string;
  issue_code?: string;
  severity?: string;
  details_json?: string;
  detected_at?: string;
};

type CrawlMetrics = {
  stages?: Record<
    string,
    {
      calls?: number;
      failures?: number;
      p95_ms?: number;
      avg_ms?: number;
      slo_ok?: boolean;
    }
  >;
};

function toTitleCase(value?: string) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatRelativeTime(value?: string | null) {
  if (!value) {
    return "No recent update";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No recent update";
  }

  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const hours = Math.round(diffMs / 3600000);

  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(diffMs / 86400000);
  return formatter.format(days, "day");
}

function issueLabel(issueCode?: string) {
  switch (issueCode) {
    case "http_error":
      return "Broken or inaccessible page";
    case "missing_title":
      return "Missing page title";
    case "missing_meta_description":
      return "Missing meta description";
    case "invalid_canonical":
      return "Invalid canonical tag";
    case "missing_h1":
      return "Missing page heading";
    case "multiple_h1":
      return "Multiple main headings";
    case "non_indexable":
      return "Page blocked from search";
    case "no_internal_links":
      return "No internal links pointing through";
    case "crawl_run_failed":
      return "Website scan failed";
    default:
      return toTitleCase(issueCode);
  }
}

function issueImpact(issueCode?: string) {
  switch (issueCode) {
    case "http_error":
      return "Customers and search engines may not be able to reach the page.";
    case "missing_title":
      return "Search engines have less context about what the page is about.";
    case "missing_meta_description":
      return "Search snippets may be weaker and less likely to attract clicks.";
    case "invalid_canonical":
      return "Search engines may get mixed signals about the correct page version.";
    case "missing_h1":
      return "The page structure is weaker and harder for search engines to interpret.";
    case "multiple_h1":
      return "The page structure is less clear than it should be.";
    case "non_indexable":
      return "The page may be hidden from search results entirely.";
    case "no_internal_links":
      return "The page may be harder for users and search engines to discover.";
    case "crawl_run_failed":
      return "The system could not finish the scan, so issue visibility is incomplete.";
    default:
      return "This issue can reduce how clearly search engines understand the site.";
  }
}

function issueFix(issueCode?: string) {
  switch (issueCode) {
    case "http_error":
      return "Fix broken responses first so important pages load correctly.";
    case "missing_title":
      return "Add a clear page title to every important page.";
    case "missing_meta_description":
      return "Write a short description that explains the page and encourages clicks.";
    case "invalid_canonical":
      return "Correct the canonical tag so it points to a full valid URL.";
    case "missing_h1":
      return "Add one main page heading that matches the page topic.";
    case "multiple_h1":
      return "Reduce the page to one main heading and keep the rest secondary.";
    case "non_indexable":
      return "Remove the block if the page should appear in search.";
    case "no_internal_links":
      return "Add links from related pages so this page is easier to find.";
    case "crawl_run_failed":
      return "Run the scan again and confirm the website can be crawled.";
    default:
      return "Review the page setup and correct the issue before the next scan.";
  }
}

function parseIssueDetails(detailsJson?: string) {
  if (!detailsJson) {
    return {};
  }

  try {
    return JSON.parse(detailsJson) as Record<string, string | number | null>;
  } catch {
    return {};
  }
}

function SiteHealthTooltip({
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
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">
        {label}
      </p>
      <div className="mt-2 space-y-1.5">
        {payload.map((entry) => (
          <div key={entry.name} className="flex min-w-40 items-center gap-2 text-sm text-zinc-200">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span>{entry.name}</span>
            <span className="ml-auto font-semibold text-white">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SiteHealthPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [issues, setIssues] = useState<TechnicalIssue[]>([]);
  const [metrics, setMetrics] = useState<CrawlMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
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
  }, []);

  const loadTechnicalData = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setRuns([]);
      setIssues([]);
      setMetrics(null);
      return;
    }

    const [runsResponse, issuesResponse, metricsResponse] = await Promise.all([
      platformApi(`/crawl/runs?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/crawl/issues?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi("/crawl/metrics", { method: "GET" }),
    ]);

    setRuns(Array.isArray(runsResponse?.items) ? (runsResponse.items as CrawlRun[]) : []);
    setIssues(Array.isArray(issuesResponse?.items) ? (issuesResponse.items as TechnicalIssue[]) : []);
    setMetrics((metricsResponse as CrawlMetrics) || null);
  }, []);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        await platformApi("/auth/me", { method: "GET" });
        const items = await loadCampaigns();
        if (items[0]?.id) {
          await loadTechnicalData(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load website health information.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns, loadTechnicalData]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void loadTechnicalData(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load website health information.");
    });
  }, [selectedCampaignId, loading, loadTechnicalData]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const latestRun = runs[0] ?? null;
  const latestRunIssues = useMemo(
    () => (latestRun ? issues.filter((issue) => issue.crawl_run_id === latestRun.id) : []),
    [issues, latestRun],
  );

  const severityCounts = useMemo(() => {
    return latestRunIssues.reduce(
      (accumulator, issue) => {
        const key = issue.severity || "low";
        accumulator[key] = (accumulator[key] || 0) + 1;
        return accumulator;
      },
      {} as Record<string, number>,
    );
  }, [latestRunIssues]);

  const issueGroups = useMemo(() => {
    const groups = new Map<
      string,
      {
        issueCode: string;
        count: number;
        highestSeverity: string;
        latestDetectedAt?: string;
      }
    >();

    const severityRank: Record<string, number> = { high: 3, medium: 2, low: 1 };

    latestRunIssues.forEach((issue) => {
      const code = issue.issue_code || "unknown_issue";
      const existing = groups.get(code);
      if (!existing) {
        groups.set(code, {
          issueCode: code,
          count: 1,
          highestSeverity: issue.severity || "low",
          latestDetectedAt: issue.detected_at,
        });
        return;
      }

      existing.count += 1;
      if ((severityRank[issue.severity || "low"] || 1) > (severityRank[existing.highestSeverity] || 1)) {
        existing.highestSeverity = issue.severity || "low";
      }
      if ((issue.detected_at || "") > (existing.latestDetectedAt || "")) {
        existing.latestDetectedAt = issue.detected_at;
      }
    });

    return [...groups.values()].sort((left, right) => {
      const severityRank: Record<string, number> = { high: 3, medium: 2, low: 1 };
      const severityDifference =
        (severityRank[right.highestSeverity] || 1) - (severityRank[left.highestSeverity] || 1);
      if (severityDifference !== 0) {
        return severityDifference;
      }
      return right.count - left.count;
    });
  }, [latestRunIssues]);

  const topIssue = issueGroups[0] ?? null;
  const scanLaneHealthy = useMemo(() => {
    const stages = Object.values(metrics?.stages || {});
    if (stages.length === 0) {
      return null;
    }
    return stages.every((stage) => stage.slo_ok !== false);
  }, [metrics]);

  const topSummary = useMemo(() => {
    if (!selectedCampaign) {
      return {
        title: "No business is selected yet",
        body: "Set up a business first so InsightOS can scan the website and find problems.",
        next: "Go back to the dashboard to run the first website scan.",
      };
    }

    if (!latestRun) {
      return {
        title: `${selectedCampaign.name || "This business"} has not been scanned yet`,
        body: "Website health starts with a website scan. No scan has run for this business yet.",
        next: "Run the first website scan, then return here to review what needs fixing first.",
      };
    }

    if (!topIssue) {
      return {
        title: "No website problems are currently flagged",
        body: `The latest ${latestRun.crawl_type || "website"} scan is ${toTitleCase(latestRun.status)} and no issues are currently listed.`,
        next: "Keep scanning regularly so new problems are caught early.",
      };
    }

    return {
      title: `${issueLabel(topIssue.issueCode)} should be fixed first`,
      body: `${topIssue.count} pages are affected, and the highest severity is ${topIssue.highestSeverity}. ${issueImpact(topIssue.issueCode)}`,
      next: issueFix(topIssue.issueCode),
    };
  }, [latestRun, selectedCampaign, topIssue]);

  const priorityChartData = useMemo(
    () => [
      { label: "Fix now", count: severityCounts.high || 0, color: "#f43f5e" },
      { label: "Fix next", count: severityCounts.medium || 0, color: "#f59e0b" },
      { label: "Monitor", count: severityCounts.low || 0, color: "#71717a" },
    ],
    [severityCounts.high, severityCounts.low, severityCounts.medium],
  );

  const issueTypeChartData = useMemo(
    () =>
      issueGroups.slice(0, 6).map((group) => ({
        label:
          issueLabel(group.issueCode).length > 22
            ? `${issueLabel(group.issueCode).slice(0, 22)}…`
            : issueLabel(group.issueCode),
        count: group.count,
        severity: group.highestSeverity,
      })),
    [issueGroups],
  );

  const scanHistoryData = useMemo(() => {
    const issueCounts = issues.reduce((counts, issue) => {
      const runId = issue.crawl_run_id || "";
      if (runId) {
        counts[runId] = (counts[runId] || 0) + 1;
      }
      return counts;
    }, {} as Record<string, number>);

    return [...runs]
      .sort(
        (left, right) =>
          new Date(left.created_at || 0).getTime() -
          new Date(right.created_at || 0).getTime(),
      )
      .slice(-10)
      .map((run) => ({
        label: run.created_at
          ? new Date(run.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })
          : "Scan",
        issues: issueCounts[run.id] || 0,
        pages: run.pages_discovered || 0,
      }));
  }, [issues, runs]);

  const issueTableRows = useMemo(
    () =>
      issueGroups.slice(0, 8).map((group) => ({
        id: group.issueCode,
        values: {
          issue: issueLabel(group.issueCode),
          severity: toTitleCase(group.highestSeverity),
          affected: String(group.count),
          impact: issueImpact(group.issueCode),
          first_fix: issueFix(group.issueCode),
        },
      })),
    [issueGroups],
  );

  const latestIssueRows = useMemo(
    () =>
      latestRunIssues.slice(0, 6).map((issue) => {
        const details = parseIssueDetails(issue.details_json);
        const detailText =
          details.status_code !== undefined
            ? `Status ${details.status_code}`
            : details.canonical
              ? `Canonical: ${details.canonical}`
              : details.h1_count !== undefined
                ? `${details.h1_count} H1 tags`
                : "No extra details";

        return {
          id: issue.id,
          values: {
            issue: issueLabel(issue.issue_code),
            severity: toTitleCase(issue.severity),
            detected: formatRelativeTime(issue.detected_at),
            detail: detailText,
          },
        };
      }),
    [latestRunIssues],
  );

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Latest scan",
        value: latestRun ? toTitleCase(latestRun.status) : "Not started",
        tone: latestRun?.status === "completed" ? "success" : latestRun ? "info" : "warning",
      },
      {
        label: "High severity",
        value: severityCounts.high ? `${severityCounts.high} flagged` : "None flagged",
        tone: (severityCounts.high || 0) > 0 ? "warning" : "success",
      },
      {
        label: "Total issues",
        value: latestRunIssues.length ? `${latestRunIssues.length} found` : "No issues",
        tone: latestRunIssues.length > 0 ? "warning" : "success",
      },
      {
        label: "Scan processing",
        value:
          scanLaneHealthy === null
            ? "No metrics yet"
            : scanLaneHealthy
              ? "Processing normally"
              : "Processing under pressure",
        tone:
          scanLaneHealthy === null
            ? "warning"
            : scanLaneHealthy
              ? "success"
              : "warning",
      },
    ],
    [latestRun, latestRunIssues.length, scanLaneHealthy, severityCounts.high],
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
      dateRangeLabel="Latest website scan"
      topBarActions={
        <>
          <button
            onClick={() => {
              setNotice("Saved site health data reloaded.");
              void loadTechnicalData(selectedCampaignId);
            }}
            disabled={!selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reload saved data
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
          eyebrow="Website health"
          title="Is your website helping or hurting you?"
          summary="See problems that could keep customers or search engines from using your website, which one to fix first, and the next practical step."
        />

        {loading ? (
          <LoadingCard
            title="Checking the latest website results"
            summary="Loading the newest website scan and putting the most important problems first."
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
            title="Set up a business before checking the website"
            summary="Add the business and website first. InsightOS can then find pages that may be broken, unclear, or difficult to find in search."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Recommended action
              </p>
              <div className="mt-3 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <div>
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                    {topSummary.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.body}</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What to do next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.next}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {topIssue ? (
                      <button
                        type="button"
                        onClick={() =>
                          document
                            .getElementById("issue-details")
                            ?.scrollIntoView({ behavior: "smooth" })
                        }
                        className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3 py-2 text-sm font-semibold text-white"
                      >
                        Review affected pages
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => router.push("/dashboard")}
                      className="rounded-md border border-[#303137] bg-[#17181b] px-3 py-2 text-sm font-medium text-zinc-200"
                    >
                      Run another scan
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Fix first"
                value={String(severityCounts.high || 0)}
                summary="These issues are the most likely to block visibility or break important pages."
                tone="highlight"
              />
              <KpiCard
                label="Fix next"
                value={String(severityCounts.medium || 0)}
                summary="These issues weaken search clarity and should be fixed after the critical ones."
              />
              <KpiCard
                label="Smaller improvements"
                value={String(severityCounts.low || 0)}
                summary="These issues are smaller cleanup items, but they still improve site quality."
              />
              <KpiCard
                label="Pages discovered"
                value={String(latestRun?.pages_discovered || 0)}
                summary={
                  latestRun
                    ? `Latest ${latestRun.crawl_type || "website"} scan was ${toTitleCase(latestRun.status)} ${formatRelativeTime(latestRun.finished_at || latestRun.created_at)}.`
                    : "No website scan has run yet."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-2">
              <ChartCard
                eyebrow="Current priorities"
                title="What needs attention first"
                summary="Problems are grouped into a simple order: urgent fixes, important follow-up work, and lower-risk cleanup."
                chart={
                  latestRunIssues.length > 0 ? (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={priorityChartData}>
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
                          <Tooltip content={<SiteHealthTooltip />} />
                          <Bar dataKey="count" name="Problems" radius={[6, 6, 0, 0]}>
                            {priorityChartData.map((entry) => (
                              <Cell key={entry.label} fill={entry.color} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <ChartEmptyState
                      title="No problems are flagged"
                      summary="The latest scan did not return any technical issues. Run scans regularly to catch new problems."
                    />
                  )
                }
                footer={
                  <p className="text-sm text-zinc-400">
                    {(severityCounts.high || 0) > 0
                      ? `${severityCounts.high} problem${severityCounts.high === 1 ? "" : "s"} should be handled before the rest.`
                      : "No urgent website problems are currently flagged."}
                  </p>
                }
              />

              <ChartCard
                eyebrow="Affected pages"
                title="Which problems are most widespread"
                summary="The tallest bars affect the most pages. Severity still determines which problem should be handled first."
                chart={
                  issueTypeChartData.length > 0 ? (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={issueTypeChartData}>
                          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                          <XAxis
                            dataKey="label"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#a1a1aa", fontSize: 11 }}
                            interval={0}
                          />
                          <YAxis
                            allowDecimals={false}
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#71717a", fontSize: 12 }}
                            width={28}
                          />
                          <Tooltip content={<SiteHealthTooltip />} />
                          <Bar dataKey="count" name="Affected pages" radius={[6, 6, 0, 0]}>
                            {issueTypeChartData.map((entry) => (
                              <Cell
                                key={entry.label}
                                fill={
                                  entry.severity === "high"
                                    ? "#f43f5e"
                                    : entry.severity === "medium"
                                      ? "#f59e0b"
                                      : "#71717a"
                                }
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <ChartEmptyState
                      title="No affected pages to compare"
                      summary="Issue types will appear here when a website scan finds something that needs attention."
                    />
                  )
                }
                footer={
                  <p className="text-sm text-zinc-400">
                    {topIssue
                      ? `${issueLabel(topIssue.issueCode)} affects ${topIssue.count} page${topIssue.count === 1 ? "" : "s"} and should be reviewed first.`
                      : "There is no affected-page action to take from the latest scan."}
                  </p>
                }
              />
            </div>

            <ChartCard
              eyebrow="Scan history"
              title="Are website problems increasing or decreasing?"
              summary="This compares stored scans over time. Fewer problems is better, but a scan that covers more pages can uncover additional work."
              chart={
                scanHistoryData.length >= 2 ? (
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={scanHistoryData}>
                        <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                        <XAxis
                          dataKey="label"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#71717a", fontSize: 12 }}
                        />
                        <YAxis
                          allowDecimals={false}
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#71717a", fontSize: 12 }}
                          width={36}
                        />
                        <Tooltip content={<SiteHealthTooltip />} />
                        <Line
                          type="monotone"
                          dataKey="issues"
                          name="Problems found"
                          stroke="#FF6A1A"
                          strokeWidth={3}
                          dot={{ r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <ChartEmptyState
                    title="One scan is not a trend"
                    summary="Run another website scan later to see which problems were fixed, remained, or appeared."
                  />
                )
              }
              footer={
                <p className="text-sm text-zinc-400">
                  Latest coverage: {latestRun?.pages_discovered || 0} pages discovered and{" "}
                  {latestRunIssues.length} problems recorded.
                </p>
              }
            />

            {runs.length === 0 ? (
              <EmptyState
                title="No website scans have run yet"
                summary="Run your first website scan from the dashboard to find broken pages, unclear page information, and other fixes."
                actionLabel="Go to dashboard"
                onAction={() => router.push("/dashboard")}
              />
            ) : (
              <>
                <div id="issue-details">
                  <ComparisonTable
                    title="Issues and recommended fixes"
                    columns={[
                      { key: "issue", label: "What is wrong" },
                      { key: "severity", label: "Priority" },
                      { key: "affected", label: "Pages affected" },
                      { key: "impact", label: "Why it matters" },
                      { key: "first_fix", label: "What to do next" },
                    ]}
                    rows={issueTableRows}
                  />
                </div>

                <details className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-zinc-100">
                    Technical details
                    <span className="text-xs font-normal text-zinc-500">
                      Raw scan evidence · expand to review
                    </span>
                  </summary>
                  <div className="mt-5 border-t border-[#26272c] pt-5">
                    <ComparisonTable
                      title="Most recent issue detections"
                      columns={[
                        { key: "issue", label: "Issue" },
                        { key: "severity", label: "Severity" },
                        { key: "detected", label: "Detected" },
                        { key: "detail", label: "Stored detail" },
                      ]}
                      rows={latestIssueRows}
                    />
                  </div>
                </details>
              </>
            )}
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
