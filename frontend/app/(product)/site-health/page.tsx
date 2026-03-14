"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  ComparisonTable,
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

function severityTone(severity?: string) {
  if (severity === "high") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }

  if (severity === "medium") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }

  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
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

export default function SiteHealthPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
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
        setError(err instanceof Error ? err.message : "Unable to load technical health data.");
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
      setError(err instanceof Error ? err.message : "Unable to load technical health data.");
    });
  }, [selectedCampaignId, loading, loadTechnicalData]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const latestRun = runs[0] ?? null;

  const severityCounts = useMemo(() => {
    return issues.reduce(
      (accumulator, issue) => {
        const key = issue.severity || "low";
        accumulator[key] = (accumulator[key] || 0) + 1;
        return accumulator;
      },
      {} as Record<string, number>,
    );
  }, [issues]);

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

    issues.forEach((issue) => {
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
  }, [issues]);

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
        body: "Set up a business first so InsightOS can scan the site and find technical issues.",
        next: "Go back to the dashboard to run the first website scan.",
      };
    }

    if (!latestRun) {
      return {
        title: `${selectedCampaign.name || "This business"} has not been scanned yet`,
        body: "Technical health starts with a website scan. No scan has run for this business yet.",
        next: "Run the first website scan, then return here to review what needs fixing first.",
      };
    }

    if (!topIssue) {
      return {
        title: "No technical issues are currently flagged",
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
      issues.slice(0, 6).map((issue) => {
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
    [issues],
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
        value: issues.length ? `${issues.length} found` : "No issues",
        tone: issues.length > 0 ? "warning" : "success",
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
    [issues.length, latestRun, scanLaneHealthy, severityCounts.high],
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
      dateRangeLabel="Live technical health data"
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
            onClick={() => {
              setNotice("Technical health data refreshed.");
              void loadTechnicalData(selectedCampaignId);
            }}
            disabled={!selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Refresh
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
          eyebrow="Technical health"
          title="What the website scan found"
          summary="Use this page to see which technical issues matter most, what should be fixed first, and what to keep watching after the latest scan."
        />

        {loading ? (
          <LoadingCard
            title="Loading technical health"
            summary="Pulling the latest scan state, issue groups, and technical fix priorities for the active business."
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
            title="No business is ready for technical health yet"
            summary="Set up a business first so InsightOS can scan the website and find technical issues."
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
                    {topSummary.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.body}</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Fix first
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{topSummary.next}</p>
                </div>
              </div>
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="High severity"
                value={String(severityCounts.high || 0)}
                summary="These issues are the most likely to block visibility or break important pages."
                tone="highlight"
              />
              <KpiCard
                label="Medium severity"
                value={String(severityCounts.medium || 0)}
                summary="These issues weaken search clarity and should be fixed after the critical ones."
              />
              <KpiCard
                label="Low severity"
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

            {runs.length === 0 ? (
              <EmptyState
                title="No website scans have run yet"
                summary="Run your first website scan from the dashboard to see technical issues and fix priorities here."
                actionLabel="Go to dashboard"
                onAction={() => router.push("/dashboard")}
              />
            ) : (
              <>
                <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
                  <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Scan state
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Latest scan and what it means
                    </h2>
                    <div className="mt-4 space-y-3">
                      <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-sm font-medium text-white">Latest scan status</p>
                        <p className="mt-2 text-sm leading-6 text-zinc-300">
                          {latestRun
                            ? `${toTitleCase(latestRun.status)} ${formatRelativeTime(latestRun.finished_at || latestRun.created_at)}`
                            : "No scan available."}
                        </p>
                      </div>
                      <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-sm font-medium text-white">Coverage</p>
                        <p className="mt-2 text-sm leading-6 text-zinc-300">
                          {latestRun?.pages_discovered
                            ? `${latestRun.pages_discovered} pages were discovered in the latest scan.`
                            : "The latest scan did not report discovered pages yet."}
                        </p>
                      </div>
                      <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                        <p className="text-sm font-medium text-white">Scan processing</p>
                        <p className="mt-2 text-sm leading-6 text-zinc-300">
                          {scanLaneHealthy === null
                            ? "No scan processing metrics are available yet."
                            : scanLaneHealthy
                              ? "The scan system is processing normally."
                              : "The scan system is showing signs of delay, so results may refresh more slowly than usual."}
                        </p>
                      </div>
                    </div>
                  </section>

                  <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Priority buckets
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Which issues matter most
                    </h2>
                    <div className="mt-4 space-y-3">
                      {[
                        {
                          key: "high",
                          title: "Fix first",
                          summary: "These issues can block pages from performing properly in search.",
                        },
                        {
                          key: "medium",
                          title: "Fix next",
                          summary: "These issues weaken search clarity and reduce page quality.",
                        },
                        {
                          key: "low",
                          title: "Clean up after",
                          summary: "These issues are smaller, but still worth cleaning up once the bigger problems are handled.",
                        },
                      ].map((bucket) => (
                        <div key={bucket.key} className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium text-white">{bucket.title}</p>
                              <p className="mt-2 text-sm leading-6 text-zinc-300">{bucket.summary}</p>
                            </div>
                            <span className={`rounded-md border px-2 py-1 text-xs font-medium ${severityTone(bucket.key)}`}>
                              {severityCounts[bucket.key] || 0}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>

                <ComparisonTable
                  title="Top issue groups"
                  columns={[
                    { key: "issue", label: "Issue" },
                    { key: "severity", label: "Severity" },
                    { key: "affected", label: "Affected Pages" },
                    { key: "impact", label: "Why It Matters" },
                    { key: "first_fix", label: "Fix First" },
                  ]}
                  rows={issueTableRows}
                />

                <ComparisonTable
                  title="Most recent issue detections"
                  columns={[
                    { key: "issue", label: "Issue" },
                    { key: "severity", label: "Severity" },
                    { key: "detected", label: "Detected" },
                    { key: "detail", label: "Detail" },
                  ]}
                  rows={latestIssueRows}
                />
              </>
            )}
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
