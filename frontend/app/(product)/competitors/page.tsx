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
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = { id: string; name?: string; domain?: string };

type Competitor = {
  id: string;
  campaign_id: string;
  domain: string;
  label?: string | null;
  discovery_source: "manual" | "search_overlap" | string;
  review_status: "suggested" | "confirmed" | string;
  overlap_count?: number | null;
  average_position?: number | null;
  estimated_traffic?: number | null;
  last_observed_at?: string | null;
  created_at: string;
};

type ContentBrief = {
  id: string;
  status: "draft" | string;
  title: string;
  primary_keyword: string;
  recommended_page_action: "improve_existing_page" | "create_service_page" | string;
  target_url?: string | null;
  competitor_domain: string;
  competitor_url?: string | null;
  service_name?: string | null;
  service_area_name?: string | null;
  outline: Array<{ order: number; heading: string; guidance: string }>;
  created_at: string;
};

type GapItem = {
  id: string;
  suggestion_id: string;
  competitor_id: string;
  competitor_domain: string;
  competitor_label?: string | null;
  keyword: string;
  gap_type: "not_showing" | "competitor_ahead";
  competitor_position: number;
  previous_competitor_position?: number | null;
  competitor_position_change?: number | null;
  movement_direction?: "up" | "down" | "steady" | "unavailable";
  movement_label?: string | null;
  movement_alert?: boolean;
  previous_source_updated_at?: string | null;
  content_brief?: ContentBrief | null;
  competitor_url?: string | null;
  owner_position?: number | null;
  owner_url?: string | null;
  page_status: "existing" | "needs_page" | "review" | string;
  page_reason?: string | null;
  search_volume?: number | null;
  matched_service_name?: string | null;
  matched_service_area_name?: string | null;
  opportunity_score: number;
  next_step: string;
  source_updated_at?: string | null;
};

type ResearchResult = {
  run: {
    id: string;
    status: string;
    location_name: string;
    completed_at?: string | null;
    previous_run_id?: string | null;
    previous_completed_at?: string | null;
  } | null;
  summary: {
    confirmed_competitors: number;
    suggested_competitors: number;
    competitors_with_gaps: number;
    exact_gaps: number;
    not_showing: number;
    competitor_ahead: number;
    movement_alerts: number;
  };
  items: GapItem[];
};

type AuthorityCompetitorMatch = {
  competitor_id: string;
  competitor_domain: string;
  competitor_label?: string | null;
  target_url: string;
  link_type?: string | null;
  dofollow: boolean;
  anchor?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
};

type AuthorityLinkGapItem = {
  id: string;
  referring_domain: string;
  source_url: string;
  source_page_title?: string | null;
  competitor_matches: AuthorityCompetitorMatch[];
  competitor_match_count: number;
  relevance_classification:
    | "service_and_area_match"
    | "service_match"
    | "area_match"
    | "needs_review";
  relevance_label: string;
  matched_services: Array<{ id: string; name: string }>;
  matched_service_areas: Array<{ id: string; name: string; region?: string | null }>;
  relevance_reasons: string[];
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  source_updated_at: string;
  why_it_matters: string;
  next_step: string;
};

type AuthorityGapResearch = {
  run: {
    id: string;
    status: string;
    owner_domain: string;
    competitors: Array<{ id: string; domain: string; label?: string | null }>;
    result_limit: number;
    source_type: "live_link_index" | string;
    observed_at?: string | null;
  } | null;
  summary: {
    exact_pages: number;
    referring_domains: number;
    competitors_compared: number;
    service_and_area_matches?: number;
    service_matches?: number;
    area_matches?: number;
    needs_review?: number;
  };
  items: AuthorityLinkGapItem[];
  truth: { classification: string; summary: string };
};

type AuthorityLinkChangeItem = {
  id: string;
  change_state: "new" | "lost";
  referring_domain: string;
  source_url: string;
  source_page_title?: string | null;
  target_url: string;
  link_type?: string | null;
  dofollow: boolean;
  anchor?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  source_updated_at: string;
  status_label: string;
  why_it_matters: string;
  next_step: string;
  verification_goal: string;
};

type AuthorityLinkChangeResearch = {
  run: {
    id: string;
    status: string;
    owner_domain: string;
    result_limit_per_state: number;
    source_type: "live_link_index" | string;
    observed_at?: string | null;
  } | null;
  summary: {
    new_links: number;
    lost_links: number;
    new_websites: number;
    lost_websites: number;
  };
  new_items: AuthorityLinkChangeItem[];
  lost_items: AuthorityLinkChangeItem[];
  truth: { classification: string; summary: string };
};

type AuthorityInventoryLink = {
  id: string;
  referring_domain: string;
  source_url: string;
  source_page_title?: string | null;
  target_url: string;
  dofollow: boolean;
  anchor?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  source_updated_at: string;
};

type AuthorityUnlinkedMention = {
  id: string;
  referring_domain: string;
  source_url: string;
  source_page_title?: string | null;
  snippet?: string | null;
  mentioned_name: string;
  relevance_classification:
    | "service_and_area_match"
    | "service_match"
    | "area_match"
    | "needs_review";
  relevance_label: string;
  matched_services: Array<{ id: string; name: string }>;
  matched_service_areas: Array<{ id: string; name: string; region?: string | null }>;
  relevance_reasons: string[];
  source_updated_at: string;
  status_label: string;
  why_it_matters: string;
  next_step: string;
};

type AuthorityInventory = {
  run: {
    id: string;
    status: string;
    owner_domain: string;
    business_name: string;
    link_limit: number;
    mention_limit: number;
    observed_at?: string | null;
  } | null;
  summary: {
    incoming_links: number;
    linking_websites: number;
    exact_name_pages_checked: number;
    unlinked_mentions: number;
  };
  links: AuthorityInventoryLink[];
  unlinked_mentions: AuthorityUnlinkedMention[];
  truth: { classification: string; summary: string };
};

type AuthorityOutreachDraft = {
  id: string;
  campaign_id: string;
  recommendation_id?: string | null;
  source_type: "competitor_gap" | "lost_link" | "unlinked_mention";
  source_record_id: string;
  source_url: string;
  target_url: string;
  referring_domain: string;
  source_page_title?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_page_url?: string | null;
  subject: string;
  message_body: string;
  status: "draft" | "reviewed" | "closed";
  status_label: string;
  owner_confirmed_recipient: boolean;
  manual_send_only: boolean;
  send_available: boolean;
  review_checklist: string[];
  updated_at: string;
};

type AuthorityOutreachDrafts = {
  items: AuthorityOutreachDraft[];
  summary: { drafts: number; reviewed: number; closed: number };
  truth: { classification: string; summary: string };
};

type CreditSummary = {
  credits: { remaining: number; blocked: boolean };
  action_prices: Array<{
    code: string;
    credits: number;
    price_type: "up_to" | "per_item" | "fixed_ceiling";
  }>;
};

const EMPTY_RESEARCH: ResearchResult = {
  run: null,
  summary: {
    confirmed_competitors: 0,
    suggested_competitors: 0,
    competitors_with_gaps: 0,
    exact_gaps: 0,
    not_showing: 0,
    competitor_ahead: 0,
    movement_alerts: 0,
  },
  items: [],
};

