"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  DetailsDisclosure,
  EmptyState,
  KpiCard,
  LoadingCard,
  OwnerDecisionPanel,
  PageSection,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type ContentPage = {
  id: string;
  title: string;
  url: string;
  page_type: string;
  publication_state: string;
  source: "connected_website" | "website_scan" | string;
  source_label: string;
  last_checked_at: string;
  word_count: number;
  attention: string[];
};

type ContentBrief = {
  id: string;
  status: string;
  title: string;
  primary_search: string;
  recommended_page_action: string;
  target_url?: string | null;
  competitor_domain: string;
  competitor_url?: string | null;
  service_name?: string | null;
  service_area_name?: string | null;
  evidence: {
    owner_position?: number | null;
    competitor_position?: number | null;
    search_volume?: number | null;
    source_updated_at?: string | null;
    evidence_note?: string | null;
  };
  outline: Array<{ order: number; heading: string; guidance: string }>;
  created_at: string;
};

type ContentWork = {
  id: string;
  title: string;
  status: string;
  target_url?: string | null;
  planned_month: number;
  updated_at: string;
};

type ContentWorkspace = {
  location: {
    campaign_id: string;
    business_location_id?: string | null;
    name: string;
    domain: string;
  };
  truth: { state: string; summary: string; limitations: string[] };
  summary: {
    pages: number;
    pages_needing_attention: number;
    draft_briefs: number;
    planned_work: number;
    published_work: number;
  };
  sources: Array<{
    code: string;
    label: string;
    state: string;
    last_checked_at?: string | null;
  }>;
  pages: ContentPage[];
  briefs: ContentBrief[];
  work: ContentWork[];
  next_action: { code: string; label: string; detail: string; href?: string | null };
};

type ContentBriefReviewResult = {
  changed: boolean;
  message: string;
  item: ContentBrief;
  safety: {
    brief_evidence_changed: false;
    draft_generated: false;
    publishing_enabled: false;
    website_changed: false;
  };
};

const SAFE_ACTION_PATHS = new Set(["/content#briefs", "/content#pages", "/site-health", "/competitors"]);

function formatDate(value?: string | null) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Saved date unavailable";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function actionLabel(value: string) {
  if (value === "improve_existing_page") return "Improve the existing page";
  if (value === "create_service_page") return "Prepare a new service page";
  return "Review the page choice";
}

function publicationLabel(value: string) {
  if (value === "publish" || value === "public") return "Public page";
  if (value === "draft") return "Saved draft";
  if (value === "private") return "Private page";
  if (value === "needs_attention") return "Page needs attention";
  return value.replaceAll("_", " ");
}

