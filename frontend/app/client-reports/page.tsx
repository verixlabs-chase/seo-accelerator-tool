"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { clearAuthSession } from "../lib/authStorage";
import { PlatformApiError, platformApi, platformApiFile, platformApiText } from "../platform/api";
import {
  LOADING_CLIENT_PORTAL_IDENTITY,
  safeClientPortalIdentity,
  type ClientPortalIdentity,
} from "../clientPortalIdentity";

type ClientReport = {
  id: string;
  location_name: string;
  period_label: string;
  status: "ready";
  generated_at: string;
  freshness: "current" | "older_saved_report";
  pdf_available: boolean;
};

type ReportList = {
  items: ClientReport[];
  count: number;
  identity?: ClientPortalIdentity;
  truth: {
    summary: string;
    limitations: string[];
  };
};

function savedDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Saved date unavailable"
    : `Saved ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)}`;
}

export default function ClientReportsPage() {
  const router = useRouter();
  const [data, setData] = useState<ReportList | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [selectedReport, setSelectedReport] = useState<ClientReport | null>(null);
  const [reportHtml, setReportHtml] = useState("");
  const [openingId, setOpeningId] = useState("");
  const [downloadingId, setDownloadingId] = useState("");
  const [locationFilter, setLocationFilter] = useState("all");
  const [savedDateFilter, setSavedDateFilter] = useState<"all" | ClientReport["freshness"]>("all");
  const [message, setMessage] = useState("");
  const identity = data
    ? safeClientPortalIdentity(data.identity)
    : LOADING_CLIENT_PORTAL_IDENTITY;
  const locationOptions = useMemo(
    () => Array.from(new Set((data?.items || []).map((item) => item.location_name))).sort((left, right) => left.localeCompare(right)),
    [data],
  );
  const visibleReports = useMemo(
    () => (data?.items || []).filter(
      (item) => (locationFilter === "all" || item.location_name === locationFilter)
        && (savedDateFilter === "all" || item.freshness === savedDateFilter),
    ),
    [data, locationFilter, savedDateFilter],
  );

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const user = await platformApi("/auth/me", { method: "GET" });
        if (!active) return;
        if (user?.org_role !== "org_client") {
          router.replace("/dashboard");
          return;
        }
        const payload = (await platformApi("/enterprise/client-reports", { method: "GET" })) as ReportList;
        if (!active) return;
        setData(payload);
        setState("ready");
      } catch (error) {
        if (!active) return;
        if (error instanceof PlatformApiError && error.status === 403) {
          setMessage("Client report access is not available for this workspace right now. Ask the workspace owner for help.");
        } else {
          setMessage("We could not load your reports. Sign in again or ask the workspace owner for help.");
        }
        setState("unavailable");
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (selectedReport && !visibleReports.some((item) => item.id === selectedReport.id)) {
      setSelectedReport(null);
      setReportHtml("");
    }
  }, [selectedReport, visibleReports]);

  async function openReport(report: ClientReport) {
    setOpeningId(report.id);
    setMessage("");
    try {
      const response = await platformApiText(
        `/enterprise/client-reports/${encodeURIComponent(report.id)}/view`,
        { method: "GET" },
      );
      if (!response.contentType.includes("text/html")) throw new Error("Unexpected report format");
      setReportHtml(response.text);
      setSelectedReport(report);
    } catch {
      setMessage("This saved report could not be opened. Ask the workspace owner to check it.");
    } finally {
      setOpeningId("");
    }
  }

  async function downloadReport(report: ClientReport) {
    if (!report.pdf_available) return;
    setDownloadingId(report.id);
    setMessage("");
    try {
      const file = await platformApiFile(
        `/enterprise/client-reports/${encodeURIComponent(report.id)}/download`,
        { method: "GET" },
      );
      if (file.contentType !== "application/pdf") throw new Error("Unexpected report format");
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const downloadUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = dispositionFilename || "client-search-report.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
    } catch {
      setMessage("This saved report PDF could not be downloaded. Ask the workspace owner to check it.");
    } finally {
      setDownloadingId("");
    }
  }

  function signOut() {
    clearAuthSession();
    router.replace("/login");
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.055),transparent_24%),#0d0e10] text-zinc-100">
      <div aria-hidden="true" className="h-1 w-full" style={{ backgroundColor: identity.accent_color }} />
      <header className="border-b border-[#292a2f] bg-[#111216]/95 px-5 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            {identity.logo_data_url ? (
              // Stored portal logos are server-verified still PNGs and never load an external origin.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={identity.logo_data_url} alt={`${identity.display_name} logo`} className="max-h-10 max-w-40 object-contain" />
            ) : null}
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-white">{identity.display_name}</p>
              <p className="mt-0.5 truncate text-xs text-zinc-500">Private client reports</p>
            </div>
          </div>
          <button type="button" onClick={signOut} className="rounded-md border border-[#323339] px-3 py-2 text-sm text-zinc-300 hover:border-zinc-500 hover:text-white">
            Sign out
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-5 py-8">
        <section className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">Client reports</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{identity.portal_title}</h1>
          <p className="mt-3 text-sm leading-6 text-zinc-400">
            Open a report for a location the workspace owner assigned to you. This view cannot change the business, billing, settings, or tracked work.
          </p>
        </section>

        {state === "loading" ? (
          <div className="mt-8 rounded-xl border border-[#292a2f] bg-[#121316] p-6 text-sm text-zinc-400" role="status">
            Loading your assigned reports...
          </div>
        ) : null}

        {message ? (
          <p className="mt-6 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100" role="status">
            {message}
          </p>
        ) : null}

        {state === "ready" && data?.items.length === 0 ? (
          <section className="mt-8 rounded-xl border border-[#292a2f] bg-[#121316] p-7">
            <h2 className="text-lg font-semibold text-white">No reports have been shared here yet</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-400">Ask the workspace owner to assign your location and prepare a verified saved report.</p>
          </section>
        ) : null}

        {state === "ready" && data?.items.length ? (
          <div className="mt-8 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
            <section aria-labelledby="available-reports-heading">
              <h2 id="available-reports-heading" className="text-lg font-semibold text-white">Available reports</h2>
              <div className="mt-3 grid gap-3 rounded-lg border border-[#292a2f] bg-[#111216] p-3">
                <label className="text-xs font-semibold text-zinc-400">
                  Location
                  <select
                    value={locationFilter}
                    onChange={(event) => setLocationFilter(event.target.value)}
                    className="mt-1.5 w-full rounded-md border border-[#34353b] bg-[#0d0e10] px-3 py-2 text-sm font-normal text-zinc-100"
                  >
                    <option value="all">All assigned locations</option>
                    {locationOptions.map((locationName) => (
                      <option key={locationName} value={locationName}>{locationName}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-semibold text-zinc-400">
                  Saved date
                  <select
                    value={savedDateFilter}
                    onChange={(event) => setSavedDateFilter(event.target.value as "all" | ClientReport["freshness"])}
                    className="mt-1.5 w-full rounded-md border border-[#34353b] bg-[#0d0e10] px-3 py-2 text-sm font-normal text-zinc-100"
                  >
                    <option value="all">All saved reports</option>
                    <option value="current">Saved in the last 31 days</option>
                    <option value="older_saved_report">Older saved reports</option>
                  </select>
                </label>
                <p className="text-xs text-zinc-500" aria-live="polite">
                  Showing {visibleReports.length} of {data.items.length} assigned reports
                </p>
              </div>
              <div className="mt-3 space-y-3">
                {visibleReports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    onClick={() => void openReport(report)}
                    disabled={Boolean(openingId)}
                    className={`w-full rounded-xl border bg-[#121316] p-4 text-left transition ${selectedReport?.id === report.id ? "ring-1 ring-inset" : "border-[#292a2f] hover:border-zinc-500"} disabled:cursor-wait disabled:opacity-70`}
                    style={selectedReport?.id === report.id ? { borderColor: identity.accent_color, boxShadow: `inset 3px 0 0 ${identity.accent_color}` } : undefined}
                  >
                    <span className="block text-sm font-semibold text-white">{report.location_name}</span>
                    <span className="mt-1 block text-sm text-zinc-300">{report.period_label}</span>
                    <span className="mt-2 block text-xs text-zinc-500">{savedDate(report.generated_at)}</span>
                    {report.freshness === "older_saved_report" ? <span className="mt-2 block text-xs text-amber-300">Older saved report</span> : null}
                    <span className="mt-3 block text-sm font-medium text-zinc-200">{openingId === report.id ? "Opening..." : "Open report"}</span>
                  </button>
                ))}
                {visibleReports.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[#34353b] bg-[#111216] p-5">
                    <p className="text-sm font-semibold text-white">No reports match these choices</p>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">Show every assigned report, then choose another location or saved date.</p>
                    <button
                      type="button"
                      onClick={() => {
                        setLocationFilter("all");
                        setSavedDateFilter("all");
                      }}
                      className="mt-3 text-sm font-semibold text-zinc-200 underline decoration-zinc-500 underline-offset-4"
                    >
                      Show all assigned reports
                    </button>
                  </div>
                ) : null}
              </div>
            </section>

            <section aria-label="Selected client report" className="min-w-0">
              {selectedReport && reportHtml ? (
                <div>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#292a2f] bg-[#111216] px-4 py-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{selectedReport.location_name}</p>
                      <p className="mt-0.5 text-xs text-zinc-500">{selectedReport.period_label}</p>
                    </div>
                    {selectedReport.pdf_available ? (
                      <button
                        type="button"
                        onClick={() => void downloadReport(selectedReport)}
                        disabled={downloadingId === selectedReport.id}
                        className="rounded-md border border-[#3a3c44] px-3 py-2 text-sm font-semibold text-zinc-100 hover:border-zinc-500 disabled:cursor-wait disabled:opacity-60"
                      >
                        {downloadingId === selectedReport.id ? "Preparing PDF..." : "Download PDF"}
                      </button>
                    ) : (
                      <span className="text-xs text-zinc-500">PDF download not available</span>
                    )}
                  </div>
                  <iframe
                    title={`${selectedReport.location_name} ${selectedReport.period_label}`}
                    srcDoc={reportHtml}
                    sandbox=""
                    referrerPolicy="no-referrer"
                    className="h-[72vh] min-h-[42rem] w-full rounded-xl border border-[#292a2f] bg-white shadow-2xl"
                  />
                </div>
              ) : (
                <div className="grid min-h-[24rem] place-items-center rounded-xl border border-dashed border-[#34353b] bg-[#111216] p-8 text-center">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Choose a report to open</h2>
                    <p className="mt-2 text-sm leading-6 text-zinc-400">The report will stay inside this private, read-only page.</p>
                  </div>
                </div>
              )}
            </section>
          </div>
        ) : null}

        {state === "ready" && data ? (
          <section className="mt-8 max-w-2xl rounded-lg border border-[#292a2f] bg-[#111216] px-4 py-3">
            <p className="text-sm text-zinc-300">{data.truth.summary}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-zinc-500">
              {data.truth.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
        ) : null}

        {state === "ready" && identity.platform_attribution_visible ? (
          <p className="mt-8 text-xs text-zinc-600">Private report access provided through InsightOS.</p>
        ) : null}
      </div>
    </main>
  );
}
