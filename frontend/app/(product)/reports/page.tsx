"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  OwnerDecisionPanel,
  ProductPageIntro,
  ReportPreview,
  TruthNotice,
  useLocationContext,
  type ReportSection,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi, platformApiFile } from "../../platform/api";
import {
  buildRuntimeTruthSignal,
} from "../truth/runtimeTruth.mjs";
import {
  getDeliveryWorkflowState,
  getReportWorkflowState,
  getScheduleWorkflowState,
  isFailedStatus,
  isPendingStatus,
} from "../truth/reportsTruth.mjs";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type ReportItem = {
  id: string;
  campaign_id: string;
  month_number: number | string;
  report_status?: string;
  summary_json?: string;
  generated_at?: string;
};

type ReportArtifact = {
  id: string;
  artifact_type?: string;
  storage_path?: string;
  storage_mode?: string;
  content_type?: string;
  byte_size?: number;
  ready?: boolean;
  retrievable?: boolean;
  durable?: boolean;
  reason?: string;
  created_at?: string;
};

type ReportRecipient = {
  id: string;
  campaign_id: string;
  email: string;
  display_name?: string;
  recipient_role: string;
  enabled: boolean;
};

type ReportShareLink = {
  id: string;
  report_id: string;
  expires_at: string;
  revoked_at?: string;
  last_opened_at?: string;
  open_count: number;
  status: "active" | "expired" | "revoked";
  share_url?: string;
};

type ReportDeliveryEvent = {
  id: string;
  delivery_channel: string;
  delivery_status: string;
  recipient: string;
  sent_at: string | null;
  created_at: string;
};

type ReportDetail = {
  report: ReportItem;
  artifacts: ReportArtifact[];
  delivery_events?: ReportDeliveryEvent[];
  snapshot?: ReportSnapshot;
  truth?: RuntimeTruth;
};

type ReportReadinessSource = {
  key: string;
  label: string;
  state: "ready" | "partial" | "stale" | "missing" | "optional" | string;
  detail: string;
  last_updated?: string | null;
  optional?: boolean;
  action_label?: string;
  action_href?: string;
};

type ReportReadiness = {
  campaign_id: string;
  checked_at: string;
  status: "ready" | "limited" | "needs_setup" | string;
  title: string;
  summary: string;
  can_generate: boolean;
  warning_count: number;
  sources: ReportReadinessSource[];
};

type PortfolioReportLocation = {
  campaign_id: string;
  business_location_id?: string | null;
  location_name: string;
  domain?: string;
  comparison_state: "ready" | "missing_report" | "legacy_report" | "invalid_snapshot" | string;
  comparison_message: string;
  report?: {
    id: string;
    month_number: number;
    status: string;
    generated_at: string;
    snapshot_hash?: string | null;
    snapshot_version?: string;
  } | null;
  period?: {
    start?: string;
    end?: string;
    comparison_start?: string;
    comparison_end?: string;
  } | null;
  metrics: ReportMetric[];
  wins_count: number;
  risks_count: number;
  next_action?: {
    title?: string;
    why_it_matters?: string;
  } | null;
  source_freshness: string;
};

type PortfolioReportComparison = {
  organization_id: string;
  checked_at: string;
  source_contract: string;
  totals_are_combined: false;
  location_count: number;
  comparable_location_count: number;
  periods_aligned: boolean;
  comparison_ready: boolean;
  common_period?: {
    start?: string;
    end?: string;
    comparison_start?: string;
    comparison_end?: string;
  } | null;
  warnings: string[];
  focus?: {
    campaign_id: string;
    location_name: string;
    reason: string;
  } | null;
  locations: PortfolioReportLocation[];
};

type ReportMetric = {
  key: string;
  label: string;
  current: number | null;
  previous: number | null;
  change_percent: number | null;
  direction: "up" | "down" | "steady" | "not_enough_information";
  result: "improved" | "declined" | "about_the_same" | "not_enough_information";
  unit: string;
  explanation?: string;
  source?: {
    label?: string;
    system?: string;
    last_updated?: string | null;
  };
  coverage?: {
    current?: ReportCoverage;
    comparison?: ReportCoverage;
  };
};

type ReportCoverage = {
  state?: "complete" | "partial" | "unavailable" | string;
  observed?: number;
  expected?: number;
};

type ReportTrendPoint = {
  date?: string;
  [key: string]: string | number | null | undefined;
};

type ReportTrendSeries = {
  key: string;
  title?: string;
  description?: string;
  source_label?: string;
  points?: ReportTrendPoint[];
  comparison_points?: ReportTrendPoint[];
};

type ReportActionMeasurement = {
  label?: string;
  explanation?: string;
  status?: string;
  check_after_days?: number | null;
};

type ReportStoryItem = {
  id?: string;
  title: string;
  detail?: string;
  result?: string;
  status?: string;
  completed_at?: string | null;
  canonical_action_id?: string;
  why_it_matters?: string;
  steps?: string[];
  owner_role?: string;
  effort?: string;
  evidence?: string[];
  measurement?: ReportActionMeasurement;
};

type ReportSnapshot = {
  schema_version?: string;
  snapshot_hash?: string;
  audience?: string;
  campaign?: {
    location_name?: string;
    name?: string;
  };
  period?: {
    start?: string;
    end?: string;
    comparison_start?: string;
    comparison_end?: string;
  };
  executive_summary?: {
    headline?: string;
    summary?: string;
  };
  metrics?: ReportMetric[];
  trend_series?: ReportTrendSeries[];
  wins?: ReportStoryItem[];
  risks?: ReportStoryItem[];
  completed_actions?: ReportStoryItem[];
  measured_outcomes?: ReportStoryItem[];
  next_priorities?: ReportStoryItem[];
  source?: {
    freshness_state?: string;
    latest_metric_at?: string | null;
  };
  rank_snapshots?: number;
  technical_issues?: number;
  intelligence_score?: number | null;
  reviews_last_30d?: number;
  avg_rating_last_30d?: number | null;
};

type ReportSchedule = {
  id: string;
  campaign_id: string;
  cadence: string;
  timezone: string;
  next_run_at: string;
  enabled: boolean;
  retry_count: number;
  last_status: string;
  truth?: RuntimeTruth;
};

