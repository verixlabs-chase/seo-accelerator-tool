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
  TruthNotice,
  useLocationContext,
  type RuntimeTruth,
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
  items: CitationItem[];
  truth?: RuntimeTruth;
  correction_access?: ListingCorrectionAccess;
};

type ListingCorrectionAccess = {
  plan_eligible: boolean;
  correction_enabled: false;
  required_plan: string;
  state: "plan_upgrade_required" | "provider_approval_required" | "plan_check_unavailable";
  summary: string;
};

type ListingDifference = {
  field: string;
  expected: string;
  found: string;
};

type DirectoryListingItem = {
  id: string;
  source_name: string;
  listing_url?: string | null;
  status: string;
  business_name?: string | null;
  address_line1?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  phone?: string | null;
  website_url?: string | null;
  primary_category?: string | null;
  field_differences: ListingDifference[];
  last_seen_at: string;
  source_type: string;
  source_system?: string | null;
  source_claimed_status?: string | null;
  import_batch_id?: string | null;
};

type ListingInventory = {
  items: DirectoryListingItem[];
  summary: {
    total: number;
    freshly_checked: number;
    imported_history: number;
    confirmed: number;
    needs_attention: number;
    newest_observation_at?: string | null;
  };
  truth: {
    correction_available: boolean;
    correction_reason?: string;
    correction_access?: ListingCorrectionAccess;
  };
};

type DiscoveryPreview = {
  location_name: string;
  estimated_credits: number;
  credits_remaining: number;
  credits_after: number;
  connected_account: boolean;
  can_start: boolean;
  message: string;
};

type DiscoveryRun = {
  id: string;
  status: string;
  result_count: number;
  estimated_credits: number;
  correction_available: boolean;
  error_message?: string | null;
  completed_at?: string | null;
};

function toTitleCase(value?: string) {
  if (!value) return "Unknown";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getStatusLabel(status?: string) {
  if (status === "completed") return "Completed";
  if (status === "running" || status === "queued") return "In progress";
  if (status === "submitted") return "Submitted";
  if (status === "live") return "Live";
  if (status === "pending" || status === "draft") return "Pending";
  if (status === "failed") return "Failed";
  if (status === "verified") return "Verified";
  return toTitleCase(status);
}

function getStatusTone(status?: string) {
  if (status === "live" || status === "verified" || status === "correct") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "inconsistent" || status === "missing" || status === "duplicate") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-100";
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
    return "This saved record says the listing was live. Open the directory to confirm its current state.";
  }
  if (citation.submission_status === "verified") {
    return "This saved record says the listing was verified. Open the directory to confirm its current state.";
  }
  if (citation.submission_status === "submitted") {
    return "This request was previously recorded as submitted. Its current directory status is not synchronized.";
  }
  if (citation.submission_status === "pending" || citation.submission_status === "draft") {
    return "This is saved request history. It is not proof that a directory is processing the request.";
  }
  if (citation.submission_status === "failed") {
    return "This saved request was not accepted. Check and correct the directory manually.";
  }
  return "This saved status is unclear. Open the directory to confirm the current listing.";
}

function differenceLabel(field: string) {
  const labels: Record<string, string> = {
    business_name: "Business name",
    address_line1: "Street address",
    city: "City",
    region: "State or region",
    postal_code: "ZIP or postal code",
    phone: "Phone number",
    website_url: "Website",
  };
  return labels[field] || toTitleCase(field);
}

