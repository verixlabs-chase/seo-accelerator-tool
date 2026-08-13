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
  ReferenceLine,
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
  OwnerDecisionPanel,
  ProductPageIntro,
  TruthNotice,
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

type VitalMetric = {
  metric_id?: string;
  display_name?: string;
  plain_language?: string;
  value?: number | null;
  unit?: string;
  status?: "good" | "needs_improvement" | "poor" | "insufficient_data";
  thresholds?: {
    good_boundary?: number;
    poor_boundary?: number;
  } | null;
};

type VitalAssessment = {
  assessment?: {
    status?: "good" | "needs_improvement" | "poor" | "insufficient_data";
    passes_core_web_vitals?: boolean | null;
  };
  metrics?: VitalMetric[];
  supporting_metrics?: VitalMetric[];
  recommended_actions?: Array<{
    action_id?: string;
    display_name?: string;
    why_it_matters?: string;
    steps?: string[];
    effort?: string;
  }>;
  search_caveat?: string;
};

type PerformanceMeasurement = {
  id?: string;
  source?: "crux_field" | "pagespeed_lab";
  scope?: "url" | "origin";
  form_factor?: "mobile" | "desktop";
  status?: "ready" | "insufficient_data" | "failed";
  measured_url?: string;
  fallback_to_origin?: boolean;
  source_version?: string | null;
  captured_at?: string;
  collection_period?: { start?: string | null; end?: string | null };
  metrics?: {
    lcp_ms?: number | null;
    inp_ms?: number | null;
    cls?: number | null;
    ttfb_ms?: number | null;
    fcp_ms?: number | null;
    tbt_ms?: number | null;
    performance_score?: number | null;
  };
  assessment?: VitalAssessment | null;
  diagnostics?: {
    opportunities?: Array<{
      audit_id?: string;
      title?: string;
      description?: string;
      estimated_savings_ms?: number;
    }>;
  };
  error?: { code?: string; message?: string } | null;
};

type PerformanceSummary = {
  campaign_id?: string;
  form_factor?: "mobile" | "desktop";
  latest?: {
    crux_field?: PerformanceMeasurement;
    pagespeed_lab?: PerformanceMeasurement;
  };
  history?: PerformanceMeasurement[];
  sync?: {
    state?: "not_started" | "current" | "failed";
    last_success_at?: string | null;
    next_refresh_at?: string | null;
  };
};

type SiteIntegrityFinding = {
  code?: string;
  url?: string;
  severity?: "high" | "medium" | "low";
  title?: string;
  evidence?: string;
  action?: string;
  source?: string;
  observed_at?: string;
  confidence?: string;
};

type SiteIntegritySummary = {
  campaign_id?: string;
  status?: "needs_connection" | "not_started" | "stale" | "attention" | "current";
  connection?: {
    connected?: boolean;
    site_url?: string | null;
    last_error?: string | null;
  };
  summary?: {
    inspected_urls?: number;
    indexed_urls?: number;
    attention_urls?: number;
    canonical_conflicts?: number;
    sitemap_count?: number;
    sitemap_errors?: number;
    sitemap_warnings?: number;
  };
  findings?: SiteIntegrityFinding[];
  freshness?: {
    observed_at?: string | null;
    is_stale?: boolean;
    stale_after_days?: number;
  };
  next_action?: {
    label?: string;
    description?: string;
    href?: string | null;
  };
  coverage_note?: string;
};

function formatVitalValue(metric: VitalMetric) {
  if (metric.value === null || metric.value === undefined) {
    return "Not enough data";
  }
  if (metric.metric_id === "cwv.cls") {
    return metric.value.toFixed(2);
  }
  return `${Math.round(metric.value).toLocaleString("en-US")} ms`;
}

function vitalStatusLabel(status?: VitalMetric["status"]) {
  if (status === "good") return "Good";
  if (status === "needs_improvement") return "Needs work";
  if (status === "poor") return "Poor";
  return "Not enough real-user data";
}