const EMPTY_AUTHORITY_RESEARCH: AuthorityGapResearch = {
  run: null,
  summary: { exact_pages: 0, referring_domains: 0, competitors_compared: 0 },
  items: [],
  truth: {
    classification: "not_collected",
    summary: "No trusted-link comparison has been run for this location yet.",
  },
};

const EMPTY_AUTHORITY_LINK_CHANGES: AuthorityLinkChangeResearch = {
  run: null,
  summary: { new_links: 0, lost_links: 0, new_websites: 0, lost_websites: 0 },
  new_items: [],
  lost_items: [],
  truth: {
    classification: "not_collected",
    summary: "No website mention history has been checked for this location yet.",
  },
};

const EMPTY_AUTHORITY_INVENTORY: AuthorityInventory = {
  run: null,
  summary: {
    incoming_links: 0,
    linking_websites: 0,
    exact_name_pages_checked: 0,
    unlinked_mentions: 0,
  },
  links: [],
  unlinked_mentions: [],
  truth: {
    classification: "not_collected",
    summary: "No complete website mention inventory has been saved for this location yet.",
  },
};

const EMPTY_AUTHORITY_OUTREACH: AuthorityOutreachDrafts = {
  items: [],
  summary: { drafts: 0, reviewed: 0, closed: 0 },
  truth: {
    classification: "owner_reviewed_workflow",
    summary: "Messages are saved for your review and are never sent automatically.",
  },
};

function formatPosition(value?: number | null) {
  return value == null ? "Not showing" : `#${Math.round(value)}`;
}

function formatDate(value?: string | null) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not checked yet";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function LinkChangeColumn({
  title,
  items,
  emptyMessage,
  busyAction,
  onAddAction,
  onPrepareOutreach,
}: {
  title: string;
  items: AuthorityLinkChangeItem[];
  emptyMessage: string;
  busyAction: string;
  onAddAction?: (item: AuthorityLinkChangeItem) => void;
  onPrepareOutreach?: (item: AuthorityLinkChangeItem) => void;
}) {
  const visibleItems = items.slice(0, 4);
  const remainingItems = items.slice(4);
  const renderItem = (item: AuthorityLinkChangeItem) => (
    <li key={item.id} className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-white">{item.source_page_title || item.referring_domain}</p>
        <span
          className={
            item.change_state === "new"
              ? "text-xs font-semibold text-emerald-300"
              : "text-xs font-semibold text-rose-300"
          }
        >
          {item.status_label}
        </span>
      </div>
      <p className="mt-1 text-sm text-zinc-400">{item.referring_domain}</p>
      <p className="mt-2 text-sm leading-6 text-zinc-300">{item.next_step}</p>
      <p className="mt-1 text-xs leading-5 text-zinc-500">Success check: {item.verification_goal}</p>
      <div className="mt-2 flex flex-wrap gap-3 text-sm">
        <a href={item.source_url} target="_blank" rel="noreferrer" className="text-sky-300 hover:text-sky-200">
          Open source page →
        </a>
        <a href={item.target_url} target="_blank" rel="noreferrer" className="text-sky-300 hover:text-sky-200">
          Open your linked page →
        </a>
      </div>
      {item.change_state === "lost" && onAddAction ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => onAddAction(item)}
            disabled={busyAction !== ""}
            className="rounded-md border border-[#34353a] px-3 py-1.5 text-xs font-medium text-zinc-200 disabled:opacity-50"
          >
            {busyAction === `authority-action:lost_link:${item.id}` ? "Adding..." : "Add to Next Steps"}
          </button>
          {onPrepareOutreach ? (
            <button
              onClick={() => onPrepareOutreach(item)}
              disabled={busyAction !== ""}
              className="rounded-md border border-sky-500/40 px-3 py-1.5 text-xs font-medium text-sky-200 disabled:opacity-50"
            >
              {busyAction === `authority-outreach:lost_link:${item.id}`
                ? "Preparing..."
                : "Prepare recovery message"}
            </button>
          ) : null}
        </div>
      ) : null}
      <p className="mt-2 text-xs text-zinc-500">
        First found {formatDate(item.first_seen_at)} · Last found {formatDate(item.last_seen_at)}
      </p>
    </li>
  );

  return (
    <div>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {visibleItems.length ? (
        <>
          <ul className="mt-2 divide-y divide-[#26272c]">{visibleItems.map(renderItem)}</ul>
          {remainingItems.length ? (
            <DetailsDisclosure
              label={`Show ${remainingItems.length} more`}
              summary="Open the remaining saved pages from this check."
            >
              <ul className="divide-y divide-[#26272c]">{remainingItems.map(renderItem)}</ul>
            </DetailsDisclosure>
          ) : null}
        </>
      ) : (
        <p className="mt-3 text-sm leading-6 text-zinc-500">{emptyMessage}</p>
      )}
    </div>
  );
}

