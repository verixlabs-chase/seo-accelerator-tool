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
  TruthNotice,
  type ReportSection,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  buildRuntimeTruthSignal,
  getRuntimeTruthSummary,
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
  created_at?: string;
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
  truth?: RuntimeTruth;
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
  const [reportsTruth, setReportsTruth] = useState<RuntimeTruth | null>(null);
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
    setReportsTruth((response?.truth as RuntimeTruth) || null);
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
      setNotice(
        `Report request completed for month ${safeMonth}. Confirm below whether it is ready to send, still processing, or needs attention.`,
      );
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
      setNotice(
        "Report delivery was requested. Confirm below whether it was sent, is still queued, or needs attention.",
      );
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
        "Runtime truth",
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
      dateRangeLabel="Stored report data"
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
          eyebrow="Reports"
          title="Package results into something you can send"
          summary="Use the Reports Center to assemble a stored summary of the latest scan and ranking results, review the local artifacts, and track whether delivery was only requested or actually confirmed."
        />

        <TruthNotice title="A report record is not the same as a client-ready deliverable.">
          Generated reports still need review, pending reports are still assembling, and delivery
          history is the only evidence that a report was actually sent. Use the workflow cards
          below before treating any report as complete or shareable.
        </TruthNotice>

        {selectedReportDetail?.truth || reportsTruth ? (
          <TruthNotice title="Current runtime truth" tone="warning">
            {getRuntimeTruthSummary(
              selectedReportDetail?.truth || reportsTruth,
              "Report runtime status is not available yet.",
            )}
          </TruthNotice>
        ) : null}

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

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Workflow status
              </p>
              <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                Exactly where report work stands
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                These cards translate raw report, delivery, and automation state into user meaning: what is complete, what is still processing, what failed, and what to do next.
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
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Reports created"
                value={String(reports.length)}
                summary="These are stored report records generated for the active business."
              />
              <KpiCard
                label="Ready to send"
                value={String(generatedCount)}
                summary="These reports are generated records. They may still be minimal local artifacts that need review before sending."
                tone="highlight"
              />
              <KpiCard
                label="Delivered"
                value={String(deliveredCount)}
                summary="These reports are marked as delivered in the app. Check delivery history and external confirmation before treating them as verified inbox delivery."
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
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
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
                      Send the selected report only after the workflow status above shows it is ready and you confirm the recipient is correct.
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
                  Select a report to review its purpose, inspect the local artifacts, and decide whether it is safe enough to send.
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
                            {toTitleCase(artifact.artifact_type)} artifact
                          </p>
                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                            {artifact.storage_path || "No storage path available."}
                          </p>
                          <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
                            Local artifact only. This file is not remotely retrievable or durable in the current runtime.
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
