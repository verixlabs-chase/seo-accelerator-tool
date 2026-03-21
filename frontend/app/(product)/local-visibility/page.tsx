"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  MapCard,
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

type LocalHealth = {
  campaign_id?: string;
  profile_id?: string;
  health_score?: number;
  captured_at?: string;
};

type MapPack = {
  campaign_id?: string;
  provider?: string;
  map_pack_position?: number | null;
  profile_name?: string;
};

type ReviewVelocity = {
  campaign_id?: string;
  profile_id?: string;
  reviews_last_30d?: number;
  avg_rating_last_30d?: number;
  captured_at?: string;
};

type ReviewItem = {
  external_review_id?: string;
  rating?: number;
  sentiment?: string;
  reviewed_at?: string;
};

function formatRelativeTime(value?: string) {
  if (!value) {
    return "No recent update";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No recent update";
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

function getHealthLabel(score = 0) {
  if (score >= 80) {
    return "Local visibility is strong";
  }

  if (score >= 60) {
    return "Local visibility is steady";
  }

  return "Local visibility needs work";
}

function getMapPackSummary(position?: number | null) {
  if (!position) {
    return "Map-pack position has not been captured yet.";
  }

  if (position <= 3) {
    return `The business is showing inside the top 3 map-pack spots at position ${position}.`;
  }

  if (position <= 10) {
    return `The business is visible locally at position ${position}, but it is outside the top map-pack tier.`;
  }

  return `The business is currently hard to find in the map pack at position ${position}.`;
}

function getReviewsSummary(reviewsLast30d = 0, avgRating = 0) {
  if (reviewsLast30d === 0) {
    return "No recent reviews were captured in the last 30 days, so review momentum is weak.";
  }

  if (avgRating >= 4.5) {
    return `${reviewsLast30d} recent reviews with a strong ${avgRating.toFixed(1)} average rating.`;
  }

  if (avgRating >= 4) {
    return `${reviewsLast30d} recent reviews with a healthy ${avgRating.toFixed(1)} average rating.`;
  }

  return `${reviewsLast30d} recent reviews, but the ${avgRating.toFixed(1)} average rating needs attention.`;
}

function getSentimentTone(sentiment?: string) {
  if (sentiment === "positive") {
    return "text-emerald-100 border-emerald-500/20 bg-emerald-500/10";
  }

  if (sentiment === "negative") {
    return "text-rose-100 border-rose-500/20 bg-rose-500/10";
  }

  return "text-zinc-200 border-[#26272c] bg-[#141518]";
}

function buildNextStep({
  mapPackPosition,
  reviewsLast30d,
  avgRatingLast30d,
  healthScore,
}: {
  mapPackPosition?: number | null;
  reviewsLast30d: number;
  avgRatingLast30d: number;
  healthScore: number;
}) {
  if ((mapPackPosition || 99) > 3) {
    return "Focus on improving local profile visibility first. The business is not yet in the top map-pack positions.";
  }

  if (reviewsLast30d < 3) {
    return "Focus on review momentum next. The business needs more fresh reviews to stay competitive locally.";
  }

  if (avgRatingLast30d > 0 && avgRatingLast30d < 4.2) {
    return "Focus on review quality next. The business is getting reviews, but the average rating needs improvement.";
  }

  if (healthScore < 70) {
    return "Focus on local consistency next. The overall local health score is not strong enough yet.";
  }

  return "Keep the local profile active and continue collecting fresh reviews while watching map-pack movement.";
}

function LocalMapVisual({ position = 20 }: { position?: number | null }) {
  const safePosition = position || 20;

  return (
    <div className="grid min-h-72 place-items-center bg-[radial-gradient(circle_at_30%_30%,rgba(255,106,26,0.18),transparent_22%),linear-gradient(180deg,#0c0d0f_0%,#101114_100%)] p-6">
      <div className="grid w-full max-w-sm grid-cols-3 gap-3">
        {Array.from({ length: 9 }).map((_, index) => {
          const slot = index + 1;
          const isBusiness = slot === Math.min(safePosition, 9);
          return (
            <div
              key={slot}
              className={`flex h-20 items-center justify-center rounded-md border text-sm font-semibold ${
                isBusiness
                  ? "border-accent-500/40 bg-accent-500/15 text-zinc-100"
                  : "border-[#26272c] bg-[#141518] text-zinc-500"
              }`}
            >
              {isBusiness ? `You #${safePosition}` : `#${slot}`}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function LocalVisibilityPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [health, setHealth] = useState<LocalHealth | null>(null);
  const [mapPack, setMapPack] = useState<MapPack | null>(null);
  const [velocity, setVelocity] = useState<ReviewVelocity | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

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

  const loadLocalData = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setHealth(null);
      setMapPack(null);
      setVelocity(null);
      setReviews([]);
      return;
    }

    const [healthResponse, mapPackResponse, velocityResponse, reviewsResponse] = await Promise.all([
      platformApi(`/local/health?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/local/map-pack?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/reviews/velocity?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/reviews?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
    ]);

    setHealth((healthResponse as LocalHealth) || null);
    setMapPack((mapPackResponse as MapPack) || null);
    setVelocity((velocityResponse as ReviewVelocity) || null);
    setReviews(Array.isArray(reviewsResponse?.items) ? (reviewsResponse.items as ReviewItem[]) : []);
  }, []);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        await platformApi("/auth/me", { method: "GET" });
        const items = await loadCampaigns();
        if (items[0]?.id) {
          await loadLocalData(items[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load local SEO data.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns, loadLocalData]);

  useEffect(() => {
    if (!selectedCampaignId || loading) {
      return;
    }

    void loadLocalData(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to load local SEO data.");
    });
  }, [selectedCampaignId, loading, loadLocalData]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const healthScore = health?.health_score || 0;
  const mapPackPosition = mapPack?.map_pack_position;
  const reviewsLast30d = velocity?.reviews_last_30d || 0;
  const avgRatingLast30d = velocity?.avg_rating_last_30d || 0;
  const nextStep = buildNextStep({
    mapPackPosition,
    reviewsLast30d,
    avgRatingLast30d,
    healthScore,
  });

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Map-pack",
        value: mapPackPosition ? `Position ${mapPackPosition}` : "No map-pack data",
        tone: mapPackPosition && mapPackPosition <= 3 ? "success" : "warning",
      },
      {
        label: "Local health",
        value: healthScore ? `${healthScore}/100` : "No health score",
        tone: healthScore >= 70 ? "success" : healthScore >= 50 ? "info" : "warning",
      },
      {
        label: "Reviews (30d)",
        value: reviewsLast30d ? `${reviewsLast30d} captured` : "No recent reviews",
        tone: reviewsLast30d >= 3 ? "success" : "warning",
      },
      {
        label: "Average rating",
        value: avgRatingLast30d ? avgRatingLast30d.toFixed(1) : "No rating yet",
        tone: avgRatingLast30d >= 4.5 ? "success" : avgRatingLast30d >= 4 ? "info" : "warning",
      },
    ],
    [avgRatingLast30d, healthScore, mapPackPosition, reviewsLast30d],
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
      dateRangeLabel="Live local SEO data"
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
            onClick={() => {
              setNotice("Local SEO data refreshed.");
              void loadLocalData(selectedCampaignId);
            }}
            disabled={!selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            onClick={() => router.push("/citations")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            View citations
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Local SEO"
          title="How your business is showing up locally"
          summary="Use this page to understand local visibility, review momentum, and what to focus on next for map-pack performance."
        />

        <TruthNotice title="Local visibility is directional when provider coverage is thin or stale.">
          Map-pack position, review velocity, and local health summarize the latest captured state
          in the database. Missing values mean the workspace has not captured enough provider data
          yet, not that the business has definitively scored zero in the real world.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading local SEO"
            summary="Pulling local visibility, review momentum, and local health signals for the active business."
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
            title="No business is ready for local SEO yet"
            summary="Set up a business first so InsightOS can collect local visibility and review data."
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
                    {getHealthLabel(healthScore)}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    {getMapPackSummary(mapPackPosition)} {getReviewsSummary(reviewsLast30d, avgRatingLast30d)}
                  </p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    What to do next
                  </p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{nextStep}</p>
                </div>
              </div>
            </section>

            <div className="grid gap-4 xl:grid-cols-4">
              <KpiCard
                label="Map-pack position"
                value={mapPackPosition ? `#${mapPackPosition}` : "N/A"}
                summary="Lower is better. This shows how easy it is to find the business in the local map pack."
                tone="highlight"
              />
              <KpiCard
                label="Local health"
                value={healthScore ? `${healthScore}` : "0"}
                summary="This is the current local visibility health score for the active business."
              />
              <KpiCard
                label="Reviews in 30 days"
                value={String(reviewsLast30d)}
                summary="Fresh reviews help keep local visibility and trust moving in the right direction."
              />
              <KpiCard
                label="Average rating"
                value={avgRatingLast30d ? avgRatingLast30d.toFixed(1) : "0.0"}
                summary="This is the average rating captured from recent review activity."
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.08fr_0.92fr]">
              <MapCard
                title={mapPack?.profile_name || "Local profile visibility"}
                summary={getMapPackSummary(mapPackPosition)}
                map={<LocalMapVisual position={mapPackPosition} />}
                legend={
                  <span className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200">
                    {mapPack?.provider?.toUpperCase() || "GBP"}
                  </span>
                }
              />

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Reviews
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Review momentum
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  Reviews influence local trust. This summary shows whether recent review activity is helping or holding the business back.
                </p>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Last 30 days
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
                      {reviewsLast30d}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {reviewsLast30d >= 3
                        ? "Fresh review activity is present."
                        : "Review velocity is light and needs attention."}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Average rating
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
                      {avgRatingLast30d ? avgRatingLast30d.toFixed(1) : "0.0"}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {avgRatingLast30d >= 4.5
                        ? "Review quality looks strong."
                        : avgRatingLast30d >= 4
                          ? "Review quality is healthy but can improve."
                          : "Review quality is a local trust risk."}
                    </p>
                  </div>
                </div>
              </section>
            </div>

            <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Local health
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  What local issues to watch
                </h2>
                <div className="mt-4 space-y-3">
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Visibility strength</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {healthScore >= 80
                        ? "The business has a strong local health score and is in a defensible position."
                        : healthScore >= 60
                          ? "The business has a workable local base, but it still needs focused improvements."
                          : "The local foundation is weak, and local visibility needs focused attention."}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Map-pack competitiveness</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {getMapPackSummary(mapPackPosition)}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Last local update</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Health updated {formatRelativeTime(health?.captured_at)} and review velocity updated {formatRelativeTime(velocity?.captured_at)}.
                    </p>
                  </div>
                </div>
              </section>

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Recent reviews
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Latest review signals
                </h2>
                <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                  These recent reviews help show whether local trust is improving, flat, or slipping.
                </p>

                {reviews.length === 0 ? (
                  <div className="mt-4 rounded-md border border-dashed border-[#26272c] bg-[#111214] p-4 text-center">
                    <p className="text-sm font-medium text-zinc-300">No recent reviews yet</p>
                    <p className="mt-1 text-sm text-zinc-500">Review signals will appear here once captured for this business.</p>
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {reviews.slice(0, 5).map((review) => (
                      <div
                        key={review.external_review_id}
                        className="rounded-md border border-[#26272c] bg-[#111214] p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-white">
                              {review.rating?.toFixed(1) || "0.0"} star review
                            </p>
                            <p className="mt-1 text-sm leading-6 text-zinc-300">
                              Captured {formatRelativeTime(review.reviewed_at)}
                            </p>
                          </div>
                          <span
                            className={`rounded-md border px-2 py-1 text-xs font-medium ${getSentimentTone(review.sentiment)}`}
                          >
                            {review.sentiment || "neutral"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>

            <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Next step
              </p>
              <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                Strengthen your local presence with citations
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                Directory citations help build local authority and consistency across the web. Submit
                your business to key directories and track listing status in the Citations workspace.
              </p>
              <button
                onClick={() => router.push("/citations")}
                className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
              >
                Manage citations
              </button>
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