function coerceNumber(value: number | string | undefined, fallback = 0) {
  if (typeof value === "number") {
    return value;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toTitleCase(value?: string) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatRelativeTime(value?: string) {
  if (!value) {
    return "No report yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No report yet";
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

function parseSummary(summaryJson?: string) {
  if (!summaryJson) {
    return null;
  }

  try {
    return JSON.parse(summaryJson) as ReportSnapshot;
  } catch {
    return null;
  }
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

function statusTone(status?: string) {
  if (status === "delivered") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }

  if (status === "generated") {
    return "border-accent-500/20 bg-accent-500/10 text-zinc-100";
  }

  return "border-[#26272c] bg-[#141518] text-zinc-200";
}

function reportPurpose(report: ReportItem) {
  if (report.report_status === "delivered") {
    return "This report has already been sent and can be used as your latest client-facing summary.";
  }

  if (report.report_status === "generated") {
    return "This report is ready to review and send to a client or business owner.";
  }

  if (isFailedStatus(report.report_status)) {
    return "This report needs attention before it should be treated as ready to review or share.";
  }

  if (isPendingStatus(report.report_status)) {
    return "This report record exists, but it is still being prepared and should not be treated as complete yet.";
  }

  return "Use this report to package the latest scan, rankings, and visibility signals into one summary.";
}

function formatMetricValue(metric: ReportMetric) {
  if (metric.current === null || metric.current === undefined) {
    return "Not measured";
  }
  if (metric.unit === "rating") {
    return `${metric.current.toFixed(1)} / 5`;
  }
  if (metric.unit === "position") {
    return `#${metric.current.toFixed(1)}`;
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(metric.current);
}

const PORTFOLIO_VISIBLE_METRIC_KEYS = new Set([
  "google_visits",
  "google_appearances",
  "average_google_position",
  "tracked_keyword_position",
]);

function portfolioStateLabel(state: string) {
  if (state === "ready") return "Ready to compare";
  if (state === "missing_report") return "Needs a report";
  if (state === "legacy_report") return "Needs a fresh report";
  if (state === "invalid_snapshot") return "Report needs attention";
  return "Not ready";
}

function portfolioPeriodLabel(location: PortfolioReportLocation) {
  if (!location.period?.start || !location.period?.end) {
    return "No comparable date range yet";
  }
  return `${location.period.start} through ${location.period.end}`;
}

function portfolioMetricChangeLabel(metric: ReportMetric) {
  if (metric.change_percent === null || metric.result === "not_enough_information") {
    return "No full comparison";
  }
  if (metric.result === "improved") {
    return `Improved ${Math.abs(metric.change_percent).toFixed(1)}%`;
  }
  if (metric.result === "declined") {
    return `Needs attention ${Math.abs(metric.change_percent).toFixed(1)}%`;
  }
  return "About the same";
}

function portfolioMetricTone(metric: ReportMetric) {
  if (metric.result === "improved") return "text-emerald-300";
  if (metric.result === "declined") return "text-rose-300";
  return "text-zinc-500";
}

function metricTrendLabel(metric: ReportMetric) {
  if (metric.change_percent === null || metric.direction === "not_enough_information") {
    return "Waiting for a full comparison";
  }
  if (metric.direction === "steady") {
    return "No clear change";
  }
  return `${metric.direction === "up" ? "↑" : "↓"} ${Math.abs(metric.change_percent).toFixed(1)}% from the earlier period`;
}

function storyList(items: ReportStoryItem[], empty: string) {
  return (
    <div className="space-y-2">
      {items.length ? items.map((item, index) => (
        <div key={item.id || `${item.title}-${index}`} className="flex items-start gap-3 border-t border-[#26272c] pt-3 first:border-0 first:pt-0">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-500/15 text-xs font-semibold text-accent-300">
            {index + 1}
          </span>
          <div>
            <p className="text-sm font-medium text-white">{item.title}</p>
            {item.detail || item.result || item.status ? (
              <p className="mt-1 text-xs leading-5 text-zinc-400">{item.detail || toTitleCase(item.result || item.status)}</p>
            ) : null}
          </div>
        </div>
      )) : <p className="text-sm leading-6 text-zinc-400">{empty}</p>}
    </div>
  );
}

function canonicalStoryKey(item: ReportStoryItem) {
  return (item.canonical_action_id || item.title || item.id || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function uniqueStories(items: ReportStoryItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = canonicalStoryKey(item);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function nextActionList(items: ReportStoryItem[]) {
  const uniqueItems = uniqueStories(items);
  if (!uniqueItems.length) {
    return <p className="text-sm leading-6 text-zinc-400">No verified next action is ready yet.</p>;
  }
  return (
    <div className="space-y-3">
      {uniqueItems.map((item, index) => {
        const measurement = item.measurement;
        const checkLabel = measurement?.check_after_days
          ? `Check ${measurement.label || "the saved measurement"} again after ${measurement.check_after_days} days.`
          : `Measure ${measurement?.label || "the saved result"} before and after the work.`;
        return (
          <article key={item.id || canonicalStoryKey(item)} className="grid gap-3 rounded-md border border-[#26272c] bg-[#0f1012] p-4 sm:grid-cols-[2rem_1fr]">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-500 text-sm font-bold text-white">
              {index + 1}
            </span>
            <div>
              <h5 className="font-semibold text-white">{item.title}</h5>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                {item.why_it_matters || item.detail || "This action is tied to the saved evidence for this location."}
              </p>
              {item.steps?.length ? (
                <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm leading-6 text-zinc-200">
                  {item.steps.map((step) => <li key={step}>{step}</li>)}
                </ol>
              ) : null}
              <div className="mt-3 border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2 text-xs leading-5 text-emerald-100">
                <span className="font-semibold">How we will check it:</span> {checkLabel} {measurement?.explanation || ""}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function reportTrendChart({
  series,
  field,
  label,
  unit,
  lowerIsBetter = false,
}: {
  series: ReportTrendSeries;
  field: string;
  label: string;
  unit: string;
  lowerIsBetter?: boolean;
}) {
  const current = (series.points || []).filter((point) => typeof point[field] === "number");
  const comparison = (series.comparison_points || []).filter((point) => typeof point[field] === "number");
  const values = [...current, ...comparison].map((point) => Number(point[field]));
  if (!values.length) {
    return null;
  }
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (Math.abs(maximum - minimum) < 0.0001) {
    const padding = Math.max(Math.abs(maximum) * 0.1, 1);
    minimum -= padding;
    maximum += padding;
  }
  const coordinates = (points: ReportTrendPoint[]) => points.map((point, index) => {
    const x = 38 + (index / Math.max(points.length - 1, 1)) * 562;
    const value = Number(point[field]);
    const verticalRatio = lowerIsBetter
      ? (value - minimum) / (maximum - minimum)
      : (maximum - value) / (maximum - minimum);
    const y = 15 + verticalRatio * 125;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <article className="rounded-md border border-[#26272c] bg-[#0f1012] p-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold text-white">{label}</p>
        <p className="text-[10px] text-zinc-500">Orange: current · Blue: earlier</p>
      </div>
      <svg viewBox="0 0 620 175" role="img" aria-label={`${label} trend`} className="mt-2 w-full">
        <line x1="38" y1="15" x2="38" y2="140" stroke="#3f3f46" />
        <line x1="38" y1="140" x2="600" y2="140" stroke="#3f3f46" />
        <line x1="38" y1="77.5" x2="600" y2="77.5" stroke="#27272a" />
        <text x="0" y="20" fontSize="10" fill="#71717a">{(lowerIsBetter ? minimum : maximum).toLocaleString(undefined, { maximumFractionDigits: 1 })}</text>
        <text x="0" y="143" fontSize="10" fill="#71717a">{(lowerIsBetter ? maximum : minimum).toLocaleString(undefined, { maximumFractionDigits: 1 })}</text>
        {comparison.length ? <polyline points={coordinates(comparison)} fill="none" stroke="#38bdf8" strokeWidth="2" strokeDasharray="7 6" /> : null}
        {current.length ? <polyline points={coordinates(current)} fill="none" stroke="#ff5c1a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /> : null}
        <text x="38" y="165" fontSize="10" fill="#71717a">{String(current[0]?.date || "")}</text>
        <text x="600" y="165" textAnchor="end" fontSize="10" fill="#71717a">{String(current[current.length - 1]?.date || "")}</text>
      </svg>
      <p className="mt-1 text-xs leading-5 text-zinc-400">{series.description} Values shown in {unit}.{lowerIsBetter ? " Higher on the chart is better." : ""}</p>
    </article>
  );
}

function trendVisualizations(series: ReportTrendSeries[]) {
  const byKey = new Map(series.map((item) => [item.key, item]));
  const definitions = [
    ["google_discovery", "visits", "Visits from Google", "visits", false],
    ["google_discovery", "appearances", "Times shown on Google", "appearances", false],
    ["tracked_rankings", "average_position", "Average tracked keyword position", "position number", true],
    ["website_scans", "issues", "Issues found in website scans", "issues", true],
    ["review_growth", "reviews", "Recent review pace", "reviews", false],
  ];
  const charts = definitions.map(([key, field, label, unit, lowerIsBetter]) => {
    const item = byKey.get(String(key));
    return item ? reportTrendChart({ series: item, field: String(field), label: String(label), unit: String(unit), lowerIsBetter: Boolean(lowerIsBetter) }) : null;
  }).filter(Boolean);
  if (!charts.length) {
    return <p className="text-sm leading-6 text-zinc-400">No dated trend values are available yet. Charts will appear as connected data is saved.</p>;
  }
  return <div className="grid gap-3 xl:grid-cols-2">{charts}</div>;
}

function dataSourceList(metrics: ReportMetric[]) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-zinc-500">
          <tr><th className="pb-2 pr-4">Measurement</th><th className="pb-2 pr-4">Source</th><th className="pb-2 pr-4">Last updated</th><th className="pb-2">Coverage</th></tr>
        </thead>
        <tbody className="divide-y divide-[#26272c] text-zinc-300">
          {metrics.map((metric) => {
            const coverage = metric.coverage?.current;
            return (
              <tr key={metric.key}>
                <td className="py-2.5 pr-4 font-medium text-white">{metric.label}</td>
                <td className="py-2.5 pr-4">{metric.source?.label || "Saved InsightOS data"}</td>
                <td className="py-2.5 pr-4">{metric.source?.last_updated || "Not available"}</td>
                <td className="py-2.5">{toTitleCase(coverage?.state)} ({coverage?.observed || 0} of {coverage?.expected || 0})</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function buildReportSections(report?: ReportItem, providedSnapshot?: ReportSnapshot): ReportSection[] {
  const summary = providedSnapshot || parseSummary(report?.summary_json);

  if (!report || !summary) {
    return [
      {
        title: "No report preview yet",
        summary: "Generate a report to package your latest visibility data into a client-ready summary.",
      },
    ];
  }

  if (summary.metrics?.length) {
    const metrics = summary.metrics;
    return [
      {
        title: "Your results at a glance",
        summary: `These numbers cover ${summary.period?.start || "the current period"} through ${summary.period?.end || "the latest saved date"}. Each one is compared with the period immediately before it.`,
        visual: (
          <div className="grid gap-px overflow-hidden rounded-md border border-[#26272c] bg-[#26272c] sm:grid-cols-2 xl:grid-cols-3">
            {metrics.map((metric) => (
              <div key={metric.key} className="bg-[#0f1012] p-4">
                <p className="text-xs font-medium text-zinc-400">{metric.label}</p>
                <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">{formatMetricValue(metric)}</p>
                <p className={`mt-1 text-xs font-medium ${metric.result === "improved" ? "text-emerald-400" : metric.result === "declined" ? "text-rose-400" : "text-zinc-500"}`}>
                  {metricTrendLabel(metric)}
                </p>
              </div>
            ))}
          </div>
        ),
      },
      {
        title: "Performance over time",
        summary: "The solid orange lines show this report period. Dashed blue lines show the earlier period when a valid comparison is available.",
        visual: trendVisualizations(summary.trend_series || []),
      },
      {
        title: "What improved",
        summary: "Only changes supported by the saved comparison are shown as wins.",
        metric: `${summary.wins?.length || 0} wins`,
        visual: storyList(summary.wins || [], "No clear improvement was measured in this report window."),
      },
      {
        title: "What needs attention",
        summary: "These are measured declines or saved problems that still need work.",
        metric: `${summary.risks?.length || 0} items`,
        visual: storyList(summary.risks || [], "No measured risk was found in the available information."),
      },
      {
        title: "Work completed and results",
        summary: "Completed work stays separate from measured results, so the report never claims that an action helped before the follow-up data exists.",
        metric: `${summary.completed_actions?.length || 0} completed`,
        visual: storyList(
          summary.measured_outcomes?.length ? summary.measured_outcomes : summary.completed_actions || [],
          "No completed action or measured result was recorded for this period.",
        ),
      },
      {
        title: "What to do next",
        summary: "Start with the first item. Every action appears once, includes the practical steps, and names the measurement used to check whether it helped.",
        metric: `${uniqueStories(summary.next_priorities || []).length} actions`,
        visual: nextActionList(summary.next_priorities || []),
      },
      {
        title: "Where the numbers came from",
        summary: "Missing or partial data is shown plainly instead of being treated as zero.",
        visual: dataSourceList(metrics),
      },
    ];
  }

  return [
    {
      title: "Search visibility",
      summary: "This section shows how much ranking data has been captured for the current report window.",
      metric: `${coerceNumber(summary.rank_snapshots)} snapshots`,
    },
    {
      title: "Website health",
      summary: "This section highlights how many website issues were found when the report was assembled.",
      metric: `${coerceNumber(summary.technical_issues)} issues`,
    },
    {
      title: "Overall intelligence score",
      summary: "Use this score as a simple summary of overall business visibility and health.",
      metric:
        summary.intelligence_score === null || summary.intelligence_score === undefined
          ? "Not available"
          : String(summary.intelligence_score),
    },
    {
      title: "Review activity",
      summary: "This section summarizes recent review volume and average rating.",
      metric: `${coerceNumber(summary.reviews_last_30d)} reviews`,
    },
  ];
}

function getDeliveryStatusLabel(status?: string) {
  if (status === "sent") return "Sent";
  if (status === "failed") return "Failed";
  if (status === "queued") return "Queued";
  return toTitleCase(status);
}

function getDeliveryStatusTone(status?: string) {
  if (status === "sent") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "failed") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  if (status === "queued") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  return "border-[#26272c] bg-[#141518] text-zinc-200";
}

function getScheduleStatusLabel(status?: string) {
  if (status === "scheduled") return "Active";
  if (status === "disabled") return "Paused";
  if (status === "retry_pending") return "Retrying";
  if (status === "max_retries_exceeded") return "Paused — retries exhausted";
  return "Idle";
}

function getScheduleStatusTone(status?: string) {
  if (status === "scheduled") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "retry_pending") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  if (status === "max_retries_exceeded" || status === "disabled") {
    return "border-[#26272c] bg-[#141518] text-zinc-400";
  }
  return "border-[#26272c] bg-[#141518] text-zinc-200";
}

function hasTruthState(truth: RuntimeTruth | null | undefined, state: string) {
  return Array.isArray(truth?.states) && truth.states.includes(state);
}

function friendlyReportError(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message.trim() : "";
  if (
    !message ||
    /failed to fetch|networkerror|network request failed|internal server error|unexpected error/i.test(
      message,
    )
  ) {
    return fallback;
  }
  return message;
}


const SCHEDULE_TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
  "Australia/Sydney",
];

export default function ReportsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [selectedReportDetail, setSelectedReportDetail] = useState<ReportDetail | null>(null);
  const [reportReadiness, setReportReadiness] = useState<ReportReadiness | null>(null);
  const [portfolioComparison, setPortfolioComparison] = useState<PortfolioReportComparison | null>(null);
  const [reportsTruth, setReportsTruth] = useState<RuntimeTruth | null>(null);
  const [monthNumber, setMonthNumber] = useState("1");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipients, setRecipients] = useState<ReportRecipient[]>([]);
  const [shareLinks, setShareLinks] = useState<ReportShareLink[]>([]);
  const [newShareUrl, setNewShareUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [schedule, setSchedule] = useState<ReportSchedule | null>(null);
  const [scheduleCadence, setScheduleCadence] = useState("weekly");
  const [scheduleTimezone, setScheduleTimezone] = useState("America/New_York");
  const [scheduleNextRun, setScheduleNextRun] = useState("");
  const [scheduleEnabled, setScheduleEnabled] = useState(true);

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

  const loadReportDetail = useCallback(async (reportId: string) => {
    if (!reportId) {
      setSelectedReportDetail(null);
      return;
    }

    const detail = await platformApi(`/reports/${reportId}`, { method: "GET" });
    setSelectedReportDetail(detail);
    try {
      const linkResponse = await platformApi(`/reports/${reportId}/share-links`, { method: "GET" });
      setShareLinks(Array.isArray(linkResponse?.items) ? (linkResponse.items as ReportShareLink[]) : []);
    } catch {
      setShareLinks([]);
    }
  }, []);

  const loadRecipients = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setRecipients([]);
      return;
    }
    const response = await platformApi(
      `/reports/recipients?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    );
    setRecipients(Array.isArray(response?.items) ? (response.items as ReportRecipient[]) : []);
  }, []);

  const loadReports = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setReports([]);
      setSelectedReportId("");
      setSelectedReportDetail(null);
      return;
    }

    const response = await platformApi(
      `/reports?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    );
    const items = Array.isArray(response?.items) ? (response.items as ReportItem[]) : [];
    setReports(items);
    setReportsTruth((response?.truth as RuntimeTruth) || null);
    const nextSelectedId = items[0]?.id || "";
    setSelectedReportId(nextSelectedId);

    if (nextSelectedId) {
      await loadReportDetail(nextSelectedId);
    } else {
      setSelectedReportDetail(null);
    }
  }, [loadReportDetail]);

  const loadReportReadiness = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setReportReadiness(null);
      return;
    }
    const response = (await platformApi(
      `/reports/readiness?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    )) as ReportReadiness;
    setReportReadiness(response);
  }, []);

  const loadPortfolioComparison = useCallback(async () => {
    const response = (await platformApi(
      "/reports/portfolio-comparison",
      { method: "GET" },
    )) as PortfolioReportComparison;
    setPortfolioComparison(response);
  }, []);

  const loadSchedule = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setSchedule(null);
      return;
    }

    const s = (await platformApi(
      `/reports/schedule?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    )) as ReportSchedule | null;

    setSchedule(s ?? null);

    if (s) {
      setScheduleCadence(s.cadence);
      setScheduleTimezone(s.timezone);
      setScheduleNextRun(s.next_run_at ? s.next_run_at.slice(0, 16) : "");
      setScheduleEnabled(s.enabled);
    } else {
      setScheduleCadence("weekly");
      setScheduleTimezone("America/New_York");
      setScheduleNextRun("");
      setScheduleEnabled(true);
    }
  }, []);

  async function runAction(
    action: string,
    fn: () => Promise<void>,
    failureMessage = "We could not complete that step right now. Please try again.",
  ) {
    setBusyAction(action);
    setError("");
    setNotice("");

    try {
      await fn();
    } catch (err) {
      setError(friendlyReportError(err, failureMessage));
    } finally {
      setBusyAction("");
    }
  }

  async function generateReport() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction("generate", async () => {
      const parsedMonth = Number.parseInt(monthNumber, 10);
      const safeMonth = Number.isNaN(parsedMonth) ? 1 : Math.min(12, Math.max(1, parsedMonth));

      await platformApi("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          month_number: safeMonth,
        }),
      });

      const refreshResults = await Promise.allSettled([
        loadReports(selectedCampaignId),
        loadReportReadiness(selectedCampaignId),
        loadPortfolioComparison(),
      ]);
      const refreshFailed = refreshResults.some(
        (result) => result.status === "rejected",
      );

      setNotice(
        refreshFailed
          ? `Month ${safeMonth} was created successfully, but some details did not refresh. Reload this page to see the saved report.`
          : `Report request completed for month ${safeMonth}. Confirm below whether it is ready to send, still processing, or needs attention.`,
      );
    }, "We could not create the report right now. Your saved business data is safe. Please try again.");
  }

  async function deliverReport() {
    const reportId = selectedReportDetail?.report.id || selectedReportId;

    if (!reportId) {
      setError("Select a report first.");
      return;
    }

    if (!recipientEmail.trim()) {
      setError("Recipient email is required.");
      return;
    }

    await runAction("deliver", async () => {
      await platformApi(`/reports/${reportId}/deliver`, {
        method: "POST",
        body: JSON.stringify({
          recipient: recipientEmail.trim(),
        }),
      });

      await loadReports(selectedCampaignId);
      await loadReportDetail(reportId);
      setNotice(
        "Report delivery was requested. Confirm below whether it was sent, is still queued, or needs attention.",
      );
    });
  }

  async function saveRecipient() {
    if (!selectedCampaignId || !recipientEmail.trim()) {
      setError("Add the email address you want to save.");
      return;
    }
    await runAction("save-recipient", async () => {
      await platformApi("/reports/recipients", {
        method: "PUT",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          email: recipientEmail.trim(),
          display_name: recipientName.trim() || null,
          recipient_role: "owner",
          enabled: true,
        }),
      });
      await loadRecipients(selectedCampaignId);
      setNotice("Recipient saved for this business.");
    });
  }

  async function toggleRecipient(recipient: ReportRecipient) {
    await runAction(`recipient-${recipient.id}`, async () => {
      await platformApi(`/reports/recipients/${recipient.id}?enabled=${!recipient.enabled}`, {
        method: "PATCH",
      });
      await loadRecipients(selectedCampaignId);
      setNotice(recipient.enabled ? "Recipient paused." : "Recipient turned back on.");
    });
  }

  async function createShareLink() {
    const reportId = selectedReportDetail?.report.id || selectedReportId;
    if (!reportId) {
      setError("Select a report first.");
      return;
    }
    await runAction("share-link", async () => {
      const created = (await platformApi(`/reports/${reportId}/share-links`, {
        method: "POST",
        body: JSON.stringify({ expires_in_hours: 168 }),
      })) as ReportShareLink;
      setNewShareUrl(created.share_url || "");
      await loadReportDetail(reportId);
      setNotice("A private link was created. It will turn off automatically in 7 days.");
    });
  }

  async function revokeShareLink(linkId: string) {
    const reportId = selectedReportDetail?.report.id || selectedReportId;
    await runAction(`revoke-${linkId}`, async () => {
      await platformApi(`/reports/share-links/${linkId}`, { method: "DELETE" });
      if (reportId) {
        await loadReportDetail(reportId);
      }
      setNotice("The private report link was turned off.");
    });
  }

  async function copyShareLink() {
    if (!newShareUrl) return;
    await navigator.clipboard.writeText(newShareUrl);
    setNotice("Private report link copied.");
  }

  async function regenerateReportFiles() {
    const reportId = selectedReportDetail?.report.id || selectedReportId;
    if (!reportId) {
      setError("Select a report first.");
      return;
    }

    await runAction("regenerate", async () => {
      await platformApi(`/reports/${reportId}/regenerate`, { method: "POST" });
      await loadReportDetail(reportId);
      setNotice("The report files were rebuilt from the same saved facts. The numbers and location were not changed.");
    });
  }

  async function openReportArtifact(artifact: ReportArtifact) {
    const reportId = selectedReportDetail?.report.id || selectedReportId;
    if (!reportId) {
      setError("Select a report first.");
      return;
    }

    const opensInBrowser = artifact.artifact_type !== "pdf";
    const reportWindow = opensInBrowser ? window.open("about:blank", "_blank") : null;
    if (reportWindow) {
      reportWindow.opener = null;
      reportWindow.document.title = "Opening your report";
      reportWindow.document.body.textContent = "Opening your report...";
    }

    let fileOpened = false;
    await runAction(
      `artifact-${artifact.id}`,
      async () => {
        try {
          const file = await platformApiFile(
            `/reports/${reportId}/artifacts/${artifact.id}`,
            { method: "GET" },
          );
          const fileUrl = URL.createObjectURL(file.blob);
          const extension = artifact.artifact_type === "pdf" ? "pdf" : "html";
          const filename = `insightos-report-month-${coerceNumber(selectedReportDetail?.report.month_number, 1)}.${extension}`;

          if (opensInBrowser) {
            if (reportWindow) {
              reportWindow.location.replace(fileUrl);
            } else {
              window.location.assign(fileUrl);
            }
          } else {
            const link = document.createElement("a");
            link.href = fileUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
          }

          fileOpened = true;
          window.setTimeout(() => URL.revokeObjectURL(fileUrl), 60_000);
          setNotice(
            opensInBrowser
              ? "The report opened in a new tab."
              : "The PDF report was downloaded.",
          );
        } finally {
          if (!fileOpened) {
            reportWindow?.close();
          }
        }
      },
      "We could not open this report file. Your saved report is still safe. Please try again.",
    );
  }

  async function downloadPortfolioReport() {
    if (!portfolioComparison?.comparison_ready) {
      setError("Create reports with matching dates for at least two locations first.");
      return;
    }

    await runAction(
      "portfolio-pdf",
      async () => {
        const file = await platformApiFile("/reports/portfolio-artifact", { method: "GET" });
        const fileUrl = URL.createObjectURL(file.blob);
        const link = document.createElement("a");
        link.href = fileUrl;
        link.download = "insightos-all-location-report.pdf";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(fileUrl), 60_000);
        setNotice("The all-location PDF was downloaded from the same saved reports shown here.");
      },
      "We could not download the all-location report right now. Your saved reports are still safe.",
    );
  }

  async function saveSchedule() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }

    await runAction("save-schedule", async () => {
      let nextRunIso: string | undefined;
      if (scheduleNextRun) {
        nextRunIso = new Date(scheduleNextRun).toISOString();
      }

      await platformApi("/reports/schedule", {
        method: "PUT",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          cadence: scheduleCadence,
          timezone: scheduleTimezone,
          next_run_at: nextRunIso,
          enabled: scheduleEnabled,
        }),
      });

      await loadSchedule(selectedCampaignId);
      setNotice(
        "Report schedule saved. Confirm below whether it is active, paused, retrying, or needs attention.",
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
          const [reportResult] = await Promise.allSettled([
            loadReports(items[0].id),
            loadSchedule(items[0].id),
            loadRecipients(items[0].id),
            loadReportReadiness(items[0].id),
            loadPortfolioComparison(),
          ]);
          if (reportResult.status === "rejected") {
            throw reportResult.reason;
          }
        }
      } catch (err) {
        setError(
          friendlyReportError(
            err,
            "Reports could not be loaded right now. Your other business data is still available.",
          ),
        );
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns, loadPortfolioComparison, loadRecipients, loadReportReadiness, loadReports, loadSchedule]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void Promise.allSettled([
      loadReports(selectedCampaignId),
      loadSchedule(selectedCampaignId),
      loadRecipients(selectedCampaignId),
      loadReportReadiness(selectedCampaignId),
    ]).then(([reportResult]) => {
      if (reportResult.status === "rejected") {
        setError(
          friendlyReportError(
            reportResult.reason,
            "Reports could not be loaded right now. Your other business data is still available.",
          ),
        );
      }
    });
  }, [loadRecipients, loadReportReadiness, loadReports, loadSchedule, selectedCampaignId, loading]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const latestReport = reports[0] ?? null;
  const deliveredCount = reports.filter((item) => item.report_status === "delivered").length;
  const generatedCount = reports.filter((item) => item.report_status === "generated").length;
  const readinessSources = (reportReadiness?.sources || []).filter(
    (item) => item.state !== "ready" || reportReadiness?.status === "ready",
  );
  const previewSections = useMemo(
    () => buildReportSections(selectedReportDetail?.report || latestReport || undefined, selectedReportDetail?.snapshot),
    [latestReport, selectedReportDetail],
  );
  const reportWorkflow = useMemo(
    () => getReportWorkflowState(latestReport, selectedCampaign, selectedReportDetail?.truth || reportsTruth),
    [latestReport, reportsTruth, selectedCampaign, selectedReportDetail?.truth],
  );
  const deliveryWorkflow = useMemo(
    () => getDeliveryWorkflowState(selectedReportDetail, selectedReportDetail?.report || latestReport, selectedReportDetail?.truth || reportsTruth),
    [latestReport, reportsTruth, selectedReportDetail],
  );
  const scheduleWorkflow = useMemo(
    () => getScheduleWorkflowState(schedule, selectedCampaign, formatRelativeTime, schedule?.truth),
    [schedule, selectedCampaign],
  );

  const summary = useMemo(() => {
    if (!selectedCampaign) {
      return {
        title: "No business is selected yet",
        body: "Set up a business first so reports can package your visibility results.",
        next: "Go back to the dashboard to finish setup and start your first scan.",
      };
    }

    if (!latestReport) {
      return {
        title: `${selectedCampaign.name || "This business"} has no reports yet`,
        body: "Generate a first report once your latest scan and ranking data are ready.",
        next: "Create the first report, review it, then send it to the right recipient.",
      };
    }

    if (isFailedStatus(latestReport.report_status)) {
      return {
        title: "Your latest report needs attention",
        body: `Month ${latestReport.month_number} is currently ${toTitleCase(latestReport.report_status)} and should not be treated as ready to send.`,
        next: "Regenerate the report after confirming the latest checks are complete.",
      };
    }

    if (isPendingStatus(latestReport.report_status)) {
      return {
        title: "Your latest report is still processing",
        body: `Month ${latestReport.month_number} exists, but it is still ${toTitleCase(latestReport.report_status)}.`,
        next: "Wait for generation to finish, then review the preview before sending it.",
      };
    }

    if (latestReport.report_status === "generated") {
      return {
        title: hasTruthState(selectedReportDetail?.truth || reportsTruth, "minimal_artifact")
          ? "Your latest report is a local preview artifact"
          : "Your latest report is ready to review",
        body: hasTruthState(selectedReportDetail?.truth || reportsTruth, "minimal_artifact")
          ? `Month ${latestReport.month_number} was generated ${formatRelativeTime(latestReport.generated_at)} as a minimal local artifact.`
          : `Month ${latestReport.month_number} was generated ${formatRelativeTime(latestReport.generated_at)}.`,
        next: hasTruthState(selectedReportDetail?.truth || reportsTruth, "minimal_artifact")
          ? "Review the preview first. Generated does not mean premium, durable, or already delivered."
          : "Review the preview, confirm the recipient, and send the report while the update is still fresh.",
      };
    }

    if (latestReport.report_status === "delivered" && hasTruthState(selectedReportDetail?.truth || reportsTruth, "delivery_unverified")) {
      return {
        title: "Your latest report is marked delivered, not externally verified",
        body: `Month ${latestReport.month_number} has a delivered record, but this runtime does not verify real inbox delivery.`,
        next: "Use the delivery history and external confirmation before treating this as a completed client send.",
      };
    }

    return {
      title: "Your latest report has been completed",
      body: `Month ${latestReport.month_number} is marked ${toTitleCase(latestReport.report_status)}.`,
      next: latestReport.report_status === "delivered"
        ? "Generate the next report when you want to package a new round of ranking and website updates."
        : "Review the delivery history below before deciding whether to resend or generate a new report.",
    };
  }, [latestReport, reportsTruth, selectedCampaign, selectedReportDetail?.truth]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Report status",
        selectedReportDetail?.truth || reportsTruth,
        "Reports can exist before deliverability or durable storage are truly confirmed.",
      ),
      {
        label: "Reports",
        value: reports.length > 0 ? `${reports.length} created` : "None yet",
        tone: reports.length > 0 ? "success" : "warning",
      },
      {
        label: "Ready to send",
        value: generatedCount > 0
          ? hasTruthState(selectedReportDetail?.truth || reportsTruth, "minimal_artifact")
            ? `${generatedCount} preview-only`
            : `${generatedCount} ready`
          : "Nothing ready",
        tone: generatedCount > 0 ? "info" : "warning",
      },
      {
        label: "Delivered",
        value: deliveredCount > 0
          ? hasTruthState(selectedReportDetail?.truth || reportsTruth, "delivery_unverified")
            ? `${deliveredCount} marked sent`
            : `${deliveredCount} sent`
          : "Nothing sent yet",
        tone: deliveredCount > 0 && !hasTruthState(selectedReportDetail?.truth || reportsTruth, "delivery_unverified") ? "success" : "warning",
      },
      {
        label: "Latest update",
        value: latestReport?.generated_at
          ? formatRelativeTime(latestReport.generated_at)
          : "Awaiting first report",
        tone: latestReport ? "info" : "warning",
      },
    ],
    [deliveredCount, generatedCount, latestReport, reports.length, reportsTruth, selectedReportDetail?.truth],
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
      dateRangeLabel="Saved report history"
      topBarActions={
        <>
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
          compact
          eyebrow="Reports"
          title="Create a clear update you can share"
          summary="Bring the latest website and search results into one report, review it, and confirm whether it was actually sent."
        />

        <TruthNotice title="Review a report before sharing it.">
          A report that is still being created is not ready to send. Check the report status and
          delivery history before treating it as complete.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading reports"
            summary="Pulling report history, the latest preview, and delivery status for the active business."
          />
        ) : null}

        {error ? (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-md border border-rose-200/20 bg-black/20 px-3 py-1.5 font-semibold text-white"
            >
              Try again
            </button>
          </section>
        ) : null}

        {notice ? (
          <section className="rounded-md border border-accent-500/20 bg-accent-500/10 p-4 text-sm text-zinc-100">
            {notice}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="No business is ready for reports yet"
            summary="Set up a business first so InsightOS can collect enough data to generate a report."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <OwnerDecisionPanel
              eyebrow="Report status"
              title={summary.title}
              summary={summary.body}
              nextStep={summary.next}
              actionLabel={generatedCount > 0 ? "Review the report" : "Create a report"}
              onAction={() =>
                document.getElementById("report-actions")?.scrollIntoView({ behavior: "smooth" })
              }
              tone={
                latestReport && isFailedStatus(latestReport.report_status)
                  ? "urgent"
                  : generatedCount > 0
                    ? "warning"
                    : deliveredCount > 0
                      ? "positive"
                      : "neutral"
              }
              progress={
                reports.length > 0
                  ? {
                      label: "Reports confirmed as delivered",
                      value: deliveredCount,
                      total: reports.length,
                      summary: "A created report is not counted as delivered until its delivery status confirms it.",
                    }
                  : undefined
              }
            />

            {campaigns.length > 1 && portfolioComparison ? (
              <section className="overflow-hidden rounded-md border border-[#2c2d32] bg-[#121316] shadow-[0_0_30px_rgba(0,0,0,0.28)]">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#2c2d32] p-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      All locations
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Compare location reports
                    </h2>
                    <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                      See each location side by side using the facts saved in its latest report. Numbers are never blended across locations.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-3">
                    <div className="text-right">
                      <p className="text-2xl font-semibold text-white">
                        {portfolioComparison.comparable_location_count} of {portfolioComparison.location_count}
                      </p>
                      <p className="text-xs text-zinc-400">locations ready to compare</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void downloadPortfolioReport()}
                      disabled={busyAction !== "" || !portfolioComparison.comparison_ready}
                      title={
                        portfolioComparison.comparison_ready
                          ? "Download one PDF using the saved reports shown below"
                          : "Create reports with matching dates for at least two locations first"
                      }
                      className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "portfolio-pdf" ? "Preparing PDF..." : "Download all-location PDF"}
                    </button>
                  </div>
                </div>

                {portfolioComparison.warnings.length ? (
                  <div className="border-b border-amber-500/20 bg-amber-500/5 px-4 py-3">
                    {portfolioComparison.warnings.map((warning) => (
                      <p key={warning} className="text-sm leading-6 text-amber-100">
                        {warning}
                      </p>
                    ))}
                  </div>
                ) : null}

                {portfolioComparison.focus ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2c2d32] bg-accent-500/5 px-4 py-3">
                    <p className="text-sm text-zinc-200">
                      <span className="font-semibold text-white">Start with {portfolioComparison.focus.location_name}.</span>{" "}
                      {portfolioComparison.focus.reason}
                    </p>
                    <button
                      type="button"
                      onClick={() => setSelectedCampaignId(portfolioComparison.focus?.campaign_id || "")}
                      className="text-sm font-semibold text-accent-300 hover:text-accent-200"
                    >
                      Open this location
                    </button>
                  </div>
                ) : null}

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[940px] border-collapse text-left">
                    <thead className="bg-black/20 text-[11px] uppercase tracking-[0.16em] text-zinc-500">
                      <tr>
                        <th className="px-4 py-3 font-semibold">Location</th>
                        <th className="px-4 py-3 font-semibold">Visits from Google</th>
                        <th className="px-4 py-3 font-semibold">Times shown</th>
                        <th className="px-4 py-3 font-semibold">Google position</th>
                        <th className="px-4 py-3 font-semibold">Tracked position</th>
                        <th className="px-4 py-3 font-semibold">Latest report</th>
                      </tr>
                    </thead>
                    <tbody>
                      {portfolioComparison.locations.map((location) => {
                        const visibleMetrics = new Map<string, ReportMetric>(
                          location.metrics
                            .filter((metric) => PORTFOLIO_VISIBLE_METRIC_KEYS.has(metric.key))
                            .map((metric) => [metric.key, metric] as const),
                        );
                        const metricKeys = [
                          "google_visits",
                          "google_appearances",
                          "average_google_position",
                          "tracked_keyword_position",
                        ];
                        return (
                          <tr key={location.campaign_id} className="border-t border-[#26272c] align-top first:border-t-0">
                            <td className="px-4 py-4">
                              <button
                                type="button"
                                onClick={() => setSelectedCampaignId(location.campaign_id)}
                                className="text-left text-sm font-semibold text-white hover:text-accent-200"
                              >
                                {location.location_name}
                              </button>
                              <p className="mt-1 max-w-[220px] truncate text-xs text-zinc-500">{location.domain || "No website saved"}</p>
                              <p className="mt-2 text-xs text-zinc-400">{portfolioPeriodLabel(location)}</p>
                            </td>
                            {metricKeys.map((metricKey) => {
                              const metric = visibleMetrics.get(metricKey);
                              return (
                                <td key={metricKey} className="px-4 py-4">
                                  <p className="text-base font-semibold text-white">
                                    {metric ? formatMetricValue(metric) : "Not measured"}
                                  </p>
                                  <p className={`mt-1 text-xs ${metric ? portfolioMetricTone(metric) : "text-zinc-500"}`}>
                                    {metric ? portfolioMetricChangeLabel(metric) : "No saved value"}
                                  </p>
                                </td>
                              );
                            })}
                            <td className="px-4 py-4">
                              <p className={`text-sm font-semibold ${location.comparison_state === "ready" ? "text-emerald-300" : "text-amber-300"}`}>
                                {portfolioStateLabel(location.comparison_state)}
                              </p>
                              {location.report ? (
                                <p className="mt-1 text-xs text-zinc-400">
                                  Month {location.report.month_number} · {location.wins_count} wins · {location.risks_count} to watch
                                </p>
                              ) : null}
                              <p className="mt-2 max-w-[220px] text-xs leading-5 text-zinc-500">
                                {location.comparison_message}
                              </p>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <p className="border-t border-[#2c2d32] px-4 py-3 text-xs leading-5 text-zinc-500">
                  A direct comparison is only made when at least two locations use the same report dates. Open a location to review its full evidence and next steps.
                </p>
              </section>
            ) : null}

            {reportReadiness ? (
              <section
                className={`rounded-md border p-4 shadow-[0_0_30px_rgba(0,0,0,0.25)] ${
                  reportReadiness.status === "ready"
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : reportReadiness.status === "limited"
                      ? "border-amber-500/30 bg-amber-500/5"
                      : "border-rose-500/30 bg-rose-500/5"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Before you create the next report
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      {reportReadiness.title}
                    </h2>
                    <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                      {reportReadiness.summary}
                    </p>
                  </div>
                  <span className="rounded-md border border-white/10 bg-black/20 px-2.5 py-1 text-xs font-semibold text-zinc-100">
                    {reportReadiness.status === "ready"
                      ? "Ready"
                      : `${reportReadiness.warning_count} item${reportReadiness.warning_count === 1 ? "" : "s"} to improve`}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
                  {readinessSources.map((source) => (
                    <div key={source.key} className="rounded-md border border-white/10 bg-black/20 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-white">{source.label}</h3>
                        <span
                          className={`text-xs font-semibold ${
                            source.state === "ready"
                              ? "text-emerald-300"
                              : source.state === "optional"
                                ? "text-zinc-400"
                                : "text-amber-300"
                          }`}
                        >
                          {source.state === "ready"
                            ? "Ready"
                            : source.state === "optional"
                              ? "Optional"
                              : source.state === "stale"
                                ? "Needs refresh"
                                : source.state === "partial"
                                  ? "Limited"
                                  : "Not ready"}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-zinc-300">{source.detail}</p>
                      {source.state !== "ready" && source.state !== "optional" && source.action_href ? (
                        <button
                          type="button"
                          onClick={() => router.push(source.action_href || "/settings")}
                          className="mt-3 text-xs font-semibold text-accent-300 hover:text-accent-200"
                        >
                          {source.action_label || "Fix this"} →
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            <details className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.3)]">
              <summary className="cursor-pointer list-none">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  Report progress
                </p>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <h2 className="text-base font-semibold text-white">
                    {reportWorkflow.status}
                  </h2>
                  <span className="text-xs text-zinc-400">See delivery details</span>
                </div>
              </summary>
              <p className="mt-4 border-t border-[#26272c] pt-4 text-sm leading-6 text-zinc-300">
                See what is ready, what is still processing, and what needs your attention.
              </p>
              <div className="mt-4 grid gap-4 xl:grid-cols-3">
                {[reportWorkflow, deliveryWorkflow, scheduleWorkflow].map((state) => (
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
            </details>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Reports created"
                value={String(reports.length)}
                summary="Reports saved for this business."
              />
              <KpiCard
                label="Ready to send"
                value={String(generatedCount)}
                summary="Reports that are prepared and waiting for your review."
                tone="highlight"
              />
              <KpiCard
                label="Delivered"
                value={String(deliveredCount)}
                summary="Reports marked as sent. Open delivery details when confirmation matters."
              />
              <KpiCard
                label="Latest report"
                value={latestReport ? `M${latestReport.month_number}` : "None"}
                changeLabel={latestReport ? toTitleCase(latestReport.report_status) : undefined}
                summary={
                  latestReport
                    ? latestReport.report_status === "generated"
                      ? "Latest report is ready to review and send."
                      : isFailedStatus(latestReport.report_status)
                        ? `Latest report needs attention after a ${toTitleCase(latestReport.report_status)} result.`
                        : isPendingStatus(latestReport.report_status)
                          ? `Latest report is ${toTitleCase(latestReport.report_status)} and still processing.`
                          : `Latest report was updated ${formatRelativeTime(latestReport.generated_at)}.`
                    : "Generate your first report once the business has enough data."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <section
                id="report-actions"
                className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]"
              >
                <div className="mb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Actions
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    Create or send a report
                  </h2>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                    Generate a fresh report for the current business, then send the selected report by email after it is clearly ready.
                  </p>
                </div>

                <div className="space-y-4">
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                      Report period
                    </label>
                    <input
                      value={monthNumber}
                      onChange={(event) => setMonthNumber(event.target.value)}
                      className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                    />
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Use this when you want to package the next reporting cycle for the active business. A report request is not complete until the workflow status above says it is ready or complete.
                    </p>
                    <button
                      onClick={generateReport}
                      disabled={busyAction !== "" || !selectedCampaignId}
                      className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "generate"
                        ? "Generating..."
                        : reportReadiness?.status === "ready"
                          ? "Generate detailed report"
                          : "Generate report with available data"}
                    </button>
                    {selectedReportDetail?.snapshot?.snapshot_hash ? (
                      <div className="mt-4 border-t border-[#26272c] pt-4">
                        <p className="text-xs leading-5 text-zinc-400">
                          Need a fresh copy of the selected files? Rebuild them from the same saved facts without changing the report numbers.
                        </p>
                        <button
                          onClick={regenerateReportFiles}
                          disabled={busyAction !== ""}
                          className="mt-3 rounded-md border border-[#26272c] bg-[#0b0b0c] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {busyAction === "regenerate" ? "Rebuilding..." : "Rebuild selected report files"}
                        </button>
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Who receives it</p>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <input
                        value={recipientName}
                        onChange={(event) => setRecipientName(event.target.value)}
                        placeholder="Name (optional)"
                        className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                      />
                      <input
                        value={recipientEmail}
                        onChange={(event) => setRecipientEmail(event.target.value)}
                        placeholder="name@example.com"
                        className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                      />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Save people you report to, then choose one before sending. Each business keeps its own list.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={saveRecipient}
                        disabled={busyAction !== "" || !recipientEmail.trim()}
                        className="rounded-md border border-[#26272c] bg-[#0b0b0c] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busyAction === "save-recipient" ? "Saving..." : "Save recipient"}
                      </button>
                      <button
                        onClick={deliverReport}
                        disabled={busyAction !== "" || !selectedReportId || !recipientEmail.trim()}
                        className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busyAction === "deliver" ? "Sending..." : "Send selected report"}
                      </button>
                    </div>
                    {recipients.length ? (
                      <div className="mt-4 space-y-2 border-t border-[#26272c] pt-4">
                        {recipients.map((recipient) => (
                          <div key={recipient.id} className="flex items-center justify-between gap-3 rounded-md border border-[#26272c] bg-[#0b0b0c] p-3">
                            <button
                              onClick={() => {
                                setRecipientEmail(recipient.email);
                                setRecipientName(recipient.display_name || "");
                              }}
                              className="min-w-0 text-left"
                            >
                              <p className="truncate text-sm font-medium text-white">{recipient.display_name || recipient.email}</p>
                              {recipient.display_name ? <p className="truncate text-xs text-zinc-400">{recipient.email}</p> : null}
                            </button>
                            <button
                              onClick={() => toggleRecipient(recipient)}
                              disabled={busyAction !== ""}
                              className="shrink-0 text-xs font-medium text-zinc-400 hover:text-white disabled:opacity-50"
                            >
                              {recipient.enabled ? "Pause" : "Turn on"}
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              </section>

              <ReportPreview
                title={
                  selectedReportDetail?.snapshot?.executive_summary?.headline
                    ? selectedReportDetail.snapshot.executive_summary.headline
                    : selectedReportDetail?.report
                    ? `Month ${selectedReportDetail.report.month_number} report`
                    : "Report preview"
                }
                audienceLabel={
                  selectedReportDetail?.snapshot
                    ? `${toTitleCase(selectedReportDetail.snapshot.audience || "owner")} report · ${toTitleCase(selectedReportDetail.snapshot.source?.freshness_state || "unknown data")}`
                    : selectedReportDetail?.report
                    ? toTitleCase(selectedReportDetail.report.report_status)
                    : "Awaiting report"
                }
                summary={
                  selectedReportDetail?.snapshot?.executive_summary?.summary
                    ? selectedReportDetail.snapshot.executive_summary.summary
                    : selectedReportDetail?.report
                    ? reportPurpose(selectedReportDetail.report)
                    : "Generate a report to see a preview of what will be packaged and sent."
                }
                sections={previewSections}
              />
            </div>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="mb-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  History
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Available reports
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Select a report to review its purpose, open its files, and decide whether it is ready to share.
                </p>
              </div>

              {reports.length === 0 ? (
                <EmptyState
                  title="No reports have been generated yet"
                  summary="Create the first report for this business to start a report history."
                  actionLabel="Generate first report"
                  onAction={() => void generateReport()}
                />
              ) : (
                <div className="space-y-3">
                  {reports.map((report) => {
                    const summaryData = parseSummary(report.summary_json);
                    const isSelected = report.id === selectedReportId;

                    return (
                      <button
                        key={report.id}
                        onClick={() => {
                          setSelectedReportId(report.id);
                          setNewShareUrl("");
                          void loadReportDetail(report.id);
                        }}
                        className={`w-full rounded-md border p-4 text-left shadow-[0_0_30px_rgba(0,0,0,0.4)] transition ${
                          isSelected
                            ? "border-accent-500/30 bg-accent-500/10"
                            : "border-[#26272c] bg-[#111214]"
                        }`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-base font-semibold text-white">
                              Month {report.month_number} report
                            </p>
                            <p className="mt-1 text-sm leading-6 text-zinc-300">
                              {reportPurpose(report)}
                            </p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              {report.report_status === "delivered"
                                ? "Complete. This report has been shared."
                                : report.report_status === "generated"
                                  ? "Generated. Review the local preview before treating it as client-ready."
                                  : isFailedStatus(report.report_status)
                                    ? "Needs attention. Do not treat this as ready yet."
                                    : isPendingStatus(report.report_status)
                                      ? "In progress. This report record exists, but processing is not finished."
                                      : "Review this state before taking the next step."}
                            </p>
                          </div>
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${statusTone(report.report_status)}`}
                          >
                            {toTitleCase(report.report_status)}
                          </span>
                        </div>
                        <div className="mt-3 grid gap-3 text-sm text-zinc-300 md:grid-cols-4">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Created
                            </p>
                            <p className="mt-1">{formatRelativeTime(report.generated_at)}</p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Rank snapshots
                            </p>
                            <p className="mt-1">{coerceNumber(summaryData?.rank_snapshots)}</p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Technical issues
                            </p>
                            <p className="mt-1">{coerceNumber(summaryData?.technical_issues)}</p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Review activity
                            </p>
                            <p className="mt-1">{coerceNumber(summaryData?.reviews_last_30d)} reviews</p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </section>

            {selectedReportDetail?.artifacts?.length ? (
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Artifacts
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Files created for the selected report
                </h2>
                <div className="mt-4 space-y-3">
                  {selectedReportDetail.artifacts.map((artifact) => (
                    <div
                      key={artifact.id}
                      className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-white">
                            {toTitleCase(artifact.artifact_type)} report
                          </p>
                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                            {artifact.ready
                              ? artifact.durable
                                ? "Saved privately and ready to open."
                                : "Ready to open. Production storage still needs to be connected."
                              : "This file is not available yet. Rebuild the report files and try again."}
                          </p>
                          <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                            {artifact.byte_size ? `${Math.max(1, Math.round(artifact.byte_size / 1024))} KB · ` : ""}
                            {artifact.durable ? "Private cloud storage" : "Development storage"}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                            {formatRelativeTime(artifact.created_at)}
                          </span>
                          {artifact.retrievable ? (
                            <button
                              type="button"
                              onClick={() => openReportArtifact(artifact)}
                              disabled={busyAction !== ""}
                              className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-xs font-medium text-zinc-100"
                            >
                              {busyAction === `artifact-${artifact.id}`
                                ? "Opening..."
                                : artifact.artifact_type === "pdf"
                                  ? "Download"
                                  : "Open"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {selectedReportDetail ? (
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Private sharing
                </p>
                <div className="mt-1.5 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">Share without emailing a file</h2>
                    <p className="mt-1.5 max-w-2xl text-sm leading-6 text-zinc-300">
                      Create a private link for this report. The link turns off after 7 days, and you can turn it off sooner at any time.
                    </p>
                  </div>
                  <button
                    onClick={createShareLink}
                    disabled={busyAction !== "" || !selectedReportDetail.artifacts.some((artifact) => artifact.retrievable)}
                    className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "share-link" ? "Creating..." : "Create 7-day link"}
                  </button>
                </div>

                {newShareUrl ? (
                  <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4">
                    <p className="text-sm font-medium text-emerald-100">Copy this link now</p>
                    <p className="mt-1 break-all text-sm leading-6 text-zinc-200">{newShareUrl}</p>
                    <button onClick={copyShareLink} className="mt-3 rounded-md border border-emerald-500/30 px-3 py-1.5 text-xs font-medium text-emerald-100">
                      Copy link
                    </button>
                  </div>
                ) : null}

                {shareLinks.length ? (
                  <div className="mt-4 space-y-2">
                    {shareLinks.map((link) => (
                      <div key={link.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#26272c] bg-[#111214] p-3">
                        <div>
                          <p className="text-sm font-medium text-white">{link.status === "active" ? "Active private link" : toTitleCase(link.status)}</p>
                          <p className="mt-1 text-xs text-zinc-400">
                            {link.status === "active" ? `Turns off ${formatRelativeTime(link.expires_at)}` : "This link can no longer open the report"}
                            {link.open_count ? ` · Opened ${link.open_count} ${link.open_count === 1 ? "time" : "times"}` : " · Not opened yet"}
                          </p>
                        </div>
                        {link.status === "active" ? (
                          <button
                            onClick={() => revokeShareLink(link.id)}
                            disabled={busyAction !== ""}
                            className="text-xs font-medium text-rose-300 hover:text-rose-200 disabled:opacity-50"
                          >
                            Turn off link
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}

            {selectedReportDetail ? (
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Delivery
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Delivery history
                </h2>

                {!selectedReportDetail.delivery_events?.length ? (
                  <div className="mt-3 rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm leading-6 text-zinc-400">
                      {selectedReportDetail.report.report_status === "delivered"
                        ? "This report is marked as delivered, but there is no event-level delivery confirmation available here."
                        : "This report has not been sent yet. Add a recipient above and send it only after confirming it is ready."}
                    </p>
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {selectedReportDetail.delivery_events.map((event) => (
                      <div
                        key={event.id}
                        className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-white">{event.recipient}</p>
                            <p className="mt-1 text-sm leading-6 text-zinc-300">
                              {toTitleCase(event.delivery_channel)}
                              {event.sent_at
                                ? ` · ${formatRelativeTime(event.sent_at)}`
                                : event.delivery_status === "failed"
                                  ? " · Delivery was not completed"
                                  : isPendingStatus(event.delivery_status)
                                    ? " · Delivery is still being processed"
                                  : ""}
                            </p>
                            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                              {event.delivery_status === "sent"
                                ? hasTruthState(selectedReportDetail.truth, "delivery_unverified")
                                  ? "Marked sent. Confirm receipt outside the product before treating it as delivered."
                                  : "Complete. The report reached this recipient."
                                : event.delivery_status === "failed"
                                  ? "Needs attention. Retry after confirming the recipient."
                                  : isPendingStatus(event.delivery_status)
                                    ? "In progress. Do not treat this report as delivered yet."
                                    : "Review this delivery state before resending."}
                            </p>
                          </div>
                          <span
                            className={`shrink-0 rounded-md border px-2 py-1 text-xs font-medium ${getDeliveryStatusTone(event.delivery_status)}`}
                          >
                            {getDeliveryStatusLabel(event.delivery_status)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Automation
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    Report schedule
                  </h2>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                    {schedule
                      ? "Adjust the cadence, timezone, and next run time for automatic report generation. Use the workflow status above to confirm whether automation is active, retrying, paused, or needs attention."
                      : "No schedule has been set up yet. Configure one below if you want automatic report generation."}
                  </p>
                </div>
                {schedule ? (
                  <span
                    className={`rounded-md border px-2.5 py-1 text-xs font-medium ${getScheduleStatusTone(schedule.last_status)}`}
                  >
                    {getScheduleStatusLabel(schedule.last_status)}
                  </span>
                ) : null}
              </div>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Enabled
                  </label>
                  <select
                    value={scheduleEnabled ? "true" : "false"}
                    onChange={(event) => setScheduleEnabled(event.target.value === "true")}
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                  >
                    <option value="true">Yes — run automatically</option>
                    <option value="false">No — paused</option>
                  </select>
                </div>

                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Cadence
                  </label>
                  <select
                    value={scheduleCadence}
                    onChange={(event) => setScheduleCadence(event.target.value)}
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </div>

                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Timezone
                  </label>
                  <select
                    value={scheduleTimezone}
                    onChange={(event) => setScheduleTimezone(event.target.value)}
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                  >
                    {SCHEDULE_TIMEZONES.map((tz) => (
                      <option key={tz} value={tz}>
                        {tz.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Next run
                  </label>
                  <input
                    type="datetime-local"
                    value={scheduleNextRun}
                    onChange={(event) => setScheduleNextRun(event.target.value)}
                    className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
                  />
                </div>
              </div>

              {schedule ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Retry count
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {schedule.retry_count === 0
                        ? "No retries recorded."
                        : `${schedule.retry_count} ${schedule.retry_count === 1 ? "retry" : "retries"} have been attempted.`}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Scheduler status
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {getScheduleStatusLabel(schedule.last_status)}
                    </p>
                  </div>
                </div>
              ) : null}

              <div className="mt-5">
                <button
                  onClick={() => void saveSchedule()}
                  disabled={busyAction !== "" || !selectedCampaignId}
                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "save-schedule" ? "Saving..." : schedule ? "Update schedule" : "Create schedule"}
                </button>
              </div>
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