function vitalOwnerMeaning(metricId?: string) {
  if (metricId === "cwv.lcp") {
    return "How quickly the main part of the page appears.";
  }
  if (metricId === "cwv.inp") {
    return "How quickly the page responds after someone clicks or taps.";
  }
  return "Whether page content stays in place instead of jumping around.";
}

function CoreVitalCard({ metric }: { metric: VitalMetric }) {
  const goodBoundary = metric.thresholds?.good_boundary;
  const poorBoundary = metric.thresholds?.poor_boundary;
  const progress =
    metric.value !== null &&
    metric.value !== undefined &&
    poorBoundary &&
    poorBoundary > 0
      ? Math.min(100, Math.max(4, (metric.value / poorBoundary) * 100))
      : 0;
  const statusTone =
    metric.status === "good"
      ? "text-emerald-400"
      : metric.status === "poor"
        ? "text-rose-400"
        : metric.status === "needs_improvement"
          ? "text-amber-400"
          : "text-zinc-400";

  return (
    <article className="border-l-2 border-[#34353b] bg-white/[0.015] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            {metric.display_name || metric.metric_id}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            {formatVitalValue(metric)}
          </p>
        </div>
        <span className={`text-xs font-semibold ${statusTone}`}>
          {metric.status === "good" ? "✓ " : metric.status === "poor" ? "! " : ""}
          {vitalStatusLabel(metric.status)}
        </span>
      </div>
      <div className="mt-4">
        <div className="relative h-2 overflow-hidden rounded-full bg-gradient-to-r from-emerald-500/70 via-amber-500/70 to-rose-500/70">
          {progress > 0 ? (
            <span
              className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-white shadow"
              style={{ left: `calc(${progress}% - 2px)` }}
            />
          ) : null}
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
          <span>
            Good: {goodBoundary !== undefined ? (
              metric.metric_id === "cwv.cls" ? goodBoundary : `${goodBoundary} ms`
            ) : "—"}
          </span>
          <span>
            Poor: {poorBoundary !== undefined ? (
              metric.metric_id === "cwv.cls" ? `over ${poorBoundary}` : `over ${poorBoundary} ms`
            ) : "—"}
          </span>
        </div>
      </div>
      <p className="mt-3 text-sm leading-5 text-zinc-300">
        {vitalOwnerMeaning(metric.metric_id)}
      </p>
    </article>
  );
}

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
      return "Preferred page setting is invalid";
    case "canonical_external":
      return "Preferred page points to another website";
    case "canonical_points_elsewhere":
      return "Page points search engines to another version";
    case "canonical_target_missing":
      return "Preferred page does not exist in this scan";
    case "broken_internal_link":
      return "A website link leads to a broken page";
    case "duplicate_content":
      return "Two pages contain the same content";
    case "orphan_page":
      return "No scanned page links to this page";
    case "redirect_chain":
      return "Page sends visitors through several redirects";
    case "invalid_structured_data":
      return "Search result details contain an error";
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
    case "canonical_external":
      return "Search engines may treat a page on another website as the preferred version.";
    case "canonical_points_elsewhere":
      return "This page may be left out of search in favor of the page it points to.";
    case "canonical_target_missing":
      return "Search engines are being sent to a preferred page that the complete scan could not find.";
    case "broken_internal_link":
      return "Customers can hit a dead end while moving through the website.";
    case "duplicate_content":
      return "Search engines may struggle to choose which page should appear in results.";
    case "orphan_page":
      return "Customers and search engines may have trouble discovering this page from the pages checked in the scan.";
    case "redirect_chain":
      return "Extra redirects slow the trip to the final page and create more places for the path to break.";
    case "invalid_structured_data":
      return "Google may not be able to use the extra business details attached to this page.";
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
      return "Update the preferred page setting so it points to a valid page.";
    case "canonical_external":
      return "Confirm the other website is intentional; otherwise point to the correct page on this site.";
    case "canonical_points_elsewhere":
      return "Confirm which page should appear in search, then keep only that page as the preferred version.";
    case "canonical_target_missing":
      return "Point the preferred page setting to a working page on this website.";
    case "broken_internal_link":
      return "Update or remove the broken link so it leads to a working page.";
    case "duplicate_content":
      return "Keep one useful version, then merge, redirect, or rewrite the other page.";
    case "orphan_page":
      return "Link to this page from a related page, or remove it if it is no longer useful.";
    case "redirect_chain":
      return "Update links so they go straight to the final page in one step.";
    case "invalid_structured_data":
      return "Correct the page's search result details, then scan the website again.";
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