export default function CitationsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [statusResult, setStatusResult] = useState<StatusResult | null>(null);
  const [inventory, setInventory] = useState<ListingInventory | null>(null);
  const [discoveryPreview, setDiscoveryPreview] = useState<DiscoveryPreview | null>(null);
  const [latestDiscoveryRun, setLatestDiscoveryRun] = useState<DiscoveryRun | null>(null);
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
        items: Array.isArray(raw?.items) ? (raw.items as CitationItem[]) : [],
        truth: raw?.truth || null,
        correction_access: raw?.correction_access,
      });
      setNotice("Saved listing request history loaded. No directory was contacted or changed.");
    });
  }

  const loadListingInventory = useCallback(async (campaignId: string) => {
    const [inventoryResponse, latestResponse] = await Promise.all([
      platformApi(`/citations/inventory?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
      platformApi(`/citations/discovery/latest?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }),
    ]);
    const saved = inventoryResponse as ListingInventory;
    setInventory({
      items: Array.isArray(saved?.items) ? saved.items : [],
      summary: saved?.summary || {
        total: 0,
        freshly_checked: 0,
        imported_history: 0,
        confirmed: 0,
        needs_attention: 0,
      },
      truth: saved?.truth || { correction_available: false },
    });
    setLatestDiscoveryRun((latestResponse?.run as DiscoveryRun | null) || null);
  }, []);

  async function previewListingCheck() {
    if (!selectedCampaignId) {
      setError("Select a business first.");
      return;
    }
    await runAction("preview-discovery", async () => {
      const response = await platformApi("/citations/discovery/preview", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId }),
      });
      setDiscoveryPreview(response as DiscoveryPreview);
    });
  }

  async function startListingCheck() {
    if (!selectedCampaignId || !discoveryPreview) return;
    await runAction("start-discovery", async () => {
      const response = await platformApi("/citations/discovery/runs", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          idempotency_key: `listing-check-${selectedCampaignId}-${Date.now()}`,
        }),
      });
      const run = response?.run as DiscoveryRun;
      setLatestDiscoveryRun(run);
      setDiscoveryPreview(null);
      await loadListingInventory(selectedCampaignId);
      setNotice(
        run.status === "completed"
          ? `Public listing check finished. ${run.result_count} matching ${run.result_count === 1 ? "listing was" : "listings were"} saved.`
          : run.error_message || "The public listing check is still being processed.",
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
        setError(err instanceof Error ? err.message : "Unable to load directory listings.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadCampaigns]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setStatusResult(null);
    setDiscoveryPreview(null);
    void loadListingInventory(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load public listings.");
    });
  }, [selectedCampaignId, loading, loadListingInventory]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const correctionAccess =
    inventory?.truth.correction_access || statusResult?.correction_access || null;

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
        label: "Public listing check",
        value: latestDiscoveryRun
          ? getStatusLabel(latestDiscoveryRun.status)
          : "Not checked yet",
        tone: latestDiscoveryRun?.status === "completed" ? "success" : "warning",
      },
      {
        label: "Listings found",
        value: inventory ? String(inventory.summary.total) : "Loading",
        tone: inventory && inventory.summary.total > 0 ? "success" : "warning",
      },
      {
        label: "Details confirmed",
        value: inventory ? String(inventory.summary.confirmed) : "Loading",
        tone: inventory && inventory.summary.confirmed > 0 ? "success" : "warning",
      },
      {
        label: "Needs attention",
        value: inventory ? String(inventory.summary.needs_attention) : "Loading",
        tone: inventory && inventory.summary.needs_attention > 0 ? "danger" : "success",
      },
    ],
    [inventory, latestDiscoveryRun],
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
      dateRangeLabel="Latest directory listing data"
      topBarActions={
        <>
          <button
            onClick={() => router.push("/local-visibility")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            Local Search
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Directory listings"
          title="See where your business information is right or wrong"
          summary="Check supported public listings for this location. InsightOS shows exactly which saved business details match and which ones need attention."
          compact
        />

        <TruthNotice title="This check does not change a listing.">
          InsightOS can find and compare supported public listings. Automatic corrections are not
          available yet, so nothing will be edited without a separate approved correction feature.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading directory listings"
            summary="Checking saved listing requests and their latest status."
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
            summary="Set up a business first so InsightOS can manage its directory listings."
            actionLabel="Go to dashboard setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-3xl">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Found online
                  </p>
                  <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                    Public listing check
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    Start here to compare this location&apos;s saved business name, address, and
                    website with supported public sources.
                  </p>
                </div>
                <button
                  onClick={() => void previewListingCheck()}
                  disabled={busyAction !== ""}
                  className="rounded-md bg-[#ff6b18] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "preview-discovery" ? "Checking allowance..." : "Check listings online"}
                </button>
              </div>

              {discoveryPreview ? (
                <div className="mt-5 grid gap-4 rounded-md border border-[#35363c] bg-[#0f1012] p-4 lg:grid-cols-[1fr_auto] lg:items-center">
                  <div>
                    <p className="text-sm font-semibold text-white">
                      Ready to check {discoveryPreview.location_name}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      {discoveryPreview.message}{" "}
                      {discoveryPreview.connected_account
                        ? "This uses the connected search-data account."
                        : `This uses ${discoveryPreview.estimated_credits} Insight Credits, leaving about ${discoveryPreview.credits_after}.`}
                    </p>
                  </div>
                  <button
                    onClick={() => void startListingCheck()}
                    disabled={busyAction !== "" || !discoveryPreview.can_start}
                    className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "start-discovery" ? "Checking..." : "Start public listing check"}
                  </button>
                </div>
              ) : null}

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard
                  label="Listings found"
                  value={inventory ? String(inventory.summary.total) : "—"}
                  summary="Matching listings saved for this location."
                />
                <KpiCard
                  label="Freshly checked"
                  value={inventory ? String(inventory.summary.freshly_checked) : "—"}
                  summary="Listings checked through the current online connection."
                />
                <KpiCard
                  label="Details confirmed"
                  value={inventory ? String(inventory.summary.confirmed) : "—"}
                  summary="Listings whose comparable business details match."
                  tone={inventory && inventory.summary.confirmed > 0 ? "highlight" : undefined}
                />
                <KpiCard
                  label="Needs attention"
                  value={inventory ? String(inventory.summary.needs_attention) : "—"}
                  summary="Listings with a saved detail that does not match."
                />
                {inventory && inventory.summary.imported_history > 0 ? (
                  <p className="sm:col-span-2 xl:col-span-4 text-xs leading-5 text-violet-200">
                    {inventory.summary.imported_history} imported listing record{inventory.summary.imported_history === 1 ? " is" : "s are"} available as background history. Imported records do not count as a fresh online check.
                  </p>
                ) : null}
              </div>

              {latestDiscoveryRun ? (
                <p className="mt-4 text-xs text-zinc-500">
                  Latest check: {getStatusLabel(latestDiscoveryRun.status)}
                  {latestDiscoveryRun.completed_at
                    ? ` on ${new Date(latestDiscoveryRun.completed_at).toLocaleDateString()}`
                    : ""}
                  . Corrections are not available in this version.
                </p>
              ) : null}

              {inventory && inventory.items.length > 0 ? (
                <div className="mt-5 space-y-3">
                  {inventory.items.map((listing) => (
                    <article
                      key={listing.id}
                      className="rounded-md border border-[#2a2b30] bg-[#101113] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-base font-semibold text-white">{listing.source_name}</p>
                          <p className="mt-1 text-sm text-zinc-400">
                            {listing.business_name || "Business name not returned"}
                            {listing.primary_category ? ` · ${listing.primary_category}` : ""}
                          </p>
                        </div>
                        <span className={`rounded-md border px-2 py-1 text-xs font-medium ${listing.source_type === "imported" ? "border-violet-400/30 bg-violet-400/10 text-violet-100" : getStatusTone(listing.status)}`}>
                          {listing.source_type === "imported"
                            ? "Imported history"
                            : listing.field_differences.length > 0
                              ? "Needs attention"
                              : "Details match"}
                        </span>
                      </div>

                      {listing.source_type === "imported" ? (
                        <div className="mt-3 rounded-md border border-violet-400/20 bg-violet-400/5 p-3 text-sm leading-6 text-violet-100">
                          This record came from a previous system on {new Date(listing.last_seen_at).toLocaleDateString()}.
                          {listing.source_claimed_status ? ` That file described it as ${listing.source_claimed_status.replaceAll("_", " ")}.` : ""} Run a public listing check before treating it as current.
                        </div>
                      ) : null}

                      {listing.field_differences.length > 0 ? (
                        <div className="mt-4 space-y-2">
                          {listing.field_differences.map((difference) => (
                            <div
                              key={`${listing.id}-${difference.field}`}
                              className="grid gap-2 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-sm md:grid-cols-[150px_1fr_1fr]"
                            >
                              <p className="font-medium text-amber-100">
                                {differenceLabel(difference.field)}
                              </p>
                              <p className="text-zinc-400">
                                <span className="text-zinc-500">Saved:</span> {difference.expected}
                              </p>
                              <p className="text-zinc-300">
                                <span className="text-zinc-500">{listing.source_type === "imported" ? "Imported file:" : "Found online:"}</span> {difference.found}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : listing.source_type !== "imported" ? (
                        <p className="mt-3 text-sm text-emerald-100">
                          The comparable business details match this location&apos;s saved information.
                        </p>
                      ) : null}

                      {listing.listing_url ? (
                        <a
                          href={listing.listing_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-4 inline-flex text-sm font-medium text-[#ff8a4c] hover:text-[#ffa06f]"
                        >
                          Open public listing →
                        </a>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : inventory ? (
                <div className="mt-5 rounded-md border border-[#2a2b30] bg-[#101113] p-4">
                  <p className="text-sm font-medium text-white">
                    {latestDiscoveryRun?.status === "completed"
                      ? "No matching listing was found in the currently supported public sources."
                      : "No public listing check has been completed for this location yet."}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-zinc-400">
                    This is not proof that the business is missing everywhere. It only describes the
                    sources supported by this check.
                  </p>
                </div>
              ) : null}
            </section>

            <OwnerDecisionPanel
              title={
                !statusResult
                  ? "Load saved listing request history"
                  : failedCount > 0
                    ? `${failedCount} saved ${failedCount === 1 ? "request needs" : "requests need"} attention`
                    : citations.length === 0
                      ? "No saved listing requests yet"
                      : liveCount === citations.length
                        ? "Every saved request was recorded as confirmed"
                        : `${liveCount} of ${citations.length} saved requests were confirmed`
              }
              summary={
                !statusResult
                  ? "InsightOS can show prior request records without contacting or changing a directory."
                  : failedCount > 0
                    ? "These are saved workflow records, not a live directory status check."
                    : citations.length === 0
                      ? "Use the public listing check above to find differences, then correct the directory manually."
                      : liveCount === citations.length
                        ? "Open the public listing before relying on an older saved confirmation."
                        : `${pendingCount} saved ${pendingCount === 1 ? "request has" : "requests have"} no confirmed result.`
              }
              nextStep={
                failedCount > 0
                  ? "Open the directory, compare it with the public check above, and correct the information manually."
                  : !statusResult
                    ? "Load the saved history to see what was previously recorded."
                    : citations.length === 0
                      ? "Run a public listing check and use its exact field differences as your correction checklist."
                      : liveCount === citations.length
                        ? "Run a fresh public check after important business information changes."
                        : "Confirm the current result directly with the directory before taking action."
              }
              actionLabel={statusResult ? "Reload saved history" : "Load saved history"}
              onAction={() => void refreshStatus()}
              tone={
                failedCount > 0
                  ? "urgent"
                  : statusResult && citations.length > 0 && liveCount === citations.length
                    ? "positive"
                    : statusResult
                      ? "warning"
                      : "neutral"
              }
              progress={
                statusResult && citations.length > 0
                  ? {
                      label: "Confirmed listing progress",
                      value: liveCount,
                      total: citations.length,
                      summary: "This reflects saved history and is not live synchronization.",
                    }
                  : undefined
              }
            />

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Saved requests"
                value={statusResult ? String(citations.length) : "—"}
                summary={
                  statusResult
                    ? "Historical listing-request records saved for this business."
                    : "Load saved history to see prior request records."
                }
              />
              <KpiCard
                label="Recorded live"
                value={statusResult ? String(liveCount) : "—"}
                summary={
                  statusResult
                    ? "Saved records previously marked live or verified."
                    : "Load saved history to see prior confirmations."
                }
                tone={liveCount > 0 ? "highlight" : undefined}
              />
              <KpiCard
                label="Saved in progress"
                value={statusResult ? String(pendingCount) : "—"}
                summary={
                  statusResult
                    ? "Records previously marked submitted, pending, or draft."
                    : "Load saved history to see incomplete records."
                }
              />
              <KpiCard
                label="Recorded failed"
                value={statusResult ? String(failedCount) : "—"}
                summary={
                  statusResult
                    ? failedCount > 0
                      ? "These saved requests were not accepted. Check the directory manually."
                      : "No failures recorded."
                    : "Load saved history to check prior failures."
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Managed corrections
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  {correctionAccess?.plan_eligible
                    ? "Your plan is eligible, but live corrections are not available yet"
                    : correctionAccess?.state === "plan_check_unavailable"
                      ? "Managed correction access could not be confirmed"
                    : correctionAccess
                      ? `Managed corrections require ${correctionAccess.required_plan}`
                      : "Managed corrections are not available yet"}
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  {correctionAccess?.summary ||
                    "InsightOS has not confirmed an approved production correction connection for this workspace."}
                </p>

                <div className="mt-5 rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What you can do now
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">
                    Run the public listing check, review each saved-versus-found difference, open
                    the public listing, and make the correction directly with that directory.
                    InsightOS will not claim that a directory was changed or synchronized.
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
                      Saved request history
                    </h2>
                    <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                      {statusResult
                        ? "Showing saved workflow records only. Reloading does not contact a directory."
                        : "Load any prior listing-request records saved for this business."}
                    </p>
                  </div>
                  <button
                    onClick={() => void refreshStatus()}
                    disabled={busyAction !== ""}
                    className="shrink-0 rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyAction === "refresh"
                      ? "Loading..."
                      : statusResult
                        ? "Reload saved history"
                        : "Load saved history"}
                  </button>
                </div>

                {!statusResult ? (
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm leading-6 text-zinc-400">
                      Saved request history has not been loaded yet. Use the button above to read
                      existing records without contacting a directory.
                    </p>
                  </div>
                ) : citations.length === 0 ? (
                  <EmptyState
                    title="No saved listing request history"
                    summary="Use the public listing check above and correct any differences directly with the directory."
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

              </section>
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
