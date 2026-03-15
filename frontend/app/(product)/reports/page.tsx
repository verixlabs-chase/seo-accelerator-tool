"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  ReportPreview,
  type ReportSection,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

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
  created_at?: string;
};

type ReportDetail = {
  report: ReportItem;
  artifacts: ReportArtifact[];
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
    return JSON.parse(summaryJson) as {
      month_number?: number;
      rank_snapshots?: number;
      technical_issues?: number;
      intelligence_score?: number | null;
      reviews_last_30d?: number;
      avg_rating_last_30d?: number | null;
    };
  } catch {
    return null;
  }
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

  return "Use this report to package the latest scan, rankings, and visibility signals into one summary.";
}

function buildReportSections(report?: ReportItem): ReportSection[] {
  const summary = parseSummary(report?.summary_json);

  if (!report || !summary) {
    return [
      {
        title: "No report preview yet",
        summary: "Generate a report to package your latest visibility data into a client-ready summary.",
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
      title: "Technical health",
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
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [selectedReportDetail, setSelectedReportDetail] = useState<ReportDetail | null>(null);
  const [monthNumber, setMonthNumber] = useState("1");
  const [recipientEmail, setRecipientEmail] = useState("");
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
  }, []);

  const loadReportDetail = useCallback(async (reportId: string) => {
    if (!reportId) {
      setSelectedReportDetail(null);
      return;
    }

    const detail = (await platformApi(`/reports/${reportId}`, { method: "GET" })) as ReportDetail;
    setSelectedReportDetail(detail);
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
    const nextSelectedId = items[0]?.id || "";
    setSelectedReportId(nextSelectedId);

    if (nextSelectedId) {
      await loadReportDetail(nextSelectedId);
    } else {
      setSelectedReportDetail(null);
    }
  }, [loadReportDetail]);

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

      await loadReports(selectedCampaignId);
      setNotice(`Report generated for month ${safeMonth}.`);
    });
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
      setNotice("Report sent successfully.");
    });
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
      setNotice("Report schedule saved.");
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
          await loadReports(items[0].id);
          await loadSchedule(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load reports.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns, loadReports, loadSchedule]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void loadReports(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load reports.");
    });
    void loadSchedule(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load schedule.");
    });
  }, [loadReports, loadSchedule, selectedCampaignId, loading]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const latestReport = reports[0] ?? null;
  const deliveredCount = reports.filter((item) => item.report_status === "delivered").length;
  const generatedCount = reports.filter((item) => item.report_status === "generated").length;
  const previewSections = useMemo(
    () => buildReportSections(selectedReportDetail?.report || latestReport || undefined),
    [latestReport, selectedReportDetail],
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

    if (latestReport.report_status === "generated") {
      return {
        title: "Your latest report is ready to send",
        body: `Month ${latestReport.month_number} was generated ${formatRelativeTime(latestReport.generated_at)}.`,
        next: "Review the preview, confirm the recipient, and send the report while the update is still fresh.",
      };
    }

    return {
      title: "Your latest report has already been sent",
      body: `Month ${latestReport.month_number} is marked ${toTitleCase(latestReport.report_status)}.`,
      next: "Generate the next report when you want to package a new round of ranking and website updates.",
    };
  }, [latestReport, selectedCampaign]);

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Reports",
        value: reports.length > 0 ? `${reports.length} created` : "None yet",
        tone: reports.length > 0 ? "success" : "warning",
      },
      {
        label: "Ready to send",
        value: generatedCount > 0 ? `${generatedCount} ready` : "Nothing queued",
        tone: generatedCount > 0 ? "info" : "warning",
      },
      {
        label: "Delivered",
        value: deliveredCount > 0 ? `${deliveredCount} sent` : "Nothing sent yet",
        tone: deliveredCount > 0 ? "success" : "warning",
      },
      {
        label: "Latest update",
        value: latestReport?.generated_at
          ? formatRelativeTime(latestReport.generated_at)
          : "Awaiting first report",
        tone: latestReport ? "info" : "warning",
      },
    ],
    [deliveredCount, generatedCount, latestReport, reports.length],
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
      dateRangeLabel="Live report data"
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
          eyebrow="Reports"
          title="Package results into something you can send"
          summary="Use the Reports Center to create a clear summary of the latest scan and ranking results, then send it to the right person."
        />

        {loading ? (
          <LoadingCard
            title="Loading reports"
            summary="Pulling report history, the latest preview, and delivery status for the active business."
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
            title="No business is ready for reports yet"
            summary="Set up a business first so InsightOS can collect enough data to generate a report."
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
                    What to do next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{summary.next}</p>
                </div>
              </div>
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Reports created"
                value={String(reports.length)}
                summary="These are the reports already generated for the active business."
              />
              <KpiCard
                label="Ready to send"
                value={String(generatedCount)}
                summary="These reports have been generated and can be delivered now."
                tone="highlight"
              />
              <KpiCard
                label="Delivered"
                value={String(deliveredCount)}
                summary="These reports have already been sent to a recipient."
              />
              <KpiCard
                label="Latest report"
                value={latestReport ? `M${latestReport.month_number}` : "None"}
                changeLabel={latestReport ? toTitleCase(latestReport.report_status) : undefined}
                summary={
                  latestReport
                    ? `Latest report was updated ${formatRelativeTime(latestReport.generated_at)}.`
                    : "Generate your first report once the business has enough data."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <div className="mb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Actions
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                    Create or send a report
                  </h2>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                    Generate a fresh report for the current business, then send the selected report by email.
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
                      Use this when you want to package the next reporting cycle for the active business.
                    </p>
                    <button
                      onClick={generateReport}
                      disabled={busyAction !== "" || !selectedCampaignId}
                      className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "generate" ? "Generating..." : "Generate report"}
                    </button>
                  </div>

                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                      Recipient email
                    </label>
                    <input
                      value={recipientEmail}
                      onChange={(event) => setRecipientEmail(event.target.value)}
                      placeholder="name@example.com"
                      className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                    />
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Send the selected report after you review the preview and confirm it is the right update.
                    </p>
                    <button
                      onClick={deliverReport}
                      disabled={busyAction !== "" || !selectedReportId}
                      className="mt-4 rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "deliver" ? "Sending..." : "Send selected report"}
                    </button>
                  </div>
                </div>
              </section>

              <ReportPreview
                title={
                  selectedReportDetail?.report
                    ? `Month ${selectedReportDetail.report.month_number} report`
                    : "Report preview"
                }
                audienceLabel={
                  selectedReportDetail?.report
                    ? toTitleCase(selectedReportDetail.report.report_status)
                    : "Awaiting report"
                }
                summary={
                  selectedReportDetail?.report
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
                  Select a report to review its purpose, see its packaged metrics, and send it if needed.
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
                            {toTitleCase(artifact.artifact_type)} artifact
                          </p>
                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                            {artifact.storage_path || "No storage path available."}
                          </p>
                        </div>
                        <span className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                          {formatRelativeTime(artifact.created_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
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
                      ? "Adjust the cadence, timezone, and next run time for automatic report generation."
                      : "No schedule has been set up yet. Configure one below to automate report generation."}
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
