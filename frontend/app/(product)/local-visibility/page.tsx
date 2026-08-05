"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  MapCard,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type RuntimeTruth,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  buildRuntimeTruthSignal,
  pickPrimaryRuntimeTruth,
} from "../truth/runtimeTruth.mjs";
import { LocalRankGridPanel } from "./LocalRankGridPanel";
import {
  GoogleBusinessListingPanel,
  type BusinessListingIntelligence,
} from "./GoogleBusinessListingPanel";

type Me = {
  organization_id?: string;
};

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

type LocationContext = {
  campaign_id: string;
  business_location_id: string;
  name: string;
  domain?: string | null;
  address: {
    line1?: string | null;
    city?: string | null;
    region?: string | null;
    postal_code?: string | null;
    country_code: string;
    country_name: string;
    formatted: string;
  };
  coordinates: {
    latitude?: number | null;
    longitude?: number | null;
    precision?: string | null;
    source?: string | null;
    status: "ready" | "missing";
  };
  provider_location: {
    code?: string | null;
    name?: string | null;
    type?: string | null;
    resolved_at?: string | null;
    status: "ready" | "missing";
  };
  base_map: {
    status: "ready" | "setup_required";
    coverage_type: "reference_map";
    message: string;
  };
  map_rank_coverage: {
    status: string;
    coverage_type: "paid_geo_grid";
    is_paid: boolean;
    message: string;
  };
  resolution_attempts?: Array<{
    target: string;
    status: string;
    message: string;
  }>;
};

type LocalResponse<T> = T & { truth?: RuntimeTruth };

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
    return "A position in local map results has not been captured yet.";
  }

  if (position <= 3) {
    return `The business is in the top three local map results at position ${position}.`;
  }

  if (position <= 10) {
    return `The business is visible in local map results at position ${position}, but it is outside the top three.`;
  }

  return `The business is currently hard to find in local map results at position ${position}.`;
}

function getReviewsSummary(reviewsLast30d = 0, avgRating = 0) {
  if (reviewsLast30d === 0) {
    return "No recent reviews were captured in the last 30 days, so new review activity is low.";
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
    return "Improve the local business listing first. This location is not yet in the top three local map results.";
  }

  if (reviewsLast30d < 3) {
    return "Ask more recent customers for reviews. Fresh reviews help the business stay competitive locally.";
  }

  if (avgRatingLast30d > 0 && avgRatingLast30d < 4.2) {
    return "Focus on review quality next. The business is getting reviews, but the average rating needs improvement.";
  }

  if (healthScore < 70) {
    return "Check that the business name, address, phone number, and services are consistent everywhere customers may find them.";
  }

  return "Keep the local business listing active, continue asking for fresh reviews, and watch whether its map position improves.";
}

function formatPrecision(value?: string | null) {
  if (value === "city_center") return "City-center reference";
  if (value === "exact") return "Exact address";
  if (value === "manual") return "Saved pin";
  return "Location reference";
}

