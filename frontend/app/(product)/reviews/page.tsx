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
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type ReviewItem = {
  id: string;
  source_name: string;
  rating: number;
  body?: string | null;
  author_name?: string | null;
  author_is_anonymous: boolean;
  response_status: string;
  response_text?: string | null;
  response_updated_at?: string | null;
  review_url?: string | null;
  reviewed_at: string;
};

type ReviewSummary = {
  total: number;
  unanswered: number;
  responded: number;
  rating_three_or_lower: number;
  average_rating?: number | null;
  newest_observation_at?: string | null;
};

type ReviewInventory = {
  items: ReviewItem[];
  summary: ReviewSummary;
};

type ReviewResponseDraft = {
  id: string;
  review_id: string;
  status: "human_required" | "ready_for_review" | "approved" | "rejected" | "unavailable";
  risk_class: "standard" | "sensitive";
  sensitive_topics: string[];
  policy_version: string;
  draft_text?: string | null;
  approved_text?: string | null;
  human_reason?: string | null;
  approval_required: boolean;
  posting_enabled: false;
  created_at: string;
};

type ReviewResponsePolicy = {
  mode: "draft_only";
  human_approval_required: true;
  direct_posting_enabled: false;
  automatic_posting_enabled: false;
  ai_configured: boolean;
  maximum_credits_per_draft?: number | null;
};

type ReviewPostingStatus = {
  available: boolean;
  automatic_posting_enabled: false;
  explicit_confirmation_required: true;
  confirmation_version: string;
  confirmation_label: string;
  capability_status: "not_authorized" | "validation_authorized" | "verified" | "revoked";
  reason: string;
  reason_code?: string | null;
};

type ReviewResponseExecution = {
  id: string;
  review_id: string;
  draft_id: string;
  status: "queued" | "posting" | "retrying" | "posted" | "paused" | "blocked" | "failed" | "cancelled";
  attempt_count: number;
  error_code?: string | null;
  error_message?: string | null;
  requested_at: string;
  posted_at?: string | null;
};

type ReviewFilter = "all" | "unanswered" | "low" | "responded";

const EMPTY_SUMMARY: ReviewSummary = {
  total: 0,
  unanswered: 0,
  responded: 0,
  rating_three_or_lower: 0,
  average_rating: null,
};

function reviewDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function Stars({ rating }: { rating: number }) {
  const filled = Math.max(1, Math.min(5, Math.round(rating)));
  return (
    <span aria-label={`${rating} out of 5 stars`} className="tracking-[0.12em]">
      <span className="text-amber-400">{"★".repeat(filled)}</span>
      <span className="text-zinc-700">{"★".repeat(5 - filled)}</span>
    </span>
  );
}

