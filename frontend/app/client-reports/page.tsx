"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { clearAuthSession } from "../lib/authStorage";
import { PlatformApiError, platformApi, platformApiText } from "../platform/api";
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
  const [message, setMessage] = useState("");
  const identity = data
    ? safeClientPortalIdentity(data.identity)
    : LOADING_CLIENT_PORTAL_IDENTITY;

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
              <div className="mt-3 space-y-3">
                {data.items.map((report) => (
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
              </div>
            </section>

            <section aria-label="Selected client report" className="min-w-0">
              {selectedReport && reportHtml ? (
                <iframe
                  title={`${selectedReport.location_name} ${selectedReport.period_label}`}
                  srcDoc={reportHtml}
                  sandbox=""
                  referrerPolicy="no-referrer"
                  className="h-[72vh] min-h-[42rem] w-full rounded-xl border border-[#292a2f] bg-white shadow-2xl"
                />
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
