"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  TruthNotice,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type CitationItem = {
  id: string;
  directory_name: string;
  submission_status: string;
  listing_url?: string | null;
};

type StatusResult = {
  job_id: string | null;
  items: CitationItem[];
};

function toTitleCase(value?: string) {
  if (!value) return "Unknown";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getStatusLabel(status?: string) {
  if (status === "submitted") return "Submitted";
  if (status === "live") return "Live";
  if (status === "pending" || status === "draft") return "Pending";
  if (status === "failed") return "Failed";
  if (status === "verified") return "Verified";
  return toTitleCase(status);
}

function getStatusTone(status?: string) {
  if (status === "live" || status === "verified") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "submitted") {
    return "border-accent-500/20 bg-accent-500/10 text-zinc-100";
  }
  if (status === "pending" || status === "draft") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
  }
  if (status === "failed") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-100";
  }
  return "border-[#26272c] bg-[#141518] text-zinc-200";
}

function getStatusGuidance(citation: CitationItem) {
  if (citation.submission_status === "live" || citation.listing_url) {
    return "This directory listing is live. The listing URL is available below.";
  }
  if (citation.submission_status === "verified") {
    return "This listing has been verified. Use the refresh button to check for a live URL.";
  }
  if (citation.submission_status === "submitted") {
    return "Submitted and queued for processing. Use the refresh button to check for updates from the directory.";
  }
  if (citation.submission_status === "pending" || citation.submission_status === "draft") {
    return "Waiting to be processed by the next batch run.";
  }
  if (citation.submission_status === "failed") {
    return "This submission was not accepted. You can resubmit or check the directory manually.";
  }
  return "Status is unclear. Use the refresh button to pull the latest update.";
}