export default function ContentWorkspacePage() {
  const pathname = usePathname();
  const router = useRouter();
  const { campaigns, selectedCampaign, selectedCampaignId, loadingLocations } = useLocationContext();
  const [payload, setPayload] = useState<ContentWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [briefReviewBusy, setBriefReviewBusy] = useState("");
  const [briefReviewMessage, setBriefReviewMessage] = useState("");
  const [briefReviewError, setBriefReviewError] = useState("");

  const loadWorkspace = useCallback(async (campaignId: string, refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const response = (await platformApi(
        `/content/workspace?campaign_id=${encodeURIComponent(campaignId)}`,
      )) as ContentWorkspace;
      setPayload(response);
    } catch {
      setError("The saved content workspace could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedCampaignId) {
      setPayload(null);
      return;
    }
    void loadWorkspace(selectedCampaignId);
  }, [loadWorkspace, selectedCampaignId]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(() => {
    if (error) return [{ label: "Saved content", value: "Needs a reload", tone: "warning" }];
    return [];
  }, [error]);
  const lastSavedAt = useMemo(() => {
    const values = payload?.sources
      .map((source) => source.last_checked_at)
      .filter((value): value is string => Boolean(value)) || [];
    return values.sort().at(-1) || null;
  }, [payload]);
  const firstDraftBrief = payload?.briefs?.find((brief) => brief.status === "draft") || null;
  const firstPageNeedingAttention = payload?.pages?.find((page) => page.attention.length > 0) || null;
  const nextHref = payload?.next_action?.href && SAFE_ACTION_PATHS.has(payload.next_action.href)
    ? payload.next_action.href
    : null;

  function followNextAction() {
    if (!nextHref) return;
    if (nextHref.startsWith("/content#")) {
      document.getElementById(nextHref.split("#")[1])?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    router.push(nextHref);
  }

  async function reviewBrief(brief: ContentBrief, decision: "accept" | "decline") {
    if (!selectedCampaignId || briefReviewBusy) return;
    setBriefReviewBusy(brief.id);
    setBriefReviewMessage("");
    setBriefReviewError("");
    try {
      const result = (await platformApi(`/content/briefs/${encodeURIComponent(brief.id)}/review`, {
        method: "PUT",
        body: JSON.stringify({ campaign_id: selectedCampaignId, decision }),
      })) as ContentBriefReviewResult;
      setBriefReviewMessage(result.message);
      await loadWorkspace(selectedCampaignId, true);
    } catch {
      setBriefReviewError("That brief decision could not be saved. Nothing was changed or published.");
    } finally {
      setBriefReviewBusy("");
    }
  }

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No website"}`
          : "No location selected"
      }
      dateRangeLabel={lastSavedAt ? `Saved ${formatDate(lastSavedAt)}` : "No saved page check"}
      topBarActions={
        <button
          type="button"
          onClick={() => selectedCampaignId && void loadWorkspace(selectedCampaignId, true)}
          disabled={!selectedCampaignId || loading || refreshing}
          className="rounded-md border border-[#2a2b30] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshing ? "Reloading…" : "Reload saved content"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Content"
          title="Plan useful website pages from saved evidence"
          summary="Review saved pages and competitor-backed briefs before writing or changing anything."
        />

        <TruthNotice title="Nothing on this page can publish to your website.">
          This workspace uses saved page checks and confirmed research. A brief is a reviewable plan,
          not proof that a page change will improve rankings.
        </TruthNotice>

        {loading || loadingLocations ? (
          <LoadingCard
            title="Loading saved pages and briefs"
            summary="Checking this location for saved website pages, page issues, and research-backed drafts."
          />
        ) : null}

        {!loading && !loadingLocations && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a location first"
            summary="Content pages and briefs stay separate for every location. Add a location before planning page work."
            actionLabel="Open setup"
            onAction={() => router.push("/dashboard")}
            icon="locations"
          />
        ) : null}

        {error ? (
          <section role="alert" className="border-y border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            <p className="font-semibold">{error}</p>
            <p className="mt-1 text-rose-100/80">
              {payload ? "The last saved workspace remains below." : "Try again later. No missing page is being reported as healthy."}
            </p>
          </section>
        ) : null}

        {!loading && payload ? (
          <OwnerDecisionPanel
            eyebrow="Current content result"
            title={
              firstDraftBrief
                ? `${payload.summary.draft_briefs} content brief${payload.summary.draft_briefs === 1 ? " is" : "s are"} ready for review`
                : firstPageNeedingAttention
                  ? `${payload.summary.pages_needing_attention} page${payload.summary.pages_needing_attention === 1 ? " needs" : "s need"} attention`
                  : payload.summary.pages
                    ? "Saved pages are ready for content planning"
                    : "No saved website pages yet"
            }
            summary={payload.truth.summary}
            nextStep={payload.next_action.detail}
            actionLabel={nextHref ? payload.next_action.label : undefined}
            onAction={nextHref ? followNextAction : undefined}
            tone={firstDraftBrief ? "neutral" : firstPageNeedingAttention ? "warning" : payload.summary.pages ? "positive" : "neutral"}
          />
        ) : null}

        {briefReviewMessage ? (
          <section role="status" className="border-y border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {briefReviewMessage}
          </section>
        ) : null}

        {briefReviewError ? (
          <section role="alert" className="border-y border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {briefReviewError}
          </section>
        ) : null}

        {!loading && payload ? (
          <section aria-label="Saved content facts" className="grid gap-px bg-[#26272c] sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Saved pages"
              value={payload.summary.pages.toLocaleString()}
              summary="Public pages and drafts found in the latest saved website evidence."
              icon="content"
            />
            <KpiCard
              label="Pages needing attention"
              value={payload.summary.pages_needing_attention.toLocaleString()}
              summary="Pages with a clear saved issue such as a missing description or too little useful detail."
              icon="warning"
            />
            <KpiCard
              label="Draft briefs"
              value={payload.summary.draft_briefs.toLocaleString()}
              summary="Research-backed page plans waiting for a person to review."
              icon="reports"
            />
            <KpiCard
              label="Published work"
              value={payload.summary.published_work.toLocaleString()}
              summary="Saved content work already marked as published in InsightOS."
              icon="check"
            />
          </section>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="Content briefs ready for review"
            summary="Each brief starts from one confirmed customer search and competitor gap."
            icon="reports"
          >
            <div id="briefs" className="scroll-mt-24">
              {payload.briefs.length === 0 ? (
                <EmptyState
                  title="No content briefs are saved yet"
                  summary="Confirm real competitors and exact search gaps before creating a review-only page plan."
                  actionLabel="Review competitors"
                  onAction={() => router.push("/competitors")}
                  icon="content"
                />
              ) : (
                <div className="space-y-3">
                  {payload.briefs.map((brief) => (
                    <article key={brief.id} className="border-y border-[#2a2b30] bg-white/[0.015] px-4 py-4">
                      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,0.35fr)]">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-full border px-2 py-0.5 text-xs ${
                              brief.status === "accepted"
                                ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                                : brief.status === "declined"
                                  ? "border-zinc-600/50 bg-zinc-800/60 text-zinc-300"
                                  : "border-accent-500/25 bg-accent-500/10 text-accent-100"
                            }`}>
                              {brief.status === "accepted"
                                ? "Page target accepted"
                                : brief.status === "declined"
                                  ? "Brief declined"
                                  : "Draft for review"}
                            </span>
                            <span className="text-xs text-zinc-500">Saved {formatDate(brief.created_at)}</span>
                          </div>
                          <h3 className="mt-2 text-lg font-semibold text-white">{brief.title}</h3>
                          <p className="mt-1 text-sm text-zinc-300">
                            Customer search: <strong className="font-medium text-zinc-100">{brief.primary_search}</strong>
                          </p>
                          <p className="mt-1 text-sm text-zinc-400">
                            {actionLabel(brief.recommended_page_action)}
                            {brief.target_url ? ` · ${brief.target_url}` : ""}
                          </p>
                        </div>
                        <div className="border-t border-[#2a2b30] pt-3 text-sm lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">Saved evidence</p>
                          <p className="mt-2 text-zinc-300">Confirmed competitor: {brief.competitor_domain}</p>
                          <p className="mt-1 text-zinc-400">
                            Their saved position: {brief.evidence.competitor_position ?? "Not available"}
                            {" · "}Your saved position: {brief.evidence.owner_position ?? "Not found"}
                          </p>
                        </div>
                      </div>
                      <DetailsDisclosure
                        label="Review the suggested page outline"
                        summary={`${brief.outline.length} sections based on this exact saved gap.`}
                      >
                        <ol className="space-y-3">
                          {brief.outline.map((section) => (
                            <li key={`${brief.id}-${section.order}`} className="border-l-2 border-accent-500/30 pl-3">
                              <p className="font-medium text-zinc-100">{section.order}. {section.heading}</p>
                              <p className="mt-1 text-sm leading-5 text-zinc-400">{section.guidance}</p>
                            </li>
                          ))}
                        </ol>
                      </DetailsDisclosure>
                      {brief.status === "draft" ? (
                        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#2a2b30] pt-4">
                          <button
                            type="button"
                            onClick={() => void reviewBrief(brief, "accept")}
                            disabled={Boolean(briefReviewBusy)}
                            className="rounded-md bg-accent-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {briefReviewBusy === brief.id
                              ? "Saving decision…"
                              : brief.recommended_page_action === "create_service_page"
                                ? "Accept new page target"
                                : "Accept page target"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void reviewBrief(brief, "decline")}
                            disabled={Boolean(briefReviewBusy)}
                            className="rounded-md border border-[#34353b] px-3 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Decline brief
                          </button>
                          <p className="text-xs text-zinc-500">
                            Accepting saves the page choice for a later drafting step. It does not write or publish content.
                          </p>
                        </div>
                      ) : brief.status === "accepted" ? (
                        <p className="mt-4 border-t border-[#2a2b30] pt-3 text-sm text-emerald-100">
                          The page choice is saved. Drafting and publishing still require separate steps.
                        </p>
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
          </PageSection>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="Saved website pages"
            summary="Review the clearest saved issues first. A page with no listed issue is not a promise that the page is perfect."
            icon="content"
          >
            <div id="pages" className="scroll-mt-24">
              {payload.pages.length === 0 ? (
                <EmptyState
                  title="No website pages have been saved"
                  summary="Run a website scan or read the connected website before planning page changes."
                  actionLabel="Open Website Health"
                  onAction={() => router.push("/site-health")}
                  icon="website-health"
                />
              ) : (
                <div className="overflow-x-auto border-y border-[#26272c]">
                  <table className="min-w-full border-collapse text-left">
                    <thead className="bg-[#111214]">
                      <tr>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Page</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Saved state</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Needs attention</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payload.pages.map((page) => (
                        <tr key={`${page.source}-${page.id}`} className="border-t border-[#26272c] align-top">
                          <td className="max-w-xl px-4 py-4">
                            <p className="font-medium text-zinc-100">{page.title}</p>
                            <p className="mt-1 break-all text-xs text-zinc-500">{page.url}</p>
                          </td>
                          <td className="whitespace-nowrap px-4 py-4 text-sm text-zinc-300">
                            <p>{publicationLabel(page.publication_state)}</p>
                            <p className="mt-1 text-xs text-zinc-500">{page.source_label} · {formatDate(page.last_checked_at)}</p>
                          </td>
                          <td className="px-4 py-4 text-sm">
                            {page.attention.length ? (
                              <ul className="space-y-1.5 text-amber-100">
                                {page.attention.map((item) => (
                                  <li key={item} className="flex gap-2">
                                    <ProductIcon name="warning" size={15} className="mt-0.5 shrink-0" />
                                    <span>{item}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-zinc-400">No clear issue in this saved check</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </PageSection>
        ) : null}

        {!loading && payload?.work.length ? (
          <PageSection
            title="Saved content work"
            summary="This is the current InsightOS work status. Publishing still requires the separate approved website workflow."
            icon="calendar"
          >
            <ul className="divide-y divide-[#26272c] border-y border-[#26272c]">
              {payload.work.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <p className="font-medium text-zinc-100">{item.title}</p>
                    <p className="mt-1 text-xs text-zinc-500">Updated {formatDate(item.updated_at)}</p>
                  </div>
                  <span className="rounded-full border border-[#34353b] px-2.5 py-1 text-xs capitalize text-zinc-300">
                    {item.status}
                  </span>
                </li>
              ))}
            </ul>
          </PageSection>
        ) : null}

        {!loading && payload?.truth.limitations.length ? (
          <details className="border-y border-[#26272c] bg-[#111214] px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-200">What this workspace does not prove</summary>
            <ul className="mt-3 space-y-2 text-sm leading-5 text-zinc-400">
              {payload.truth.limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}
            </ul>
          </details>
        ) : null}
      </section>
    </AppShell>
  );
}