function issueDetail(details: Record<string, string | number | null>) {
  if (typeof details.target_url === "string") {
    const status =
      details.status_code !== undefined && details.status_code !== null
        ? ` (status ${details.status_code})`
        : "";
    return `${details.target_url}${status}`;
  }
  if (typeof details.duplicate_with === "string") {
    return `Matches ${details.duplicate_with}`;
  }
  if (typeof details.canonical_url === "string") {
    return `Points to ${details.canonical_url}`;
  }
  if (typeof details.redirect_count === "number") {
    return `${details.redirect_count} redirects before the final page`;
  }
  if (typeof details.invalid_blocks === "number") {
    return `${details.invalid_blocks} invalid search detail block${details.invalid_blocks === 1 ? "" : "s"}`;
  }
  if (typeof details.page_url === "string") {
    return details.page_url;
  }
  if (details.status_code !== undefined) {
    return `Status ${details.status_code}`;
  }
  if (typeof details.canonical === "string") {
    return `Canonical: ${details.canonical}`;
  }
  if (typeof details.h1_count === "number") {
    return `${details.h1_count} H1 tags`;
  }
  return "No extra details";
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
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [siteIntegrity, setSiteIntegrity] = useState<SiteIntegritySummary | null>(null);
  const [formFactor, setFormFactor] = useState<"mobile" | "desktop">("mobile");
  const [historyDays, setHistoryDays] = useState(90);
  const [measuring, setMeasuring] = useState(false);
  const [checkingIndex, setCheckingIndex] = useState(false);
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
  }, [setSelectedCampaignId]);

  const loadTechnicalData = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setRuns([]);
      setIssues([]);
      setMetrics(null);
      setPerformance(null);
      setSiteIntegrity(null);
      return;
    }

    const [
      runsResponse,
      issuesResponse,
      metricsResponse,
      performanceResponse,
      integrityResponse,
    ] = await Promise.all([
      platformApi(`/crawl/runs?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/crawl/issues?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi("/crawl/metrics", { method: "GET" }),
      platformApi(
        `/website-performance/summary?campaign_id=${encodeURIComponent(campaignId)}&form_factor=${formFactor}&days=${historyDays}`,
        { method: "GET" },
      ),
      platformApi(`/crawl/site-integrity?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
    ]);

    setRuns(Array.isArray(runsResponse?.items) ? (runsResponse.items as CrawlRun[]) : []);
    setIssues(Array.isArray(issuesResponse?.items) ? (issuesResponse.items as TechnicalIssue[]) : []);
    setMetrics((metricsResponse as CrawlMetrics) || null);
    setPerformance((performanceResponse as PerformanceSummary) || null);
    setSiteIntegrity((integrityResponse as SiteIntegritySummary) || null);
  }, [formFactor, historyDays]);

  const runIndexCheck = useCallback(async () => {
    if (!selectedCampaignId) {
      return;
    }
    if (!siteIntegrity?.connection?.connected) {
      router.push("/settings");
      return;
    }
    setCheckingIndex(true);
    setError("");
    setNotice("");
    try {
      const result = await platformApi("/crawl/site-integrity/refresh", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, max_urls: 10 }),
      });
      const nextIntegrity = result?.integrity as SiteIntegritySummary | undefined;
      if (nextIntegrity) {
        setSiteIntegrity(nextIntegrity);
      }
      const checked = Number(result?.refresh?.inspected_urls || 0);
      const failed = Number(result?.refresh?.failed_urls || 0);
      setNotice(
        failed > 0
          ? `Google's saved information was checked for ${checked} page${checked === 1 ? "" : "s"}. ${failed} page${failed === 1 ? " needs" : "s need"} another try.`
          : `Google's saved information was checked for ${checked} important page${checked === 1 ? "" : "s"}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check Google index information.");
    } finally {
      setCheckingIndex(false);
    }
  }, [router, selectedCampaignId, siteIntegrity?.connection?.connected]);

  const runPerformanceCheck = useCallback(async () => {
    if (!selectedCampaignId) {
      return;
    }
    setMeasuring(true);
    setError("");
    setNotice("");
    try {
      const result = await platformApi(
        `/website-performance/collect?campaign_id=${encodeURIComponent(selectedCampaignId)}&form_factor=${formFactor}`,
        { method: "POST" },
      );
      if (result?.status === "completed") {
        const measurements = Array.isArray(result?.result?.measurements)
          ? (result.result.measurements as PerformanceMeasurement[])
          : [];
        const failedSources = measurements
          .filter((measurement) => measurement.status === "failed")
          .map((measurement) =>
            measurement.source === "pagespeed_lab" ? "lab test" : "real-user lookup",
          );
        setNotice(
          failedSources.length > 0
            ? `The ${failedSources.join(" and ")} needs attention. The successful results are shown below.`
            : `${formFactor === "mobile" ? "Phone" : "Computer"} speed test completed. The newest results are shown below.`,
        );
      } else {
        setNotice("The website speed test was queued. Reload shortly to see the result.");
      }
      await loadTechnicalData(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to test website performance.");
    } finally {
      setMeasuring(false);
    }
  }, [formFactor, loadTechnicalData, selectedCampaignId]);

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
        body: `The latest website scan is ${toTitleCase(latestRun.status)} and no problems are currently listed.`,
        next: "Keep scanning regularly so new problems are caught early.",
      };
    }

    return {
      title: `${issueLabel(topIssue.issueCode)} should be fixed first`,
      body: `${topIssue.count} page${topIssue.count === 1 ? " is" : "s are"} affected, and the highest priority is ${topIssue.highestSeverity}. ${issueImpact(topIssue.issueCode)}`,
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
        const detailText = issueDetail(details);

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

  const fieldMeasurement = performance?.latest?.crux_field;
  const labMeasurement = performance?.latest?.pagespeed_lab;
  const vitalMetrics = fieldMeasurement?.assessment?.metrics || [];
  const recommendedPerformanceAction =
    fieldMeasurement?.assessment?.recommended_actions?.[0] || null;
  const performanceHistoryData = useMemo(
    () =>
      (performance?.history || []).map((measurement) => {
        const measurementMetrics = measurement.assessment?.metrics || [];
        const targetRatio = (metricId: string) => {
          const metric = measurementMetrics.find((item) => item.metric_id === metricId);
          const target = metric?.thresholds?.good_boundary;
          if (metric?.value === null || metric?.value === undefined || !target) {
            return null;
          }
          return Math.round((metric.value / target) * 100);
        };
        return {
          label: new Date(
            measurement.collection_period?.end ||
              measurement.captured_at ||
              Date.now(),
          ).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
          lcp: targetRatio("cwv.lcp"),
          inp: targetRatio("cwv.inp"),
          cls: targetRatio("cwv.cls"),
        };
      }),
    [performance?.history],
  );

  const performanceHeadline = useMemo(() => {
    const status = fieldMeasurement?.assessment?.assessment?.status;
    if (!fieldMeasurement) {
      return {
        title: "Website speed has not been measured yet",
        summary:
          "Run the first test to compare real customer experience with Google's current Core Web Vitals targets.",
        tone: "text-zinc-100",
      };
    }
    if (fieldMeasurement.status === "failed") {
      return {
        title: "The latest real-user measurement failed",
        summary:
          fieldMeasurement.error?.message ||
          "Run the test again. Your saved crawl results are still available below.",
        tone: "text-rose-300",
      };
    }
    if (status === "good") {
      return {
        title: "Real customers are getting a good page experience",
        summary:
          "All three Core Web Vitals are within Google's good range for this device type.",
        tone: "text-emerald-300",
      };
    }
    if (status === "insufficient_data") {
      return {
        title: "Google does not have enough real-user data yet",
        summary:
          "This is not a pass or a failure. Use the one-time lab test as a diagnostic while more customer visits accumulate.",
        tone: "text-amber-200",
      };
    }
    return {
      title: "Customer experience needs work",
      summary:
        recommendedPerformanceAction?.why_it_matters ||
        "At least one Core Web Vital is outside Google's good range. Start with the first recommendation below.",
      tone: status === "poor" ? "text-rose-300" : "text-amber-200",
    };
  }, [fieldMeasurement, recommendedPerformanceAction]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Speed measurement",
        value:
          fieldMeasurement?.status === "failed"
            ? "Test failed"
            : fieldMeasurement
              ? "Current"
              : "Not measured",
        tone:
          fieldMeasurement?.status === "failed"
            ? "danger"
            : fieldMeasurement
              ? "success"
              : "warning",
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
            ? "info"
            : scanLaneHealthy
              ? "success"
              : "danger",
      },
      {
        label: "Lab test",
        value:
          labMeasurement?.status === "failed"
            ? "Needs attention"
            : labMeasurement
              ? "Current"
              : "Not measured",
        tone:
          labMeasurement?.status === "failed"
            ? "warning"
            : labMeasurement
              ? "success"
              : "info",
      },
    ],
    [fieldMeasurement, labMeasurement, scanLaneHealthy],
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
            onClick={() => void runPerformanceCheck()}
            disabled={!selectedCampaignId || measuring}
            className="rounded-md border border-accent-500/35 bg-accent-500/12 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {measuring ? "Testing website…" : "Test website now"}
          </button>
          <button
            onClick={() => {
              setNotice("Saved website health data reloaded.");
              void loadTechnicalData(selectedCampaignId);
            }}
            disabled={!selectedCampaignId || measuring}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reload saved data
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Website health"
          title="Is your website helping or hurting you?"
          summary="See problems that could keep customers or search engines from using your website, which one to fix first, and the next practical step."
        />

        <TruthNotice title="Start with the first problem marked in red or amber.">
          Fix one priority at a time. Open technical details only when a developer needs them.
        </TruthNotice>

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
            <OwnerDecisionPanel
              eyebrow="Fix this first"
              title={topSummary.title}
              summary={topSummary.body}
              nextStep={topSummary.next}
              actionLabel={topIssue ? "Review affected pages" : latestRun ? "Run another scan" : "Run the first scan"}
              onAction={() => {
                if (topIssue) {
                  document.getElementById("issue-details")?.scrollIntoView({ behavior: "smooth" });
                  return;
                }
                router.push("/dashboard");
              }}
              tone={
                (severityCounts.high || 0) > 0
                  ? "urgent"
                  : topIssue
                    ? "warning"
                    : latestRun
                      ? "positive"
                      : "neutral"
              }
            />

            <section className="space-y-5 border-y border-[#26272c] bg-[#111214]/70 px-4 py-5 md:px-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-400">
                    Google index check
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
                    Can Google find and keep your important pages?
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    Compare Google&apos;s saved page information with the latest website scan. Start with
                    the first problem below; technical evidence stays available when a developer needs it.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void runIndexCheck()}
                  disabled={!selectedCampaignId || checkingIndex}
                  className="rounded-md bg-accent-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {checkingIndex
                    ? "Checking important pages…"
                    : siteIntegrity?.connection?.connected
                      ? siteIntegrity?.summary?.inspected_urls
                        ? "Check again"
                        : "Check important pages"
                      : "Connect Google first"}
                </button>
              </div>

              <div className="grid gap-px overflow-hidden rounded-md border border-[#26272c] bg-[#26272c] sm:grid-cols-2 xl:grid-cols-4">
                {[
                  {
                    label: "Pages checked",
                    value: siteIntegrity?.summary?.inspected_urls ?? 0,
                    detail: "Important pages with saved Google evidence",
                  },
                  {
                    label: "Confirmed in Google",
                    value: siteIntegrity?.summary?.indexed_urls ?? 0,
                    detail: "Pages Google reported as indexed",
                  },
                  {
                    label: "Need attention",
                    value: siteIntegrity?.summary?.attention_urls ?? 0,
                    detail: "Pages without a clear indexed result",
                  },
                  {
                    label: "Sitemap problems",
                    value:
                      (siteIntegrity?.summary?.sitemap_errors ?? 0) +
                      (siteIntegrity?.summary?.sitemap_warnings ?? 0),
                    detail: "Errors and warnings reported by Google",
                  },
                ].map((item) => (
                  <div key={item.label} className="bg-[#111214] px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                      {item.label}
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-white">{item.value}</p>
                    <p className="mt-1 text-xs leading-5 text-zinc-400">{item.detail}</p>
                  </div>
                ))}
              </div>

              {!siteIntegrity?.connection?.connected ? (
                <div className="border-l-2 border-amber-400 bg-amber-400/[0.07] px-4 py-4">
                  <h3 className="text-sm font-semibold text-amber-100">
                    Connect Google Search Console to confirm index status
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    The website scan still works without it, but only Google can confirm its saved index
                    result for a page.
                  </p>
                </div>
              ) : (siteIntegrity?.findings || []).length > 0 ? (
                <div className="space-y-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      What to fix first
                    </p>
                    <p className="mt-1 text-sm text-zinc-300">
                      These findings point to a specific page, evidence, source, and next step.
                    </p>
                  </div>
                  {(siteIntegrity?.findings || []).slice(0, 5).map((finding) => (
                    <article
                      key={`${finding.code}-${finding.url}`}
                      className={`border-l-2 px-4 py-4 ${
                        finding.severity === "high"
                          ? "border-rose-500 bg-rose-500/[0.06]"
                          : finding.severity === "medium"
                            ? "border-amber-400 bg-amber-400/[0.05]"
                            : "border-zinc-600 bg-white/[0.02]"
                      }`}
                    >
                      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-white">{finding.title}</p>
                          <p className="mt-1 break-all text-xs text-zinc-500">{finding.url}</p>
                        </div>
                        <span className="text-xs font-semibold text-zinc-400">
                          {finding.severity === "high"
                            ? "Fix first"
                            : finding.severity === "medium"
                              ? "Fix next"
                              : "Monitor"}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-zinc-300">{finding.evidence}</p>
                      <p className="mt-2 text-sm font-medium leading-6 text-zinc-100">
                        Next: {finding.action}
                      </p>
                      <p className="mt-3 text-xs leading-5 text-zinc-500">
                        Source: {finding.source} · checked {formatRelativeTime(finding.observed_at)}
                      </p>
                    </article>
                  ))}
                </div>
              ) : siteIntegrity?.summary?.inspected_urls ? (
                <div className="border-l-2 border-emerald-500 bg-emerald-500/[0.06] px-4 py-4">
                  <h3 className="text-sm font-semibold text-emerald-100">
                    No urgent index problem was confirmed
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    Keep monitoring after publishing, redirecting, or changing important pages.
                  </p>
                </div>
              ) : (
                <div className="border-l-2 border-zinc-600 bg-white/[0.02] px-4 py-4">
                  <h3 className="text-sm font-semibold text-zinc-100">
                    Run the first Google index check
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">
                    InsightOS will check up to 10 important pages at a time to protect the connection&apos;s
                    daily limit.
                  </p>
                </div>
              )}

              <details className="border-t border-[#26272c] pt-4 text-xs leading-5 text-zinc-500">
                <summary className="cursor-pointer font-semibold text-zinc-400">
                  How this check should be read
                </summary>
                <p className="mt-2 max-w-4xl">
                  {siteIntegrity?.coverage_note ||
                    "This checks Google's saved index information, not a live indexing test. A sitemap submission is not treated as proof that a page is indexed."}
                </p>
                {siteIntegrity?.freshness?.observed_at ? (
                  <p className="mt-2">
                    Latest saved evidence: {formatRelativeTime(siteIntegrity.freshness.observed_at)}
                    {siteIntegrity.freshness.is_stale ? " · refresh recommended" : " · current"}
                  </p>
                ) : null}
              </details>
            </section>

            <section className="space-y-5 border-y border-[#26272c] bg-[#111214]/70 px-4 py-5 md:px-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-400">
                    Real customer experience
                  </p>
                  <h2 className={`mt-2 text-2xl font-semibold tracking-[-0.03em] ${performanceHeadline.tone}`}>
                    {performanceHeadline.title}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    {performanceHeadline.summary}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex rounded-md bg-[#0d0e10] p-1" aria-label="Device type">
                    {(["mobile", "desktop"] as const).map((device) => (
                      <button
                        key={device}
                        type="button"
                        onClick={() => setFormFactor(device)}
                        className={`rounded px-3 py-1.5 text-sm font-medium ${
                          formFactor === device
                            ? "bg-accent-500 text-white"
                            : "text-zinc-400 hover:text-white"
                        }`}
                      >
                        {device === "mobile" ? "Phone" : "Computer"}
                      </button>
                    ))}
                  </div>
                  <label className="flex items-center gap-2 text-xs text-zinc-400">
                    History
                    <select
                      value={historyDays}
                      onChange={(event) => setHistoryDays(Number(event.target.value))}
                      className="rounded-md border border-[#303137] bg-[#0d0e10] px-2.5 py-2 text-sm text-zinc-100"
                    >
                      <option value={30}>30 days</option>
                      <option value={90}>90 days</option>
                      <option value={180}>6 months</option>
                      <option value={365}>1 year</option>
                    </select>
                  </label>
                </div>
              </div>

              {!fieldMeasurement && !labMeasurement ? (
                <EmptyState
                  title="Measure the website against Google's current targets"
                  summary="This runs a real-user Core Web Vitals lookup and a separate one-time lab test for the selected location and device."
                  actionLabel={measuring ? "Test in progress…" : "Run the first speed test"}
                  onAction={() => void runPerformanceCheck()}
                />
              ) : (
                <>
                  <div className="grid gap-4 xl:grid-cols-3">
                    {vitalMetrics.map((metric) => (
                      <CoreVitalCard key={metric.metric_id} metric={metric} />
                    ))}
                  </div>

                  <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
                    <ChartCard
                      eyebrow={`${historyDays}-day history`}
                      title="How close each Core Web Vital is to Google's good range"
                      summary="100% is the edge of Google's good range. Lower is better. Field measurements use a rolling 28-day window, so changes appear gradually."
                      chart={
                        performanceHistoryData.length > 0 ? (
                          <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={performanceHistoryData}>
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
                                  width={42}
                                  unit="%"
                                />
                                <Tooltip content={<SiteHealthTooltip />} />
                                <ReferenceLine
                                  y={100}
                                  stroke="#34d399"
                                  strokeDasharray="6 5"
                                  label={{ value: "Good limit", fill: "#6ee7b7", fontSize: 11 }}
                                />
                                <Line
                                  type="monotone"
                                  dataKey="lcp"
                                  name="Main content load"
                                  stroke="#FF6A1A"
                                  strokeWidth={3}
                                  connectNulls
                                />
                                <Line
                                  type="monotone"
                                  dataKey="inp"
                                  name="Click response"
                                  stroke="#60a5fa"
                                  strokeWidth={3}
                                  connectNulls
                                />
                                <Line
                                  type="monotone"
                                  dataKey="cls"
                                  name="Layout stability"
                                  stroke="#c084fc"
                                  strokeWidth={3}
                                  connectNulls
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        ) : (
                          <ChartEmptyState
                            title="History starts with the first measurement"
                            summary="Run the first test now. Future scheduled measurements will make the trend visible here."
                          />
                        )
                      }
                      footer={
                        <div className="space-y-1 text-xs leading-5 text-zinc-400">
                          <p>
                            Source: Google Chrome UX Report ·{" "}
                            {fieldMeasurement?.fallback_to_origin
                              ? "origin-level fallback because this page lacks enough visits"
                              : "page-level real-user data"}
                          </p>
                          <p>
                            Latest window ended{" "}
                            {fieldMeasurement?.collection_period?.end
                              ? new Date(fieldMeasurement.collection_period.end).toLocaleDateString()
                              : "on an unavailable date"}
                            . Passing these targets helps page experience but does not guarantee higher rankings.
                          </p>
                        </div>
                      }
                    />

                    <section className="border-l-2 border-[#34353b] bg-white/[0.015] px-5 py-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        One-time lab test
                      </p>
                      <div className="mt-3 flex items-end gap-3">
                        <p className="text-4xl font-semibold tracking-[-0.04em] text-white">
                          {labMeasurement?.metrics?.performance_score ?? "—"}
                        </p>
                        <p className="pb-1 text-sm text-zinc-400">performance score / 100</p>
                      </div>
                      <p className="mt-3 text-sm leading-5 text-zinc-300">
                        This controlled test helps diagnose fixes. It is separate from what real customers experienced.
                      </p>
                      {labMeasurement?.status === "failed" ? (
                        <div className="mt-5 border-l-2 border-rose-500 bg-rose-500/[0.07] px-3 py-3">
                          <p className="text-sm font-semibold text-rose-200">
                            The lab test did not finish
                          </p>
                          <p className="mt-1 text-xs leading-5 text-rose-100/80">
                            {labMeasurement.error?.message ||
                              "Run the website test again. The real-user result above is still valid."}
                          </p>
                        </div>
                      ) : (labMeasurement?.diagnostics?.opportunities || []).length > 0 ? (
                        <div className="mt-5 space-y-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                            Biggest technical opportunities
                          </p>
                          {(labMeasurement?.diagnostics?.opportunities || []).slice(0, 3).map((item) => (
                            <div key={item.audit_id || item.title} className="border-t border-[#2a2b30] pt-3">
                              <p className="text-sm font-medium text-zinc-100">{item.title}</p>
                              <p className="mt-1 text-xs text-zinc-400">
                                About {Math.round(item.estimated_savings_ms || 0)} ms of lab-test savings
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-5 text-sm text-zinc-400">
                          No major lab opportunity was returned in the latest test.
                        </p>
                      )}
                      <p className="mt-5 text-xs leading-5 text-zinc-500">
                        Lighthouse {labMeasurement?.source_version || "version unavailable"} · tested{" "}
                        {formatRelativeTime(labMeasurement?.captured_at)}
                      </p>
                    </section>
                  </div>

                  {recommendedPerformanceAction ? (
                    <section className="border-l-2 border-accent-500 bg-accent-500/[0.06] px-5 py-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">
                        Best speed improvement to start with
                      </p>
                      <h3 className="mt-2 text-lg font-semibold text-white">
                        {recommendedPerformanceAction.display_name}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-zinc-300">
                        {recommendedPerformanceAction.why_it_matters}
                      </p>
                      {recommendedPerformanceAction.steps?.[0] ? (
                        <p className="mt-3 text-sm font-medium text-zinc-100">
                          First step: {recommendedPerformanceAction.steps[0]}
                        </p>
                      ) : null}
                    </section>
                  ) : null}
                </>
              )}
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
                    ? `Latest website scan was ${toTitleCase(latestRun.status)} ${formatRelativeTime(latestRun.finished_at || latestRun.created_at)}.`
                    : "No website scan has run yet."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-2">
              <ChartCard
                eyebrow="Current priorities"
                title="What needs attention first"
                summary="Problems are ordered by urgency: fix the red items first, then work through the amber items and lower-risk cleanup."
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
                      summary="The latest scan did not find any website problems. Run scans regularly to catch new ones."
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
                  {latestRunIssues.length} problem{latestRunIssues.length === 1 ? "" : "s"} recorded.
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