export default function CitationsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [statusResult, setStatusResult] = useState<StatusResult | null>(null);
  const [newDirectory, setNewDirectory] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
    const response = await platformApi("/campaigns", { method: "GET" });
    const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
    setCampaigns(items);
    setSelectedCampaignId((current) => {
      if (current && items.some((item) => item.id === current)) return current;
      return items[0]?.id || "";
    });
    return items;
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

  async function submitCitation() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    if (!newDirectory.trim()) {
      setError("Directory name is required.");
      return;
    }
    await runAction("submit", async () => {
      const directory = newDirectory.trim();
      await platformApi("/citations/submissions", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          directory_name: directory,
        }),
      });
      setNewDirectory("");
      setNotice(
        `Citation submitted to "${directory}". A background job has been queued to process this batch. Use "Refresh status" below to check for updates.`,
      );
    });
  }

  async function refreshStatus() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    await runAction("refresh", async () => {
      const response = await platformApi(
        `/citations/status?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "GET" },
      );
      const raw = response as StatusResult | null;
      setStatusResult({
        job_id: raw?.job_id ?? null,
        items: Array.isArray(raw?.items) ? (raw.items as CitationItem[]) : [],
      });
      setNotice(
        raw?.job_id
          ? "Status refreshed. A background job has been queued to pull updates from each directory. Results below reflect the current database state."
          : "Status loaded. No background job was queued — the message broker may be unavailable. Results below reflect the current database state.",
      );
    });
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        await loadCampaigns();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load citations.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadCampaigns]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setStatusResult(null);
  }, [selectedCampaignId, loading]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;

  const citations = statusResult?.items ?? [];
  const liveCount = citations.filter(
    (c) => c.submission_status === "live" || c.submission_status === "verified" || c.listing_url,
  ).length;
  const pendingCount = citations.filter(
    (c) => c.submission_status === "submitted" || c.submission_status === "pending" || c.submission_status === "draft",
  ).length;
  const failedCount = citations.filter((c) => c.submission_status === "failed").length;

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Citations",
        value: citations.length > 0 ? `${citations.length} tracked` : "Not yet loaded",
        tone: citations.length > 0 ? "success" : "warning",
      },
      {
        label: "Live listings",
        value: liveCount > 0 ? `${liveCount} live` : "None confirmed",
        tone: liveCount > 0 ? "success" : "warning",
      },
      {
        label: "Pending",
        value: pendingCount > 0 ? `${pendingCount} in progress` : "None pending",
        tone: pendingCount > 0 ? "info" : "success",
      },
      {
        label: "Failed",
        value: failedCount > 0 ? `${failedCount} failed` : "None failed",
        tone: failedCount > 0 ? "danger" : "success",
      },
    ],
    [citations.length, failedCount, liveCount, pendingCount],
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
      dateRangeLabel="Live citation data"
      topBarActions={
        <>
          <select
            value={selectedCampaignId}
            onChange={(event) => {
              setSelectedCampaignId(event.target.value);
              setNotice("");
              setError("");
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
            onClick={() => router.push("/local-visibility")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            Local SEO
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Citations"
          title="Submit and track your directory listings"
          summary="Citations are mentions of your business on directories and data aggregators. Submit to a directory to start the listing process, then use the refresh button to check on progress and find your live listing URLs."
        />

        <TruthNotice title="Citation status reflects workflow state, not guaranteed directory publication.">
          Submitted and pending rows mean the request is in flight. Only a live or verified state,
          ideally with a listing URL, should be treated as evidence that the directory entry is
          actually published.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading citations"
            summary="Setting up the citations workspace for the active business."
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
            title="No business is ready yet"
            summary="Set up a business first so InsightOS can manage directory citations."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Citations tracked"
                value={statusResult ? String(citations.length) : "—"}
                summary={
                  statusResult
                    ? "Total directory submissions tracked for this business."
                    : "Load citation status to see how many directories are tracked."
                }
              />
              <KpiCard
                label="Live listings"
                value={statusResult ? String(liveCount) : "—"}
                summary={
                  statusResult
                    ? "Directories where the listing is confirmed live."
                    : "Load citation status to see how many listings are live."
                }
                tone={liveCount > 0 ? "highlight" : undefined}
              />
              <KpiCard
                label="In progress"
                value={statusResult ? String(pendingCount) : "—"}
                summary={
                  statusResult
                    ? "Submissions that have been sent but are not yet confirmed live."
                    : "Load citation status to see how many are still processing."
                }
              />
              <KpiCard
                label="Failed"
                value={statusResult ? String(failedCount) : "—"}
                summary={
                  statusResult
                    ? failedCount > 0
                      ? "These submissions were not accepted. You can resubmit or check the directory manually."
                      : "No failures recorded."
                    : "Load citation status to check for any failed submissions."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Submit
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Add a directory citation
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Enter the name of a directory or data aggregator. Once submitted, a background job
                  queues the listing for processing. Use the refresh button to monitor progress.
                </p>

                <div className="mt-4 space-y-3">
                  <div>
                    <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Directory name
                    </label>
                    <input
                      value={newDirectory}
                      onChange={(event) => setNewDirectory(event.target.value)}
                      placeholder="e.g. Google Business Profile"
                      className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                    />
                  </div>

                  <button
                    onClick={() => void submitCitation()}
                    disabled={busyAction !== "" || !newDirectory.trim()}
                    className="w-full rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "submit" ? "Submitting..." : "Submit citation"}
                  </button>
                </div>

                <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    How citations work
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">
                    Submitting creates a record and queues a background job. The directory provider
                    then processes the listing, which can take time. Use{" "}
                    <span className="text-zinc-300">Refresh status</span> on the right to pull the
                    latest updates. Live listings will show a URL when the directory confirms them.
                  </p>
                </div>
              </section>

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Status
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Citation status
                    </h2>
                    <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                      {statusResult
                        ? "Showing the current database state. Refresh again to pull the latest updates from each directory."
                        : "Load the current status of all citations for this business. This queues a background refresh job."}
                    </p>
                  </div>
                  <button
                    onClick={() => void refreshStatus()}
                    disabled={busyAction !== ""}
                    className="shrink-0 rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "refresh"
                      ? "Refreshing..."
                      : statusResult
                        ? "Refresh status"
                        : "Load citation status"}
                  </button>
                </div>

                {!statusResult ? (
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm leading-6 text-zinc-400">
                      Citation status has not been loaded yet. Use the button above to pull the
                      current status of all directory submissions for this business.
                    </p>
                  </div>
                ) : citations.length === 0 ? (
                  <EmptyState
                    title="No citations found for this business"
                    summary="Submit a directory citation using the form on the left to get started."
                  />
                ) : (
                  <div className="space-y-3">
                    {citations.map((citation) => (
                      <div
                        key={citation.id}
                        className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <p className="text-sm font-medium text-white">{citation.directory_name}</p>
                          <span
                            className={`shrink-0 rounded-md border px-2 py-1 text-xs font-medium ${getStatusTone(citation.submission_status)}`}
                          >
                            {getStatusLabel(citation.submission_status)}
                          </span>
                        </div>
                        <p className="mt-1.5 text-sm leading-5 text-zinc-400">
                          {getStatusGuidance(citation)}
                        </p>
                        {citation.listing_url ? (
                          <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-3 py-2">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                              Listing URL
                            </p>
                            <p className="mt-1 break-all text-sm text-emerald-100">
                              {citation.listing_url}
                            </p>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}

                {statusResult && !statusResult.job_id ? (
                  <p className="mt-4 text-xs text-zinc-600">
                    No background job was queued on last refresh — message broker may be
                    unavailable. Results reflect the current database state only.
                  </p>
                ) : null}
              </section>
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
