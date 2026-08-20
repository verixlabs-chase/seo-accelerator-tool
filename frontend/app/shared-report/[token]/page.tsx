"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type ReportState = "loading" | "ready" | "expired" | "unavailable";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "/api/v1" : "http://localhost:8000/api/v1");

function validToken(value: string) {
  return /^[A-Za-z0-9_-]{24,160}$/.test(value);
}

export default function SharedReportPage() {
  const params = useParams<{ token: string }>();
  const token = typeof params?.token === "string" ? params.token : "";
  const [state, setState] = useState<ReportState>("loading");
  const [reportHtml, setReportHtml] = useState("");

  useEffect(() => {
    if (!validToken(token)) {
      setState("unavailable");
      return;
    }

    const controller = new AbortController();
    setState("loading");
    setReportHtml("");

    void fetch(`${API_BASE}/reports/shared/${encodeURIComponent(token)}`, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      headers: { Accept: "text/html" },
      signal: controller.signal,
      referrerPolicy: "no-referrer",
    })
      .then(async (response) => {
        if (response.status === 410) {
          setState("expired");
          return;
        }
        if (!response.ok || !response.headers.get("content-type")?.includes("text/html")) {
          setState("unavailable");
          return;
        }
        setReportHtml(await response.text());
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("unavailable");
      });

    return () => controller.abort();
  }, [token]);

  return (
    <main className="min-h-screen bg-[#0d0e10] text-zinc-100">
      <header className="border-b border-[#2a2b30] bg-[#111216] px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold tracking-tight text-white">InsightOS</p>
            <p className="mt-0.5 text-xs text-zinc-500">Private client report</p>
          </div>
          <p className="text-xs text-zinc-500">This link turns off automatically.</p>
        </div>
      </header>

      {state === "loading" ? (
        <section className="mx-auto grid min-h-[70vh] max-w-lg place-items-center px-5 text-center" role="status">
          <div>
            <div className="mx-auto h-7 w-7 animate-pulse rounded-full border-2 border-orange-500 border-t-transparent" />
            <h1 className="mt-4 text-xl font-semibold text-white">Opening your report</h1>
            <p className="mt-2 text-sm text-zinc-400">Checking this private link now.</p>
          </div>
        </section>
      ) : null}

      {state === "ready" ? (
        <section aria-label="Client report" className="mx-auto max-w-7xl p-3 sm:p-5">
          <iframe
            title="Shared client report"
            srcDoc={reportHtml}
            sandbox=""
            referrerPolicy="no-referrer"
            className="h-[calc(100vh-6.5rem)] min-h-[42rem] w-full rounded-lg border border-[#2a2b30] bg-white shadow-2xl"
          />
        </section>
      ) : null}

      {state === "expired" || state === "unavailable" ? (
        <section className="mx-auto grid min-h-[70vh] max-w-lg place-items-center px-5 text-center" role="status">
          <div>
            <div className="mx-auto grid h-11 w-11 place-items-center rounded-full border border-amber-500/25 bg-amber-500/10 text-xl text-amber-300">
              !
            </div>
            <h1 className="mt-4 text-xl font-semibold text-white">
              {state === "expired" ? "This private report link is no longer active" : "This report is not available"}
            </h1>
            <p className="mt-2 text-sm leading-6 text-zinc-400">
              {state === "expired"
                ? "It expired or the sender turned it off. Ask the sender for a new private link."
                : "Check that the complete link was copied correctly, or ask the sender for a new one."}
            </p>
            <Link href="/" className="mt-5 inline-flex text-sm font-semibold text-orange-400 underline decoration-orange-400/40 underline-offset-4">
              Visit InsightOS
            </Link>
          </div>
        </section>
      ) : null}
    </main>
  );
}