function LocationBaseMap({ context }: { context: LocationContext | null }) {
  const latitude = context?.coordinates.latitude;
  const longitude = context?.coordinates.longitude;
  if (
    context?.coordinates.status !== "ready" ||
    typeof latitude !== "number" ||
    typeof longitude !== "number"
  ) {
    return (
      <div className="grid min-h-80 place-items-center bg-[radial-gradient(circle_at_30%_30%,rgba(255,106,26,0.12),transparent_28%),linear-gradient(180deg,#0c0d0f_0%,#101114_100%)] p-6 text-center">
        <div className="max-w-sm">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-accent-500/30 bg-accent-500/10 text-xl">
            +
          </div>
          <p className="mt-4 text-base font-semibold text-white">Map setup is incomplete</p>
          <p className="mt-2 text-sm leading-6 text-zinc-400">
            Save a city and state/region, then resolve the location to place this business on a real map.
          </p>
        </div>
      </div>
    );
  }

  const latitudeSpan = 0.13;
  const longitudeSpan = 0.17;
  const bbox = [
    longitude - longitudeSpan,
    latitude - latitudeSpan,
    longitude + longitudeSpan,
    latitude + latitudeSpan,
  ].join(",");
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(
    bbox,
  )}&layer=mapnik&marker=${encodeURIComponent(`${latitude},${longitude}`)}`;
  const openMapUrl = `https://www.openstreetmap.org/?mlat=${encodeURIComponent(
    latitude,
  )}&mlon=${encodeURIComponent(longitude)}#map=12/${latitude}/${longitude}`;

  return (
    <div className="bg-[#0c0d0f]">
      <iframe
        src={mapUrl}
        title={`Interactive reference map for ${context.name}`}
        className="h-80 w-full border-0"
        loading="lazy"
        referrerPolicy="strict-origin-when-cross-origin"
      />
      <div className="flex flex-col gap-2 border-t border-[#26272c] bg-[#111214] px-4 py-3 text-xs text-zinc-400 sm:flex-row sm:items-center sm:justify-between">
        <span>
          {formatPrecision(context.coordinates.precision)} · approximately a 10-mile planning view
        </span>
        <a
          href={openMapUrl}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-accent-400 hover:text-accent-300"
        >
          Open larger map · © OpenStreetMap
        </a>
      </div>
    </div>
  );
}