export default function CompetitorsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [research, setResearch] = useState<ResearchResult>(EMPTY_RESEARCH);
  const [authorityResearch, setAuthorityResearch] = useState<AuthorityGapResearch>(EMPTY_AUTHORITY_RESEARCH);
  const [authorityLinkChanges, setAuthorityLinkChanges] = useState<AuthorityLinkChangeResearch>(
    EMPTY_AUTHORITY_LINK_CHANGES,
  );
  const [authorityInventory, setAuthorityInventory] = useState<AuthorityInventory>(
    EMPTY_AUTHORITY_INVENTORY,
  );
  const [authorityOutreach, setAuthorityOutreach] = useState<AuthorityOutreachDrafts>(
    EMPTY_AUTHORITY_OUTREACH,
  );
  const [creditSummary, setCreditSummary] = useState<CreditSummary | null>(null);
  const [newDomain, setNewDomain] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
    const response = await platformApi("/campaigns", { method: "GET" });
    const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
    setCampaigns(items);
    setSelectedCampaignId((current) =>
      current && items.some((item) => item.id === current) ? current : items[0]?.id || "",
    );
    return items;
  }, [setSelectedCampaignId]);

  const loadLocation = useCallback(async (campaignId: string) => {
    if (!campaignId) return;
    const [
      competitorResponse,
      researchResponse,
      authorityResponse,
      authorityChangeResponse,
      authorityInventoryResponse,
      authorityOutreachResponse,
    ] = await Promise.all([
      platformApi(`/competitors?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/competitors/research?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/authority/link-gaps?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/authority/link-changes?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/authority/inventory?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/authority/outreach-drafts?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
    ]);
    setCompetitors(
      Array.isArray(competitorResponse?.items) ? (competitorResponse.items as Competitor[]) : [],
    );
    setResearch((researchResponse as ResearchResult) || EMPTY_RESEARCH);
    setAuthorityResearch((authorityResponse as AuthorityGapResearch) || EMPTY_AUTHORITY_RESEARCH);
    setAuthorityLinkChanges(
      (authorityChangeResponse as AuthorityLinkChangeResearch) || EMPTY_AUTHORITY_LINK_CHANGES,
    );
    setAuthorityInventory(
      (authorityInventoryResponse as AuthorityInventory) || EMPTY_AUTHORITY_INVENTORY,
    );
    setAuthorityOutreach(
      (authorityOutreachResponse as AuthorityOutreachDrafts) || EMPTY_AUTHORITY_OUTREACH,
    );
  }, []);

  const loadCredits = useCallback(async () => {
    try {
      const response = (await platformApi("/usage/credits", { method: "GET" })) as CreditSummary;
      setCreditSummary(response);
    } catch {
      setCreditSummary(null);
    }
  }, []);

  async function runAction(name: string, action: () => Promise<void>) {
    setBusyAction(name);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusyAction("");
    }
  }

  async function findCompetitors() {
    if (!selectedCampaignId) return;
    await runAction("discover", async () => {
      const response = await platformApi("/competitors/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, limit: 12 }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(
        response?.suggestions_found
          ? `Found ${response.suggestions_found} possible competitors. Confirm only the businesses customers truly compare with you.`
          : "No new competitors were found from the available search overlap.",
      );
    });
  }

  async function confirmCompetitor(item: Competitor) {
    if (!selectedCampaignId) return;
    await runAction(`confirm:${item.id}`, async () => {
      await platformApi("/competitors", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          domain: item.domain,
          label: item.label || null,
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(`${item.label || item.domain} is now included in competitor research.`);
    });
  }

  async function dismissCompetitor(item: Competitor) {
    if (!selectedCampaignId) return;
    await runAction(`dismiss:${item.id}`, async () => {
      await platformApi("/competitors/review", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          competitor_id: item.id,
          decision: "dismissed",
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(`${item.label || item.domain} was removed from this location’s suggestions.`);
    });
  }

  async function addCompetitor() {
    if (!selectedCampaignId || !newDomain.trim()) return;
    await runAction("add", async () => {
      await platformApi("/competitors", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          domain: newDomain.trim(),
          label: newLabel.trim() || null,
        }),
      });
      setNewDomain("");
      setNewLabel("");
      await loadLocation(selectedCampaignId);
      setNotice("Competitor added. Refresh the search comparison to find exact gaps.");
    });
  }

  async function trackGap(item: GapItem) {
    if (!selectedCampaignId) return;
    await runAction(`track:${item.id}`, async () => {
      const response = await platformApi("/keyword-research/track", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [item.suggestion_id],
        }),
      });
      setNotice(
        response?.created_count
          ? `“${item.keyword}” is now in Search Rankings.`
          : `“${item.keyword}” was already in Search Rankings.`,
      );
    });
  }

  async function addGapToNextSteps(item: GapItem) {
    if (!selectedCampaignId) return;
    await runAction(`action:${item.id}`, async () => {
      const response = await platformApi("/keyword-research/create-action", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [item.suggestion_id],
        }),
      });
      setNotice(response?.message || `“${item.keyword}” is ready to review in Next Steps.`);
    });
  }

  async function createContentBrief(item: GapItem) {
    if (!selectedCampaignId) return;
    await runAction(`brief:${item.id}`, async () => {
      const response = await platformApi("/competitors/content-brief", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_id: item.suggestion_id,
          competitor_id: item.competitor_id,
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(response?.message || `Draft brief saved for “${item.keyword}.” Nothing was published.`);
    });
  }

  async function refreshComparison() {
    if (!selectedCampaignId) return;
    await runAction("refresh", async () => {
      await platformApi("/keyword-research/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, max_suggestions: 75 }),
      });
      await loadLocation(selectedCampaignId);
      setNotice("The comparison now uses the latest searches available for this location.");
    });
  }

  async function refreshAuthorityGaps() {
    if (!selectedCampaignId) return;
    await runAction("authority-gaps", async () => {
      const response = await platformApi("/authority/link-gaps/refresh", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          idempotency_key: `authority-gap:${selectedCampaignId}:${Date.now()}`,
        }),
      });
      setAuthorityResearch((response as AuthorityGapResearch) || EMPTY_AUTHORITY_RESEARCH);
      await loadCredits();
      setNotice(
        response?.summary?.exact_pages
          ? `Found ${response.summary.exact_pages} exact page${response.summary.exact_pages === 1 ? "" : "s"} worth reviewing.`
          : "No competitor-only website mentions were found in this check.",
      );
    });
  }

  async function refreshAuthorityLinkChanges() {
    if (!selectedCampaignId) return;
    await runAction("authority-link-changes", async () => {
      const response = await platformApi("/authority/link-changes/refresh", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          idempotency_key: `authority-link-changes:${selectedCampaignId}:${Date.now()}`,
        }),
      });
      setAuthorityLinkChanges(
        (response as AuthorityLinkChangeResearch) || EMPTY_AUTHORITY_LINK_CHANGES,
      );
      await loadCredits();
      const totalChanges = Number(response?.summary?.new_links || 0) + Number(response?.summary?.lost_links || 0);
      setNotice(
        totalChanges
          ? `Saved ${totalChanges} exact website mention change${totalChanges === 1 ? "" : "s"} for review.`
          : "No newly found or lost website mentions were returned in this check.",
      );
    });
  }

  async function refreshAuthorityInventory() {
    if (!selectedCampaignId || businessName.trim().length < 2) return;
    await runAction("authority-inventory", async () => {
      const response = await platformApi("/authority/inventory/refresh", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          business_name: businessName.trim(),
          idempotency_key: `authority-inventory:${selectedCampaignId}:${Date.now()}`,
        }),
      });
      setAuthorityInventory((response as AuthorityInventory) || EMPTY_AUTHORITY_INVENTORY);
      await loadCredits();
      setNotice(
        response?.summary?.unlinked_mentions
          ? `Saved ${response.summary.incoming_links} incoming links and ${response.summary.unlinked_mentions} possible mention${response.summary.unlinked_mentions === 1 ? "" : "s"} to review.`
          : `Saved ${response?.summary?.incoming_links || 0} incoming links. No exact-name pages without a link were confirmed in this check.`,
      );
    });
  }

  async function addAuthorityAction(
    sourceType: "competitor_gap" | "lost_link" | "unlinked_mention",
    item: AuthorityLinkGapItem | AuthorityLinkChangeItem | AuthorityUnlinkedMention,
  ) {
    if (!selectedCampaignId) return;
    await runAction(`authority-action:${sourceType}:${item.id}`, async () => {
      const response = await platformApi("/authority/actions", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          source_type: sourceType,
          source_id: item.id,
          owner_confirmed_relevant:
            sourceType !== "lost_link" &&
            "relevance_classification" in item &&
            item.relevance_classification === "needs_review",
        }),
      });
      setNotice(response?.message || "The website follow-up is ready to review in Next Steps.");
    });
  }

  async function prepareAuthorityOutreach(
    sourceType: "competitor_gap" | "lost_link" | "unlinked_mention",
    item: AuthorityLinkGapItem | AuthorityLinkChangeItem | AuthorityUnlinkedMention,
  ) {
    if (!selectedCampaignId) return;
    await runAction(`authority-outreach:${sourceType}:${item.id}`, async () => {
      const response = await platformApi("/authority/outreach-drafts", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          source_type: sourceType,
          source_id: item.id,
          owner_confirmed_relevant:
            sourceType !== "lost_link" &&
            "relevance_classification" in item &&
            item.relevance_classification === "needs_review",
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(response?.message || "A review-only message is ready below. Nothing was sent.");
      window.setTimeout(
        () => document.getElementById("authority-outreach-drafts")?.scrollIntoView({ behavior: "smooth" }),
        50,
      );
    });
  }

  function changeOutreachDraft(
    draftId: string,
    field: "contact_name" | "contact_email" | "contact_page_url" | "subject" | "message_body",
    value: string,
  ) {
    setAuthorityOutreach((current) => {
      const items: AuthorityOutreachDraft[] = current.items.map((item) =>
        item.id === draftId
          ? {
              ...item,
              [field]: value,
              status: "draft" as const,
              status_label: "Needs your review",
              owner_confirmed_recipient: false,
            }
          : item,
      );
      return {
        ...current,
        items,
        summary: {
          drafts: items.filter((item) => item.status === "draft").length,
          reviewed: items.filter((item) => item.status === "reviewed").length,
          closed: items.filter((item) => item.status === "closed").length,
        },
      };
    });
  }

  async function saveOutreachDraft(
    draft: AuthorityOutreachDraft,
    status: "draft" | "reviewed" | "closed",
  ) {
    if (!selectedCampaignId) return;
    await runAction(`authority-outreach-save:${draft.id}`, async () => {
      const response = await platformApi(`/authority/outreach-drafts/${encodeURIComponent(draft.id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          contact_name: draft.contact_name || null,
          contact_email: draft.contact_email || null,
          contact_page_url: draft.contact_page_url || null,
          subject: draft.subject,
          message_body: draft.message_body,
          status,
          owner_confirmed_recipient: status === "reviewed",
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(response?.message || "The message was saved. Nothing was sent.");
    });
  }

  async function copyOutreachDraft(draft: AuthorityOutreachDraft) {
    setError("");
    try {
      await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.message_body}`);
      setNotice("Message copied. InsightOS did not send it.");
    } catch {
      setError("Unable to copy automatically. Select the message text and copy it manually.");
    }
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        const [items] = await Promise.all([loadCampaigns(), loadCredits()]);
        if (items[0]?.id) await loadLocation(items[0].id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load competitor research.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadCampaigns, loadCredits, loadLocation]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setError("");
    setNotice("");
    void loadLocation(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to change locations.");
    });
  }, [selectedCampaignId, loading, loadLocation]);

  useEffect(() => {
    const campaign = campaigns.find((item) => item.id === selectedCampaignId);
    setBusinessName(authorityInventory.run?.business_name || campaign?.name || "");
  }, [selectedCampaignId, campaigns, authorityInventory.run?.business_name]);

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId);
  const confirmed = competitors.filter((item) => item.review_status === "confirmed");
  const suggested = competitors.filter((item) => item.review_status === "suggested");
  const topGap = research.items[0];
  const discoveryCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "competitor_discovery",
  );
  const authorityCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "authority_link_gap_refresh",
  );
  const authorityChangeCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "authority_link_change_refresh",
  );
  const authorityInventoryCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "authority_inventory_refresh",
  );
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals: TrustSignal[] = [
    {
      label: "Location",
      value: selectedCampaign?.name || "Choose a location",
      tone: selectedCampaign ? "success" : "warning",
    },
    {
      label: "Competitors confirmed",
      value: String(confirmed.length),
      tone: confirmed.length ? "success" : "warning",
    },
    {
      label: "Search comparison",
      value: research.run ? formatDate(research.run.completed_at) : "Not run",
      tone: research.run ? "success" : "warning",
    },
  ];

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed business"} / ${selectedCampaign.domain || "No website"}`
          : "No business selected"
      }
      dateRangeLabel="Latest saved comparison"
      topBarActions={
        <button
          onClick={() => router.push("/keyword-research")}
          className="rounded-md border border-[#2f3035] px-3 py-1.5 text-sm text-zinc-200"
        >
          Find searches
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Competitors"
          title="See who is winning the searches you want"
          summary="Find the businesses customers see beside yours, then compare the exact searches and pages where they are ahead."
        />

        {discoveryCreditPrice ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[#26272c] py-3 text-sm">
            <p className="text-zinc-300">
              Finding competitors uses {discoveryCreditPrice.credits} Insight Credits for this location.
            </p>
            <p className="font-semibold text-white">
              {creditSummary?.credits.remaining.toLocaleString()} available
            </p>
          </div>
        ) : null}

        <TruthNotice title="Choose competitors customers would actually hire.">
          Search overlap is only a starting clue. Confirm local businesses that sell the same work
          in the same area before using their pages to plan improvements.
        </TruthNotice>

        {loading ? (
          <LoadingCard title="Loading competitor research" summary="Checking this location’s saved comparisons." />
        ) : null}
        {error ? (
          <div className="rounded-md border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-100">{error}</div>
        ) : null}
        {notice ? (
          <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 p-4 text-sm text-emerald-100">{notice}</div>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a business first"
            summary="Competitor research needs a website and location before it can compare search results."
            actionLabel="Go to setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <OwnerDecisionPanel
              title={
                topGap
                  ? `${topGap.competitor_label || topGap.competitor_domain} is ahead for “${topGap.keyword}”`
                  : suggested.length
                    ? `Review ${suggested.length} possible competitor${suggested.length === 1 ? "" : "s"}`
                    : confirmed.length
                      ? "Refresh the searches to build a current comparison"
                      : "Find the businesses customers see beside yours"
              }
              summary={
                topGap
                  ? `They appear around ${formatPosition(topGap.competitor_position)}. Your website is ${topGap.owner_position == null ? "not showing in the saved results" : `around ${formatPosition(topGap.owner_position)}`}.`
                  : suggested.length
                    ? "Search overlap can include directories and national websites. Confirm only businesses that truly compete for the same customers."
                    : "InsightOS will suggest likely competitors from real search overlap. You decide which ones belong in the comparison."
              }
              nextStep={
                topGap
                  ? topGap.next_step
                  : suggested.length
                    ? "Confirm the closest local competitors below."
                    : confirmed.length
                      ? "Run a fresh search comparison."
                      : "Run the first competitor search."
              }
              actionLabel={
                suggested.length ? "Review suggestions" : confirmed.length ? "Refresh comparison" : "Find competitors"
              }
              onAction={() => {
                if (suggested.length) {
                  document.getElementById("competitor-suggestions")?.scrollIntoView({ behavior: "smooth" });
                } else if (confirmed.length) {
                  void refreshComparison();
                } else {
                  void findCompetitors();
                }
              }}
              tone={topGap ? "warning" : "neutral"}
            />

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="Real competitors confirmed"
                value={String(research.summary.confirmed_competitors)}
                summary="Businesses included in this location’s comparison."
              />
              <KpiCard
                label="Searches where they lead"
                value={String(research.summary.exact_gaps)}
                summary="Exact, relevant searches backed by a saved result."
                tone={research.summary.exact_gaps ? "highlight" : undefined}
              />
              <KpiCard
                label="Searches where you are absent"
                value={String(research.summary.not_showing)}
                summary="Confirmed competitor searches where your website was not found."
              />
              <KpiCard
                label="Competitor movement alerts"
                value={String(research.summary.movement_alerts)}
                summary="Competitors that moved by at least three places since the earlier matching check."
                tone={research.summary.movement_alerts ? "highlight" : undefined}
              />
            </div>

            <section id="competitor-suggestions" className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Who customers compare</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Choose your real competitors</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Shared searches are a clue, not a final decision. Confirm local businesses that sell the same work in the same area.
                  </p>
                </div>
                <button
                  onClick={() => void findCompetitors()}
                  disabled={busyAction !== "" || creditSummary?.credits.blocked}
                  className="rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {busyAction === "discover" ? "Finding competitors…" : "Find competitors"}
                </button>
              </div>

              {suggested.length ? (
                <div className="mt-5 grid gap-3 lg:grid-cols-2">
                  {suggested.map((item) => (
                    <article key={item.id} className="rounded-md border border-[#2b2c31] bg-[#121315] p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="font-semibold text-white">{item.label || item.domain}</h3>
                          <p className="mt-1 text-sm text-zinc-400">{item.domain}</p>
                        </div>
                        <span className="rounded-full bg-sky-500/10 px-2.5 py-1 text-xs text-sky-200">
                          {item.overlap_count || 0} shared searches
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-zinc-300">
                        This website repeatedly appears for searches also tied to your website. Confirm it only if it serves the same customers.
                      </p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          onClick={() => void confirmCompetitor(item)}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-100 disabled:opacity-50"
                        >
                          {busyAction === `confirm:${item.id}` ? "Confirming…" : "Yes, this is a competitor"}
                        </button>
                        <button
                          onClick={() => void dismissCompetitor(item)}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-[#303137] px-3 py-2 text-sm text-zinc-300 disabled:opacity-50"
                        >
                          {busyAction === `dismiss:${item.id}` ? "Removing…" : "Not a competitor"}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="mt-5 text-sm text-zinc-400">
                  No unreviewed suggestions. Run the check when you want to look for more.
                </p>
              )}

              {confirmed.length ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  {confirmed.map((item) => (
                    <span key={item.id} className="rounded-full border border-[#303137] px-3 py-1.5 text-sm text-zinc-200">
                      {item.label || item.domain}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Who mentions your business
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Links you have and mentions to review</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Save exact pages that link to your website. We also check exact-name mentions and only flag a page when no link from that same page was found in the same check.
                  </p>
                </div>
                <div className="flex w-full max-w-xl flex-col gap-2 sm:flex-row">
                  <label className="flex-1 text-xs text-zinc-400">
                    Exact business name
                    <input
                      value={businessName}
                      onChange={(event) => setBusinessName(event.target.value)}
                      placeholder="Name customers see"
                      className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                    />
                  </label>
                  <button
                    onClick={() => void refreshAuthorityInventory()}
                    disabled={
                      busyAction !== "" ||
                      !selectedCampaignId ||
                      businessName.trim().length < 2 ||
                      creditSummary?.credits.blocked
                    }
                    className="self-end rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                  >
                    {busyAction === "authority-inventory"
                      ? "Checking…"
                      : authorityInventoryCreditPrice
                        ? `Check mentions · ${authorityInventoryCreditPrice.credits} credits`
                        : "Check mentions"}
                  </button>
                </div>
              </div>

              {authorityInventory.run ? (
                <>
                  <div className="mt-5 grid border-y border-[#26272c] sm:grid-cols-4">
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:pr-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Incoming links saved</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityInventory.summary.incoming_links}</p>
                    </div>
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:px-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Linking websites</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityInventory.summary.linking_websites}</p>
                    </div>
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:px-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Name matches checked</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityInventory.summary.exact_name_pages_checked}</p>
                    </div>
                    <div className="py-4 sm:pl-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Possible missing links</p>
                      <p className="mt-1 text-2xl font-semibold text-amber-200">{authorityInventory.summary.unlinked_mentions}</p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-zinc-500">
                    {authorityInventory.truth.summary} Checked {formatDate(authorityInventory.run.observed_at)}.
                  </p>

                  <div className="mt-5">
                    <h3 className="font-semibold text-white">Mentions worth checking</h3>
                    {authorityInventory.unlinked_mentions.length ? (
                      <ol className="mt-3 divide-y divide-[#26272c] border-y border-[#26272c]">
                        {authorityInventory.unlinked_mentions.map((item, index) => (
                          <li key={item.id} className="grid gap-4 py-5 lg:grid-cols-[2rem_1fr_1.35fr]">
                            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-sm font-semibold text-amber-200">
                              {index + 1}
                            </div>
                            <div>
                              <p className="font-semibold text-white">{item.source_page_title || item.referring_domain}</p>
                              <p className="mt-1 text-sm text-zinc-400">{item.referring_domain}</p>
                              <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-sky-300 hover:text-sky-200">
                                Open the exact page →
                              </a>
                              {item.snippet ? <p className="mt-2 text-xs leading-5 text-zinc-500">“{item.snippet}”</p> : null}
                            </div>
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${item.relevance_classification === "needs_review" ? "bg-amber-500/10 text-amber-200" : "bg-emerald-500/10 text-emerald-200"}`}>
                                  {item.relevance_label}
                                </span>
                                {[...item.matched_services, ...item.matched_service_areas].map((match) => (
                                  <span key={`${item.id}-${match.id}`} className="text-xs text-zinc-500">{match.name}</span>
                                ))}
                              </div>
                              <p className="mt-2 text-sm leading-6 text-zinc-300">{item.why_it_matters}</p>
                              <p className="mt-2 text-sm font-medium leading-6 text-white">{item.next_step}</p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                  onClick={() => void addAuthorityAction("unlinked_mention", item)}
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-[#34353a] px-3 py-1.5 text-xs font-medium text-zinc-200 disabled:opacity-50"
                                >
                                  {busyAction === `authority-action:unlinked_mention:${item.id}`
                                    ? "Adding..."
                                    : item.relevance_classification === "needs_review"
                                      ? "Confirm and add to Next Steps"
                                      : "Add to Next Steps"}
                                </button>
                                <button
                                  onClick={() => void prepareAuthorityOutreach("unlinked_mention", item)}
                                  disabled={busyAction !== ""}
                                  className="rounded-md border border-sky-500/40 px-3 py-1.5 text-xs font-medium text-sky-200 disabled:opacity-50"
                                >
                                  {busyAction === `authority-outreach:unlinked_mention:${item.id}`
                                    ? "Preparing..."
                                    : item.relevance_classification === "needs_review"
                                      ? "Confirm and prepare a message"
                                      : "Prepare a message"}
                                </button>
                              </div>
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="mt-3 text-sm leading-6 text-zinc-400">
                        No exact-name pages without a website link were confirmed in this check.
                      </p>
                    )}
                  </div>

                  <DetailsDisclosure
                    label={`See ${authorityInventory.links.length} saved incoming link${authorityInventory.links.length === 1 ? "" : "s"}`}
                    summary="Open the exact source and destination pages behind the inventory."
                  >
                    {authorityInventory.links.length ? (
                      <ul className="divide-y divide-[#26272c]">
                        {authorityInventory.links.map((item) => (
                          <li key={item.id} className="grid gap-3 py-4 md:grid-cols-[1fr_1fr_auto]">
                            <div>
                              <p className="font-medium text-white">{item.source_page_title || item.referring_domain}</p>
                              <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-sky-300 hover:text-sky-200">Open source page →</a>
                            </div>
                            <div>
                              <p className="text-xs uppercase tracking-[0.12em] text-zinc-500">Links to</p>
                              <a href={item.target_url} target="_blank" rel="noreferrer" className="mt-1 inline-block break-all text-sm text-zinc-300 hover:text-white">{item.target_url}</a>
                            </div>
                            <div className="text-xs text-zinc-500">
                              <p>{item.dofollow ? "Standard link" : "Link marked not to pass ranking credit"}</p>
                              <p className="mt-1">Last seen {formatDate(item.last_seen_at || item.source_updated_at)}</p>
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-zinc-400">No incoming links were returned in this saved check.</p>
                    )}
                  </DetailsDisclosure>
                </>
              ) : (
                <div className="mt-5">
                  <EmptyState
                    title="Build the first complete mention list"
                    summary="Confirm the exact business name, then run one bounded check for incoming links and possible missing links."
                    actionLabel="Check mentions"
                    onAction={() => void refreshAuthorityInventory()}
                  />
                </div>
              )}
            </section>

            <section className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Links to your website</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">What changed with website mentions</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    See exact pages that recently started linking to your website and links reported as gone. Each result includes what to check and how to know the follow-up worked.
                  </p>
                </div>
                <button
                  onClick={() => void refreshAuthorityLinkChanges()}
                  disabled={busyAction !== "" || !selectedCampaignId || creditSummary?.credits.blocked}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "authority-link-changes"
                    ? "Checking…"
                    : authorityChangeCreditPrice
                      ? `Check changes · ${authorityChangeCreditPrice.credits} credits`
                      : "Check changes"}
                </button>
              </div>

              {authorityLinkChanges.run ? (
                <>
                  <div className="mt-5 grid border-y border-[#26272c] sm:grid-cols-2">
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:pr-5">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">New links found</p>
                      <p className="mt-1 text-2xl font-semibold text-emerald-300">{authorityLinkChanges.summary.new_links}</p>
                      <p className="mt-1 text-xs text-zinc-500">From {authorityLinkChanges.summary.new_websites} websites</p>
                    </div>
                    <div className="py-4 sm:pl-5">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Links reported gone</p>
                      <p className="mt-1 text-2xl font-semibold text-rose-300">{authorityLinkChanges.summary.lost_links}</p>
                      <p className="mt-1 text-xs text-zinc-500">From {authorityLinkChanges.summary.lost_websites} websites</p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-zinc-500">
                    {authorityLinkChanges.truth.summary} Checked {formatDate(authorityLinkChanges.run.observed_at)}.
                  </p>
                  <div className="mt-4 grid gap-6 lg:grid-cols-2">
                    <LinkChangeColumn
                      title="New links to review"
                      items={authorityLinkChanges.new_items}
                      emptyMessage="No newly found links were returned in this check."
                      busyAction={busyAction}
                    />
                    <LinkChangeColumn
                      title="Lost links to investigate"
                      items={authorityLinkChanges.lost_items}
                      emptyMessage="No lost links were returned in this check."
                      busyAction={busyAction}
                      onAddAction={(item) => void addAuthorityAction("lost_link", item)}
                      onPrepareOutreach={(item) => void prepareAuthorityOutreach("lost_link", item)}
                    />
                  </div>
                </>
              ) : (
                <div className="mt-5">
                  <EmptyState
                    title="Check what changed"
                    summary="Run one bounded check to save exact new and lost website mentions for this location."
                    actionLabel="Check changes"
                    onAction={() => void refreshAuthorityLinkChanges()}
                  />
                </div>
              )}
            </section>

            <section className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Where to catch up</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Exact searches and competing pages</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Every item names the search, both saved positions, and the competing page when one was available. No made-up gap score is used.
                  </p>
                </div>
                <button
                  onClick={() => void refreshComparison()}
                  disabled={busyAction !== "" || confirmed.length === 0}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "refresh" ? "Refreshing…" : "Refresh comparison"}
                </button>
              </div>

              {research.items.length ? (
                <div className="mt-5 divide-y divide-[#26272c] border-y border-[#26272c]">
                  {research.items.map((item, index) => (
                    <article key={item.id} className="grid gap-4 py-5 lg:grid-cols-[2rem_1.1fr_.8fr_1.2fr]">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-500/15 text-sm font-semibold text-orange-200">
                        {index + 1}
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">{item.keyword}</h3>
                        <p className="mt-1 text-sm text-zinc-400">
                          {[item.matched_service_name, item.matched_service_area_name].filter(Boolean).join(" · ") || "Confirmed relevant search"}
                        </p>
                        {item.search_volume != null ? (
                          <p className="mt-1 text-xs text-zinc-500">About {item.search_volume.toLocaleString()} searches in the saved market data</p>
                        ) : null}
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Your site</p>
                          <p className="mt-1 font-semibold text-white">{formatPosition(item.owner_position)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Competitor</p>
                          <p className="mt-1 font-semibold text-orange-200">{formatPosition(item.competitor_position)}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{item.competitor_label || item.competitor_domain}</p>
                        {item.previous_competitor_position != null && item.movement_label ? (
                          <p
                            className={`mt-1 text-sm font-medium ${
                              item.movement_direction === "up"
                                ? "text-orange-200"
                                : item.movement_direction === "down"
                                  ? "text-emerald-300"
                                  : "text-zinc-400"
                            }`}
                          >
                            {item.movement_label} Earlier: {formatPosition(item.previous_competitor_position)}.
                          </p>
                        ) : null}
                        <p className="mt-1 text-sm leading-6 text-zinc-300">{item.next_step}</p>
                        <p className="mt-1 text-xs leading-5 text-zinc-500">
                          {item.page_status === "existing"
                            ? "A likely page on your website was found."
                            : item.page_status === "needs_page"
                              ? "No saved page clearly covers this customer need yet."
                              : item.page_reason || "The best website page still needs review."}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-3 text-xs">
                          {item.competitor_url ? (
                            <a href={item.competitor_url} target="_blank" rel="noreferrer" className="text-sky-300 hover:text-sky-200">
                              Open their page ↗
                            </a>
                          ) : null}
                          {item.owner_url ? (
                            <a href={item.owner_url} target="_blank" rel="noreferrer" className="text-zinc-300 hover:text-white">
                              Open your page ↗
                            </a>
                          ) : null}
                          <span className="text-zinc-500">Checked {formatDate(item.source_updated_at)}</span>
                          {item.previous_source_updated_at && item.previous_competitor_position != null ? (
                            <span className="text-zinc-500">Earlier check {formatDate(item.previous_source_updated_at)}</span>
                          ) : null}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => void trackGap(item)}
                            disabled={busyAction !== ""}
                            className="rounded-md border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-100 disabled:opacity-50"
                          >
                            {busyAction === `track:${item.id}` ? "Adding…" : "Track this search"}
                          </button>
                          <button
                            onClick={() => void addGapToNextSteps(item)}
                            disabled={busyAction !== ""}
                            className="rounded-md border border-[#34353a] px-3 py-1.5 text-xs font-medium text-zinc-200 disabled:opacity-50"
                          >
                            {busyAction === `action:${item.id}` ? "Adding…" : "Add to Next Steps"}
                          </button>
                          <button
                            onClick={() => void createContentBrief(item)}
                            disabled={busyAction !== "" || Boolean(item.content_brief)}
                            className="rounded-md border border-orange-500/30 bg-orange-500/10 px-3 py-1.5 text-xs font-medium text-orange-100 disabled:opacity-50"
                          >
                            {busyAction === `brief:${item.id}`
                              ? "Saving…"
                              : item.content_brief
                                ? "Brief saved"
                                : "Create content brief"}
                          </button>
                        </div>
                        {item.content_brief ? (
                          <div className="mt-3 rounded-md border border-orange-500/20 bg-orange-500/5 p-3">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div>
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-orange-200">Draft content brief</p>
                                <p className="mt-1 text-sm font-semibold text-white">{item.content_brief.title}</p>
                              </div>
                              <span className="rounded-full border border-[#34353a] px-2 py-1 text-[11px] text-zinc-300">Nothing published</span>
                            </div>
                            <DetailsDisclosure
                              label="Review the outline"
                              summary={`${item.content_brief.outline.length} plain-language sections based on this exact search gap.`}
                            >
                              <ol className="space-y-3">
                                {item.content_brief.outline.map((section) => (
                                  <li key={`${item.content_brief?.id}-${section.order}`} className="text-sm leading-6 text-zinc-300">
                                    <span className="font-semibold text-white">{section.order}. {section.heading}</span>
                                    <span className="block text-zinc-400">{section.guidance}</span>
                                  </li>
                                ))}
                              </ol>
                            </DetailsDisclosure>
                          </div>
                        ) : null}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="mt-5">
                  <EmptyState
                    title={confirmed.length ? "No exact gaps are ready yet" : "Confirm a competitor first"}
                    summary={
                      confirmed.length
                        ? "Refresh the comparison. InsightOS will only show relevant searches with enough evidence to compare."
                        : "Find or add a real competitor, confirm it, then refresh the comparison."
                    }
                    actionLabel={confirmed.length ? "Refresh comparison" : "Find competitors"}
                    onAction={() => void (confirmed.length ? refreshComparison() : findCompetitors())}
                  />
                </div>
              )}
            </section>

            <section className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Where they are mentioned</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Websites that mention competitors, but not you</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    See the exact pages that point customers toward confirmed competitors. Review each page before deciding whether a useful local relationship or resource belongs there too.
                  </p>
                </div>
                <button
                  onClick={() => void refreshAuthorityGaps()}
                  disabled={busyAction !== "" || confirmed.length === 0 || creditSummary?.credits.blocked}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "authority-gaps"
                    ? "Checkingâ€¦"
                    : authorityCreditPrice
                      ? `Check websites Â· ${authorityCreditPrice.credits} credits`
                      : "Check websites"}
                </button>
              </div>

              {authorityResearch.run ? (
                <>
                  <div className="mt-5 grid border-y border-[#26272c] sm:grid-cols-3">
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:pr-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Exact pages</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityResearch.summary.exact_pages}</p>
                    </div>
                    <div className="py-4 sm:border-r sm:border-[#26272c] sm:px-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Different websites</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityResearch.summary.referring_domains}</p>
                    </div>
                    <div className="py-4 sm:pl-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Competitors checked</p>
                      <p className="mt-1 text-2xl font-semibold text-white">{authorityResearch.summary.competitors_compared}</p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-zinc-500">
                    {authorityResearch.truth.summary} Checked {formatDate(authorityResearch.run.observed_at)}.
                  </p>

                  {authorityResearch.items.length ? (
                    <ol className="mt-4 divide-y divide-[#26272c] border-y border-[#26272c]">
                      {authorityResearch.items.map((item, index) => (
                        <li key={item.id} className="grid gap-4 py-5 lg:grid-cols-[2rem_1fr_1.25fr]">
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-sky-500/10 text-sm font-semibold text-sky-200">
                            {index + 1}
                          </div>
                          <div>
                            <p className="font-semibold text-white">{item.source_page_title || item.referring_domain}</p>
                            <p className="mt-1 text-sm text-zinc-400">{item.referring_domain}</p>
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-2 inline-block text-sm text-sky-300 hover:text-sky-200"
                            >
                              Open the exact page â†—
                            </a>
                            <p className="mt-2 text-xs text-zinc-500">
                              Seen {formatDate(item.first_seen_at)} Â· Last checked {formatDate(item.last_seen_at || item.source_updated_at)}
                            </p>
                          </div>
                          <div>
                            <div className="mb-2 flex flex-wrap items-center gap-2">
                              <span
                                className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                                  item.relevance_classification === "needs_review"
                                    ? "bg-amber-500/10 text-amber-200"
                                    : "bg-emerald-500/10 text-emerald-200"
                                }`}
                              >
                                {item.relevance_label}
                              </span>
                              {[...item.matched_services, ...item.matched_service_areas].map((match) => (
                                <span key={`${item.id}-${match.id}`} className="text-xs text-zinc-500">
                                  {match.name}
                                </span>
                              ))}
                            </div>
                            <p className="text-sm leading-6 text-zinc-300">{item.why_it_matters}</p>
                            <p className="mt-2 text-sm font-medium leading-6 text-white">{item.next_step}</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                onClick={() => void addAuthorityAction("competitor_gap", item)}
                                disabled={busyAction !== ""}
                                className="rounded-md border border-[#34353a] px-3 py-1.5 text-xs font-medium text-zinc-200 disabled:opacity-50"
                              >
                                {busyAction === `authority-action:competitor_gap:${item.id}`
                                  ? "Adding..."
                                  : item.relevance_classification === "needs_review"
                                    ? "Confirm and add to Next Steps"
                                    : "Add to Next Steps"}
                              </button>
                              <button
                                onClick={() => void prepareAuthorityOutreach("competitor_gap", item)}
                                disabled={busyAction !== ""}
                                className="rounded-md border border-sky-500/40 px-3 py-1.5 text-xs font-medium text-sky-200 disabled:opacity-50"
                              >
                                {busyAction === `authority-outreach:competitor_gap:${item.id}`
                                  ? "Preparing..."
                                  : item.relevance_classification === "needs_review"
                                    ? "Confirm and prepare a message"
                                    : "Prepare a message"}
                              </button>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.competitor_matches.map((match) => (
                                <a
                                  key={`${item.id}-${match.competitor_id}-${match.target_url}`}
                                  href={match.target_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="rounded-full border border-[#34353a] px-2.5 py-1 text-xs text-zinc-300 hover:text-white"
                                >
                                  {match.competitor_label || match.competitor_domain} target page â†—
                                </a>
                              ))}
                            </div>
                            <DetailsDisclosure
                              label="See what was verified"
                              summary="The saved source page, competitor destination, and observation dates are kept together."
                            >
                              <ul className="space-y-2 text-sm leading-6 text-zinc-300">
                                {item.competitor_matches.map((match) => (
                                  <li key={`evidence-${item.id}-${match.competitor_id}-${match.target_url}`}>
                                    {match.competitor_label || match.competitor_domain}: {match.dofollow ? "standard followed link" : "link marked not to pass ranking credit"}
                                    {match.anchor ? ` using â€œ${match.anchor}â€` : ""}. First seen {formatDate(match.first_seen_at)}; last seen {formatDate(match.last_seen_at)}.
                                  </li>
                                ))}
                              </ul>
                            </DetailsDisclosure>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-4 text-sm leading-6 text-zinc-400">
                      No competitor-only website mentions were found in this saved check.
                    </p>
                  )}
                </>
              ) : (
                <div className="mt-5">
                  <EmptyState
                    title={confirmed.length ? "Check where competitors are mentioned" : "Confirm a competitor first"}
                    summary={
                      confirmed.length
                        ? "Run one bounded check to find exact pages that mention confirmed competitors without mentioning this business."
                        : "This comparison needs at least one confirmed business that serves the same customers."
                    }
                    actionLabel={confirmed.length ? "Check websites" : "Review competitors"}
                    onAction={() => {
                      if (confirmed.length) void refreshAuthorityGaps();
                      else document.getElementById("competitor-suggestions")?.scrollIntoView({ behavior: "smooth" });
                    }}
                  />
                </div>
              )}
            </section>

            <section id="authority-outreach-drafts" className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Owner-reviewed outreach
                  </p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Messages you can send yourself</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Start from a verified page, check the recipient yourself, and edit every word before using it.
                    InsightOS does not find email addresses or send these messages automatically.
                  </p>
                </div>
                {authorityOutreach.items.length ? (
                  <div className="flex gap-4 text-xs text-zinc-400">
                    <span>{authorityOutreach.summary.drafts} to review</span>
                    <span>{authorityOutreach.summary.reviewed} ready</span>
                  </div>
                ) : null}
              </div>
              <p className="mt-3 text-xs leading-5 text-zinc-500">{authorityOutreach.truth.summary}</p>

              {authorityOutreach.items.length ? (
                <div className="mt-5 space-y-4">
                  {authorityOutreach.items.map((draft) => (
                    <article key={draft.id} className="rounded-lg border border-[#2d2e34] bg-[#111214] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">
                            {draft.source_page_title || draft.referring_domain}
                          </p>
                          <a
                            href={draft.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-block text-xs text-sky-300 hover:text-sky-200"
                          >
                            Open the exact source page →
                          </a>
                        </div>
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                            draft.status === "reviewed"
                              ? "bg-emerald-500/10 text-emerald-200"
                              : draft.status === "closed"
                                ? "bg-zinc-500/10 text-zinc-400"
                                : "bg-amber-500/10 text-amber-200"
                          }`}
                        >
                          {draft.status_label}
                        </span>
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-3">
                        <label className="text-xs text-zinc-400">
                          Recipient name (optional)
                          <input
                            value={draft.contact_name || ""}
                            onChange={(event) => changeOutreachDraft(draft.id, "contact_name", event.target.value)}
                            placeholder="The person you verified"
                            className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                          />
                        </label>
                        <label className="text-xs text-zinc-400">
                          Verified email (optional)
                          <input
                            value={draft.contact_email || ""}
                            onChange={(event) => changeOutreachDraft(draft.id, "contact_email", event.target.value)}
                            placeholder="name@example.com"
                            className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                          />
                        </label>
                        <label className="text-xs text-zinc-400">
                          Or verified contact page
                          <input
                            value={draft.contact_page_url || ""}
                            onChange={(event) => changeOutreachDraft(draft.id, "contact_page_url", event.target.value)}
                            placeholder="https://example.com/contact"
                            className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                          />
                        </label>
                      </div>

                      <label className="mt-4 block text-xs text-zinc-400">
                        Subject
                        <input
                          value={draft.subject}
                          onChange={(event) => changeOutreachDraft(draft.id, "subject", event.target.value)}
                          className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                        />
                      </label>
                      <label className="mt-3 block text-xs text-zinc-400">
                        Message
                        <textarea
                          value={draft.message_body}
                          onChange={(event) => changeOutreachDraft(draft.id, "message_body", event.target.value)}
                          rows={8}
                          className="mt-1.5 w-full rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm leading-6 text-white outline-none"
                        />
                      </label>

                      <DetailsDisclosure
                        label="Before you use this message"
                        summary="Four checks keep this request useful and honest."
                      >
                        <ol className="space-y-2 text-sm leading-6 text-zinc-300">
                          {draft.review_checklist.map((item, index) => (
                            <li key={`${draft.id}-check-${index + 1}`}>
                              {index + 1}. {item}
                            </li>
                          ))}
                        </ol>
                      </DetailsDisclosure>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void saveOutreachDraft(draft, "draft")}
                          disabled={busyAction !== "" || draft.status === "closed"}
                          className="rounded-md border border-[#34353a] px-3 py-2 text-xs font-medium text-zinc-200 disabled:opacity-50"
                        >
                          {busyAction === `authority-outreach-save:${draft.id}` ? "Saving..." : "Save draft"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void saveOutreachDraft(draft, "reviewed")}
                          disabled={busyAction !== "" || draft.status === "closed"}
                          className="rounded-md bg-sky-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                        >
                          I checked the recipient — mark ready
                        </button>
                        <button
                          type="button"
                          onClick={() => void copyOutreachDraft(draft)}
                          disabled={draft.status !== "reviewed"}
                          className="rounded-md border border-emerald-500/40 px-3 py-2 text-xs font-medium text-emerald-200 disabled:opacity-40"
                        >
                          Copy message
                        </button>
                        <button
                          type="button"
                          onClick={() => void saveOutreachDraft(draft, "closed")}
                          disabled={busyAction !== "" || draft.status === "closed"}
                          className="rounded-md px-3 py-2 text-xs font-medium text-zinc-500 disabled:opacity-40"
                        >
                          Close draft
                        </button>
                      </div>
                      <p className="mt-3 text-xs text-zinc-500">
                        Manual send only. Marking this ready does not contact anyone.
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm leading-6 text-zinc-400">
                  Choose “Prepare a message” on a relevant website opportunity or lost link to begin.
                </p>
              )}
            </section>

            <DetailsDisclosure label="Add a competitor yourself" summary="Use this when you already know a business customers compare with you.">
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <input
                  value={newDomain}
                  onChange={(event) => setNewDomain(event.target.value)}
                  placeholder="competitor.com"
                  aria-label="Competitor website"
                  className="rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                />
                <input
                  value={newLabel}
                  onChange={(event) => setNewLabel(event.target.value)}
                  placeholder="Business name (optional)"
                  aria-label="Competitor business name"
                  className="rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                />
                <button
                  onClick={() => void addCompetitor()}
                  disabled={busyAction !== "" || !newDomain.trim()}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "add" ? "Adding…" : "Add competitor"}
                </button>
              </div>
            </DetailsDisclosure>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
