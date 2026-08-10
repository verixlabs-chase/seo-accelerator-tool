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
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadInventory = useCallback(async (campaignId: string) => {
    const response = (await platformApi(
      `/reviews/inventory?campaign_id=${encodeURIComponent(campaignId)}&source_type=owned_profile&limit=250`,
      { method: "GET" },
    )) as ReviewInventory;
    setInventory({
      items: Array.isArray(response?.items) ? response.items : [],
      summary: response?.summary || EMPTY_SUMMARY,
    });
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

        <TruthNotice title="Review replies are not turned on yet.">
          You can read and sort saved reviews here. InsightOS cannot write or post a reply in this version.
        </TruthNotice>

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