export default function LocalVisibilityPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [organizationId, setOrganizationId] = useState("");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [health, setHealth] = useState<LocalHealth | null>(null);
  const [mapPack, setMapPack] = useState<MapPack | null>(null);
  const [locationContext, setLocationContext] = useState<LocationContext | null>(null);
  const [velocity, setVelocity] = useState<ReviewVelocity | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [listingIntelligence, setListingIntelligence] = useState<BusinessListingIntelligence | null>(null);
  const [healthTruth, setHealthTruth] = useState<RuntimeTruth | null>(null);
  const [mapPackTruth, setMapPackTruth] = useState<RuntimeTruth | null>(null);
  const [velocityTruth, setVelocityTruth] = useState<RuntimeTruth | null>(null);
  const [reviewsTruth, setReviewsTruth] = useState<RuntimeTruth | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingLocalData, setLoadingLocalData] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [resolvingLocation, setResolvingLocation] = useState(false);
  const loadSequenceRef = useRef(0);

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
    const requestSequence = ++loadSequenceRef.current;
    if (!campaignId) {
      setHealth(null);
      setMapPack(null);
      setLocationContext(null);
      setVelocity(null);
      setReviews([]);
      setListingIntelligence(null);
      return;
    }

    const [healthResponse, mapPackResponse, velocityResponse, reviewsResponse, contextResponse, listingResponse] = await Promise.all([
      platformApi(`/local/health?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/local/map-pack?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/reviews/velocity?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/reviews?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/local/location-context?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      organizationId
        ? platformApi(
            `/organizations/${organizationId}/data-connections/google-business-profile/intelligence/${encodeURIComponent(campaignId)}?days=90`,
            { method: "GET" },
          )
        : Promise.resolve(null),
    ]);

    const normalizedHealth = (healthResponse as LocalResponse<LocalHealth>) || null;
    const normalizedMapPack = (mapPackResponse as LocalResponse<MapPack>) || null;
    const normalizedVelocity = (velocityResponse as LocalResponse<ReviewVelocity>) || null;
    const normalizedReviews = (reviewsResponse as { items?: ReviewItem[]; truth?: RuntimeTruth }) || null;
    if (requestSequence !== loadSequenceRef.current) {
      return;
    }

    setHealth(normalizedHealth || null);
    setMapPack(normalizedMapPack || null);
    setVelocity(normalizedVelocity || null);
    setReviews(Array.isArray(normalizedReviews?.items) ? (normalizedReviews.items as ReviewItem[]) : []);
    setLocationContext((contextResponse as LocationContext) || null);
    setListingIntelligence((listingResponse as BusinessListingIntelligence) || null);
    setHealthTruth(normalizedHealth?.truth || null);
    setMapPackTruth(normalizedMapPack?.truth || null);
    setVelocityTruth(normalizedVelocity?.truth || null);
    setReviewsTruth(normalizedReviews?.truth || null);
  }, [organizationId]);

  const resolveMapLocation = useCallback(async () => {
    if (!selectedCampaignId) return;
    setResolvingLocation(true);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/local/location-context/resolve?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      )) as LocationContext;
      setLocationContext(response);
      const attempts = response.resolution_attempts || [];
      const resolved = attempts.filter((item) =>
        ["resolved", "already_resolved"].includes(item.status),
      ).length;
      const unresolved = attempts.filter(
        (item) => !["resolved", "already_resolved"].includes(item.status),
      );
      setNotice(
        unresolved.length === 0
          ? "The business map and search area are ready."
          : `${resolved} location setup item${resolved === 1 ? "" : "s"} ready. ${unresolved
              .map((item) => item.message)
              .join(" ")}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to resolve this location.");
    } finally {
      setResolvingLocation(false);
    }
  }, [selectedCampaignId]);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");

      try {
        const currentUser = (await platformApi("/auth/me", { method: "GET" })) as Me;
        setOrganizationId(currentUser.organization_id || "");
        await loadCampaigns();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load local SEO data.");
      } finally {
        setLoading(false);
      }
    }

    void loadPage();
  }, [loadCampaigns]);

  useEffect(() => {
    if (!selectedCampaignId) {
      return;
    }

    setLoadingLocalData(true);
    setError("");
    setNotice("");
    setHealth(null);
    setMapPack(null);
    setLocationContext(null);
    setVelocity(null);
    setReviews([]);
    setListingIntelligence(null);
    setHealthTruth(null);
    setMapPackTruth(null);
    setVelocityTruth(null);
    setReviewsTruth(null);
    void loadLocalData(selectedCampaignId)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unable to load local SEO data.");
      })
      .finally(() => setLoadingLocalData(false));
  }, [selectedCampaignId, loadLocalData]);

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
  const runtimeTruth = useMemo(
    () => pickPrimaryRuntimeTruth([mapPackTruth, healthTruth, velocityTruth, reviewsTruth]),
    [healthTruth, mapPackTruth, reviewsTruth, velocityTruth],
  );

  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      buildRuntimeTruthSignal(
        "Updates",
        runtimeTruth,
        "Local-search information may be old or unavailable when a live data connection is not ready.",
      ),
      {
        label: "Base map",
        value: locationContext?.base_map.status === "ready" ? "Ready" : "Setup needed",
        tone: locationContext?.base_map.status === "ready" ? "success" : "warning",
      },
      {
        label: "Local map results",
        value: mapPackPosition ? `Position ${mapPackPosition}` : "Not checked yet",
        tone:
          runtimeTruth?.classification === "unavailable"
            ? "danger"
            : mapPackPosition && mapPackPosition <= 3
              ? "success"
              : "warning",
      },
      {
        label: "Local strength",
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
    [avgRatingLast30d, healthScore, locationContext?.base_map.status, mapPackPosition, reviewsLast30d, runtimeTruth],
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
      dateRangeLabel="Latest local search data"
      topBarActions={
        <>
          <button
            onClick={() => {
              setNotice("Saved local visibility data reloaded.");
              void loadLocalData(selectedCampaignId);
            }}
            disabled={!selectedCampaignId}
            className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reload saved data
          </button>
          <button
            onClick={() => router.push("/citations")}
            className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
          >
            View directory listings
          </button>
        </>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Local search"
          title="Can nearby customers find your business?"
          summary="See how visible this location is in nearby searches, whether reviews are helping, and what to improve next."
        />

        <TruthNotice title="A missing number does not mean your business has no visibility.">
          This page shows the latest information saved for this location. If a result is missing,
          InsightOS has not collected enough information yet.
        </TruthNotice>

        {loading || loadingLocalData ? (
          <LoadingCard
            title="Loading local search results"
            summary="Checking how easy this location is to find and loading its latest review activity."
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

        {!loading && !loadingLocalData && campaigns.length > 0 ? (
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
                label="Local search position"
                value={mapPackPosition ? `#${mapPackPosition}` : "N/A"}
                summary="Lower is better. Positions 1–3 are the businesses customers see most prominently on the map."
                tone="highlight"
              />
              <KpiCard
                label="Local visibility"
                value={healthScore ? `${healthScore}` : "0"}
                summary="A quick summary of how strong this location looks across saved local-search information."
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
                title={locationContext?.name || mapPack?.profile_name || "Business location"}
                summary={
                  locationContext?.address.formatted ||
                  "Add structured location details before placing this business on the map."
                }
                map={<LocationBaseMap context={locationContext} />}
                legend={
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-100">
                      Business location map
                    </span>
                    <span className="rounded-md border border-[#3a2a20] bg-amber-500/5 px-3 py-1.5 text-sm text-amber-100">
                      Map only — not search positions
                    </span>
                    {locationContext?.base_map.status !== "ready" ||
                    locationContext?.provider_location.status !== "ready" ? (
                      <button
                        onClick={() => void resolveMapLocation()}
                        disabled={resolvingLocation}
                        className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100 disabled:opacity-50"
                      >
                        {resolvingLocation ? "Resolving…" : "Resolve location"}
                      </button>
                    ) : null}
                  </div>
                }
              />

              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Reviews
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  New review activity
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
                        : "New review activity is low and needs attention."}
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

            <div className="grid gap-4 md:grid-cols-2">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Search-area setup
                </p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-white">
                      {locationContext?.provider_location.status === "ready"
                        ? locationContext.provider_location.name
                        : "Search area needs setup"}
                    </h2>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      {locationContext?.provider_location.status === "ready"
                        ? "This location is ready for live search checks."
                        : "Add complete city and state details so InsightOS can match the correct search area."}
                    </p>
                  </div>
                  <span
                    className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${
                      locationContext?.provider_location.status === "ready"
                        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
                        : "border-amber-500/20 bg-amber-500/10 text-amber-100"
                    }`}
                  >
                    {locationContext?.provider_location.status === "ready" ? "Ready" : "Needs setup"}
                  </span>
                </div>
              </section>

              <section className="rounded-md border border-[#3a2a20] bg-[#171518] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Neighborhood search coverage
                </p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-white">Area-by-area tracking is ready below</h2>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      Choose customer searches and an area to see how this business appears from
                      different nearby spots. The business map above remains a separate reference.
                    </p>
                  </div>
                  <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-100">
                    Confirm before each check
                  </span>
                </div>
              </section>
            </div>

            <LocalRankGridPanel campaignId={selectedCampaignId} />

            <GoogleBusinessListingPanel
              intelligence={listingIntelligence}
              onOpenSettings={() => router.push("/settings")}
            />

            <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
              <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Local search strength
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  What local issues to watch
                </h2>
                <div className="mt-4 space-y-3">
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Visibility strength</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {healthScore >= 80
                        ? "This location has a strong local-search foundation."
                        : healthScore >= 60
                          ? "The business has a workable local base, but it still needs focused improvements."
                          : "The local foundation is weak, and local visibility needs focused attention."}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Position in local map results</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {getMapPackSummary(mapPackPosition)}
                    </p>
                  </div>
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
                    <p className="text-sm font-medium text-white">Last local update</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Visibility updated {formatRelativeTime(health?.captured_at)} and new review
                      activity updated {formatRelativeTime(velocity?.captured_at)}.
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
                Strengthen your local presence with directory listings
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-300">
                Consistent business details on trusted directories help customers and search
                engines recognize this location. Add and track those listings in one place.
              </p>
              <button
                onClick={() => router.push("/citations")}
                className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
              >
                Manage directory listings
              </button>
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