export default function ReviewsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [inventory, setInventory] = useState<ReviewInventory>({
    items: [],
    summary: EMPTY_SUMMARY,
  });
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [draftsByReview, setDraftsByReview] = useState<Record<string, ReviewResponseDraft>>({});
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});
  const [responsePolicy, setResponsePolicy] = useState<ReviewResponsePolicy | null>(null);
  const [postingStatus, setPostingStatus] = useState<ReviewPostingStatus | null>(null);
  const [executionsByReview, setExecutionsByReview] = useState<Record<string, ReviewResponseExecution>>({});
  const [publishConfirmations, setPublishConfirmations] = useState<Record<string, boolean>>({});
  const [workingReviewId, setWorkingReviewId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadInventory = useCallback(async (campaignId: string) => {
    const [response, draftResponse, policyResponse, postingResponse, executionResponse] = await Promise.all([
      platformApi(
        `/reviews/inventory?campaign_id=${encodeURIComponent(campaignId)}&source_type=owned_profile&limit=250`,
        { method: "GET" },
      ) as Promise<ReviewInventory>,
      platformApi(`/reviews/drafts?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<{ items: ReviewResponseDraft[] }>,
      platformApi(`/reviews/response-policy?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<ReviewResponsePolicy>,
      platformApi(`/reviews/posting-status?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<ReviewPostingStatus>,
      platformApi(`/reviews/executions?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<{ items: ReviewResponseExecution[] }>,
    ]);
    setInventory({
      items: Array.isArray(response?.items) ? response.items : [],
      summary: response?.summary || EMPTY_SUMMARY,
    });
    const nextDrafts: Record<string, ReviewResponseDraft> = {};
    const nextEdits: Record<string, string> = {};
    for (const draft of draftResponse?.items || []) {
      nextDrafts[draft.review_id] = draft;
      nextEdits[draft.id] = draft.approved_text || draft.draft_text || "";
    }
    setDraftsByReview(nextDrafts);
    setDraftEdits(nextEdits);
    setResponsePolicy(policyResponse || null);
    setPostingStatus(postingResponse || null);
    const nextExecutions: Record<string, ReviewResponseExecution> = {};
    for (const execution of executionResponse?.items || []) {
      if (!nextExecutions[execution.review_id]) nextExecutions[execution.review_id] = execution;
    }
    setExecutionsByReview(nextExecutions);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        const response = await platformApi("/campaigns", { method: "GET" });
        const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
        if (cancelled) return;
        setCampaigns(items);
        setSelectedCampaignId((current) => {
          if (current && items.some((item) => item.id === current)) return current;
          return items[0]?.id || "";
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Reviews could not be loaded.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadPage();
    return () => {
      cancelled = true;
    };
  }, [setSelectedCampaignId]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setFilter("all");
    setNotice("");
    void loadInventory(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Reviews could not be loaded.");
    });
  }, [loadInventory, loading, selectedCampaignId]);

  useEffect(() => {
    if (!selectedCampaignId) return;
    const hasPendingWork = Object.values(executionsByReview).some((item) =>
      ["queued", "posting", "retrying"].includes(item.status),
    );
    if (!hasPendingWork) return;
    const timer = window.setInterval(() => {
      void loadInventory(selectedCampaignId).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [executionsByReview, loadInventory, selectedCampaignId]);

  async function checkForReviews() {
    if (!selectedCampaignId) return;
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      const response = await platformApi(
        `/reviews/sync?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      setInventory({
        items: Array.isArray(response?.items) ? (response.items as ReviewItem[]) : [],
        summary: (response?.summary as ReviewSummary) || EMPTY_SUMMARY,
      });
      setNotice(response?.job?.message || "The latest saved reviews are shown below.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reviews could not be updated.");
    } finally {
      setRefreshing(false);
    }
  }

  async function draftReply(reviewId: string, refresh = false) {
    if (!selectedCampaignId) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      const draft = (await platformApi(
        `/reviews/${encodeURIComponent(reviewId)}/drafts?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST", body: JSON.stringify({ refresh }) },
      )) as ReviewResponseDraft;
      setDraftsByReview((current) => ({ ...current, [reviewId]: draft }));
      setDraftEdits((current) => ({
        ...current,
        [draft.id]: draft.approved_text || draft.draft_text || "",
      }));
      if (draft.status === "human_required") {
        setNotice("This review needs a person to write the reply. No AI action or credit was used.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "A reply draft could not be prepared.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function decideDraft(reviewId: string, draft: ReviewResponseDraft, decision: "approve" | "reject") {
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      const updated = (await platformApi(`/reviews/drafts/${encodeURIComponent(draft.id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          decision,
          approved_text: decision === "approve" ? draftEdits[draft.id] || draft.draft_text || "" : null,
        }),
      })) as ReviewResponseDraft;
      setDraftsByReview((current) => ({ ...current, [reviewId]: updated }));
      setDraftEdits((current) => ({
        ...current,
        [updated.id]: updated.approved_text || updated.draft_text || "",
      }));
      setNotice(
        decision === "approve"
          ? "Approved wording was saved. InsightOS did not post it."
          : "The draft was discarded.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The draft decision could not be saved.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function copyApprovedReply(draft: ReviewResponseDraft) {
    const text = draft.approved_text || "";
    if (!text || !navigator.clipboard) return;
    await navigator.clipboard.writeText(text);
    setNotice("Approved reply copied. You can paste it into your business profile.");
  }

  async function publishApprovedReply(reviewId: string, draft: ReviewResponseDraft) {
    if (!selectedCampaignId || !postingStatus || !publishConfirmations[draft.id]) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      await platformApi(
        `/reviews/drafts/${encodeURIComponent(draft.id)}/publish?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            confirmation_version: postingStatus.confirmation_version,
            confirm_publish_to_google: true,
          }),
        },
      );
      await loadInventory(selectedCampaignId);
      setNotice("Your approved reply is queued for Google. We will show the confirmed result here.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The approved reply could not be queued.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function controlPublish(
    reviewId: string,
    execution: ReviewResponseExecution,
    action: "pause" | "resume" | "cancel" | "retry",
  ) {
    if (!selectedCampaignId) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      await platformApi(`/reviews/executions/${encodeURIComponent(execution.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ action }),
      });
      await loadInventory(selectedCampaignId);
      setNotice(
        action === "pause"
          ? "Posting is paused."
          : action === "resume"
            ? "Posting is queued again."
            : action === "cancel"
              ? "Posting was cancelled before Google received it."
              : "Posting is queued to try again.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The posting action could not be completed.");
    } finally {
      setWorkingReviewId("");
    }
  }

  const filteredReviews = useMemo(() => {
    if (filter === "unanswered") {
      return inventory.items.filter((item) => item.response_status === "unanswered");
    }
    if (filter === "responded") {
      return inventory.items.filter((item) => item.response_status === "responded");
    }
    if (filter === "low") {
      return inventory.items.filter((item) => item.rating <= 3);
    }
    return inventory.items;
  }, [filter, inventory.items]);

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Needs a reply",
        value: String(inventory.summary.unanswered),
        tone: inventory.summary.unanswered > 0 ? "warning" : "success",
      },
      {
        label: "3 stars or lower",
        value: String(inventory.summary.rating_three_or_lower),
        tone: inventory.summary.rating_three_or_lower > 0 ? "danger" : "success",
      },
    ],
    [inventory.summary.rating_three_or_lower, inventory.summary.unanswered],
  );

  const filters: Array<{ id: ReviewFilter; label: string; count: number }> = [
    { id: "all", label: "All reviews", count: inventory.summary.total },
    { id: "unanswered", label: "Needs a reply", count: inventory.summary.unanswered },
    { id: "low", label: "3 stars or lower", count: inventory.summary.rating_three_or_lower },
    { id: "responded", label: "Answered", count: inventory.summary.responded },
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
      dateRangeLabel="Latest saved customer reviews"
      topBarActions={
        <button
          type="button"
          onClick={() => void checkForReviews()}
          disabled={!selectedCampaignId || refreshing}
          className="rounded-md bg-[#ff6b18] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshing ? "Checking..." : "Check for new reviews"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Customer reviews"
          title="See what customers said and what needs a reply"
          summary="Keep each location's reviews in one place. Start with unhappy customers and reviews that have not received an answer."
          compact
        />

        <TruthNotice title="AI can prepare wording, but you stay in control.">
          Every suggested reply must be checked and approved by a person. Posting is a separate step
          with its own confirmation. Automatic replies are off.
        </TruthNotice>

        {responsePolicy && !responsePolicy.ai_configured ? (
          <section className="rounded-md border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            AI reply drafting is not connected yet. Your reviews remain available and no credits will be used.
          </section>
        ) : null}

        {loading ? <LoadingCard title="Loading customer reviews" summary="Checking the selected location." /> : null}
        {error ? (
          <section className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}
        {notice ? (
          <section className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            {notice}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            icon="reviews"
            title="No business is ready yet"
            summary="Set up a business location before collecting its customer reviews."
            actionLabel="Set up a location"
            onAction={() => router.push("/locations")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <section className="grid gap-3 sm:grid-cols-3">
              <KpiCard
                icon="reviews"
                label="Needs a reply"
                value={String(inventory.summary.unanswered)}
                summary="Customer reviews with no saved business response."
                tone={inventory.summary.unanswered > 0 ? "highlight" : "default"}
              />
              <KpiCard
                icon="spark"
                label="Average rating"
                value={inventory.summary.average_rating?.toFixed(1) || "—"}
                summary="Average across the reviews saved for this location."
              />
              <KpiCard
                icon="warning"
                label="3 stars or lower"
                value={String(inventory.summary.rating_three_or_lower)}
                summary="Start here when a customer had a poor experience."
              />
            </section>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-5">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Review inbox
                  </p>
                  <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                    {filteredReviews.length} {filteredReviews.length === 1 ? "review" : "reviews"}
                  </h2>
                </div>
                <div className="flex flex-wrap gap-2" aria-label="Review filters">
                  {filters.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={filter === item.id}
                      onClick={() => setFilter(item.id)}
                      className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                        filter === item.id
                          ? "border-accent-500/40 bg-accent-500/15 text-white"
                          : "border-[#303138] bg-[#101113] text-zinc-400 hover:text-white"
                      }`}
                    >
                      {item.label} <span className="ml-1 text-current/70">{item.count}</span>
                    </button>
                  ))}
                </div>
              </div>

              {filteredReviews.length > 0 ? (
                <div className="mt-5 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                  {filteredReviews.map((review) => (
                    <article key={review.id} className="py-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">
                            {review.author_is_anonymous ? "Anonymous customer" : review.author_name || "Customer"}
                          </p>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                            <Stars rating={review.rating} />
                            <span className="text-zinc-500">{reviewDate(review.reviewed_at)}</span>
                          </div>
                        </div>
                        <span
                          className={`rounded-md border px-2 py-1 text-xs font-semibold ${
                            review.response_status === "responded"
                              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
                              : "border-amber-500/20 bg-amber-500/10 text-amber-100"
                          }`}
                        >
                          {review.response_status === "responded" ? "Answered" : "Needs a reply"}
                        </span>
                      </div>
                      <p className="mt-3 max-w-4xl text-sm leading-6 text-zinc-200">
                        {review.body || "This customer left a star rating without a written comment."}
                      </p>
                      {review.response_text ? (
                        <div className="mt-4 border-l-2 border-emerald-500/40 bg-emerald-500/[0.04] px-4 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-200/70">
                            Your saved response
                          </p>
                          <p className="mt-1.5 text-sm leading-6 text-zinc-300">{review.response_text}</p>
                        </div>
                      ) : null}
                      {review.response_status === "unanswered"
                        ? (() => {
                            const draft = draftsByReview[review.id];
                            const execution = executionsByReview[review.id];
                            const isWorking = workingReviewId === review.id;
                            if (!draft) {
                              const creditLabel = responsePolicy?.maximum_credits_per_draft
                                ? `Up to ${responsePolicy.maximum_credits_per_draft} Insight Credit${
                                    responsePolicy.maximum_credits_per_draft === 1 ? "" : "s"
                                  }`
                                : "Usage is measured before work starts";
                              return (
                                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[#292a2f] pt-4">
                                  <button
                                    type="button"
                                    onClick={() => void draftReply(review.id)}
                                    disabled={isWorking || responsePolicy?.ai_configured === false}
                                    className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {isWorking ? "Preparing wording..." : "Draft a reply"}
                                  </button>
                                  <span className="text-xs text-zinc-500">{creditLabel}. Nothing is posted.</span>
                                </div>
                              );
                            }
                            if (draft.status === "human_required") {
                              return (
                                <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/[0.07] p-4">
                                  <p className="font-semibold text-amber-100">A person should handle this reply</p>
                                  <p className="mt-1 text-sm leading-6 text-zinc-300">{draft.human_reason}</p>
                                  {draft.sensitive_topics.length > 0 ? (
                                    <p className="mt-2 text-xs text-zinc-500">
                                      Safety check: {draft.sensitive_topics.join(", ")}
                                    </p>
                                  ) : null}
                                  {review.review_url ? (
                                    <a
                                      href={review.review_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="mt-3 inline-flex text-sm font-semibold text-[#ff8a4c] hover:text-[#ffa06f]"
                                    >
                                      Open the original review →
                                    </a>
                                  ) : null}
                                </div>
                              );
                            }
                            if (draft.status === "ready_for_review") {
                              return (
                                <div className="mt-4 rounded-md border border-violet-500/20 bg-violet-500/[0.06] p-4">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div>
                                      <p className="font-semibold text-white">Check this suggested reply</p>
                                      <p className="mt-1 text-sm text-zinc-400">
                                        Edit anything that does not sound like your business, then approve or discard it.
                                      </p>
                                    </div>
                                    <span className="rounded-full border border-violet-400/20 px-2.5 py-1 text-[11px] font-semibold text-violet-100">
                                      Not posted
                                    </span>
                                  </div>
                                  <textarea
                                    aria-label={`Reply draft for ${review.author_name || "customer"}`}
                                    value={draftEdits[draft.id] ?? draft.draft_text ?? ""}
                                    maxLength={600}
                                    onChange={(event) =>
                                      setDraftEdits((current) => ({ ...current, [draft.id]: event.target.value }))
                                    }
                                    className="mt-3 min-h-28 w-full resize-y rounded-md border border-[#34353c] bg-[#0e0f11] p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-violet-400/50"
                                  />
                                  <div className="mt-3 flex flex-wrap items-center gap-2">
                                    <button
                                      type="button"
                                      disabled={isWorking || !(draftEdits[draft.id] ?? draft.draft_text ?? "").trim()}
                                      onClick={() => void decideDraft(review.id, draft, "approve")}
                                      className="rounded-md bg-emerald-600 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      {isWorking ? "Saving..." : "Approve this wording"}
                                    </button>
                                    <button
                                      type="button"
                                      disabled={isWorking}
                                      onClick={() => void decideDraft(review.id, draft, "reject")}
                                      className="rounded-md border border-[#34353c] px-3.5 py-2 text-sm font-semibold text-zinc-200 disabled:opacity-50"
                                    >
                                      Discard draft
                                    </button>
                                    <span className="text-xs text-zinc-500">Approval saves it here only.</span>
                                  </div>
                                </div>
                              );
                            }
                            if (draft.status === "approved") {
                              return (
                                <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] p-4">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <p className="font-semibold text-emerald-100">Approved wording</p>
                                    <span className="rounded-full border border-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-100">
                                      {execution?.status === "posted"
                                        ? "Posted to Google"
                                        : execution?.status === "posting"
                                          ? "Posting now"
                                          : execution?.status === "retrying"
                                            ? "Waiting to try again"
                                            : execution?.status === "queued"
                                              ? "Queued"
                                              : execution?.status === "paused"
                                                ? "Paused"
                                                : execution?.status === "blocked"
                                                  ? "Needs attention"
                                                  : execution?.status === "failed"
                                                    ? "Could not post"
                                                    : execution?.status === "cancelled"
                                                      ? "Cancelled"
                                                      : "Not posted"}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-zinc-200">{draft.approved_text}</p>
                                  {execution?.error_message ? (
                                    <p className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/[0.08] px-3 py-2 text-sm text-amber-100">
                                      {execution.error_message}
                                    </p>
                                  ) : null}
                                  {!execution && postingStatus?.available ? (
                                    <label className="mt-4 flex max-w-2xl cursor-pointer items-start gap-3 rounded-md border border-[#34353c] bg-[#101113] p-3 text-sm leading-6 text-zinc-200">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(publishConfirmations[draft.id])}
                                        onChange={(event) =>
                                          setPublishConfirmations((current) => ({
                                            ...current,
                                            [draft.id]: event.target.checked,
                                          }))
                                        }
                                        className="mt-1 h-4 w-4 accent-[#ff6b18]"
                                      />
                                      <span>{postingStatus.confirmation_label}</span>
                                    </label>
                                  ) : null}
                                  {!execution && postingStatus && !postingStatus.available ? (
                                    <p className="mt-3 text-sm leading-6 text-zinc-400">{postingStatus.reason}</p>
                                  ) : null}
                                  <div className="mt-3 flex flex-wrap items-center gap-3">
                                    {!execution && postingStatus?.available ? (
                                      <button
                                        type="button"
                                        disabled={isWorking || !publishConfirmations[draft.id]}
                                        onClick={() => void publishApprovedReply(review.id, draft)}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        {isWorking ? "Queuing..." : "Post approved reply to Google"}
                                      </button>
                                    ) : null}
                                    {execution && ["queued", "retrying"].includes(execution.status) ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "pause")}
                                        className="rounded-md border border-amber-500/25 px-3.5 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
                                      >
                                        Pause posting
                                      </button>
                                    ) : null}
                                    {execution?.status === "paused" ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "resume")}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:opacity-50"
                                      >
                                        Resume posting
                                      </button>
                                    ) : null}
                                    {execution && ["queued", "retrying", "paused"].includes(execution.status) ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "cancel")}
                                        className="rounded-md border border-[#34353c] px-3.5 py-2 text-sm font-semibold text-zinc-200 disabled:opacity-50"
                                      >
                                        Cancel
                                      </button>
                                    ) : null}
                                    {execution?.status === "failed" ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "retry")}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:opacity-50"
                                      >
                                        Try posting again
                                      </button>
                                    ) : null}
                                    <button
                                      type="button"
                                      onClick={() => void copyApprovedReply(draft)}
                                      className="rounded-md border border-emerald-500/25 px-3.5 py-2 text-sm font-semibold text-emerald-100"
                                    >
                                      Copy approved reply
                                    </button>
                                    <span className="text-xs text-zinc-500">
                                      {execution
                                        ? "Posting history stays attached to this approved reply."
                                        : "Copying does not post or change anything."}
                                    </span>
                                  </div>
                                </div>
                              );
                            }
                            return (
                              <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/[0.06] p-4">
                                <p className="font-semibold text-amber-100">
                                  {draft.status === "rejected" ? "Draft discarded" : "Wording is not available yet"}
                                </p>
                                <p className="mt-1 text-sm leading-6 text-zinc-300">
                                  {draft.human_reason || "You can ask for a fresh draft when you are ready."}
                                </p>
                                <button
                                  type="button"
                                  disabled={isWorking || responsePolicy?.ai_configured === false}
                                  onClick={() => void draftReply(review.id, true)}
                                  className="mt-3 rounded-md border border-amber-500/25 px-3.5 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
                                >
                                  {isWorking ? "Preparing wording..." : "Try a fresh draft"}
                                </button>
                              </div>
                            );
                          })()
                        : null}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="mt-5 rounded-md border border-[#2a2b30] bg-[#101113] p-5">
                  <p className="font-semibold text-white">
                    {inventory.summary.total === 0
                      ? "No reviews have been saved for this location yet"
                      : "No reviews match this filter"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-zinc-400">
                    {inventory.summary.total === 0
                      ? "Use Check for new reviews. If this location is not connected, open Data connections and match its business listing first."
                      : "Choose a different filter to see the rest of the review inbox."}
                  </p>
                  {inventory.summary.total === 0 ? (
                    <button
                      type="button"
                      onClick={() => router.push("/settings")}
                      className="mt-3 text-sm font-semibold text-[#ff8a4c] hover:text-[#ffa06f]"
                    >
                      Open data connections →
                    </button>
                  ) : null}
                </div>
              )}
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
