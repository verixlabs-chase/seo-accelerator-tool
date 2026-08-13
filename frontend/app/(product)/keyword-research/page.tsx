"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type MouseEvent,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  EmptyState,
  LoadingCard,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import { simplifyCustomerCopy } from "../truth/customerLanguage.mjs";

type ResearchRun = {
  id: string;
  status: "complete" | "partial" | "unavailable" | "running";
  location_name: string;
  sources: string[];
  warnings: string[];
  suggestion_count: number;
  completed_at?: string | null;
};

type SearchSuggestion = {
  id: string;
  keyword: string;
  source_types: string[];
  search_volume?: number | null;
  cpc?: number | null;
  competition_level?: string | null;
  keyword_difficulty?: number | null;
  current_position?: number | null;
  gsc_impressions?: number | null;
  gsc_position?: number | null;
  intent: string;
  opportunity_group: "quick_win" | "new_opportunity" | "already_found" | "tracked";
  relevance_score: number;
  relevance_status: "relevant" | "needs_review" | "unrelated";
  matched_service_id?: string | null;
  matched_service_name?: string | null;
  matched_service_area_id?: string | null;
  matched_service_area_name?: string | null;
  area_match_type?: "included" | "excluded" | "confirmed_market" | "missing" | null;
  ai_review_status?: "not_requested" | "validated" | "unavailable" | "rejected";
  ai_relevance_status?: "relevant" | "needs_review" | "unrelated" | null;
  ai_confidence?: number | null;
  ai_reason?: string | null;
  relevance_reason?: string | null;
  owner_feedback?: "relevant" | "unrelated" | null;
  competitor_evidence?: Array<{
    competitor_id: string;
    domain: string;
    label?: string | null;
    position?: number | null;
    url?: string | null;
    observed_at: string;
  }>;
  opportunity_score: number;
  recommended_action: string;
  recommendation_reason: string;
  cluster?: {
    key: string;
    label: string;
    service_name?: string | null;
    problem: string;
    location_name?: string | null;
    intent: string;
  };
  target_page?: {
    status: "existing" | "needs_page" | "review" | "not_applicable";
    url?: string | null;
    title?: string | null;
    reason: string;
  };
  trend?: {
    status:
      | "new"
      | "gaining_demand"
      | "losing_demand"
      | "improving_rank"
      | "slipping_rank"
      | "steady"
      | "not_enough_history";
    label: string;
    demand_change?: number | null;
    position_improvement?: number | null;
    opportunity_change?: number | null;
    previous_search_volume?: number | null;
    previous_position?: number | null;
  };
  tracked_at?: string | null;
};

type SearchClusterSummary = {
  key: string;
  label: string;
  problem: string;
  locationName?: string | null;
  keywords: string[];
  keywordCount: number;
  trackedCount: number;
  totalDemand: number;
  bestPosition?: number | null;
  targetPage?: SearchSuggestion["target_page"];
  suggestionIds: string[];
  hasMeasuredEvidence: boolean;
};

type KeywordHistory = {
  snapshot_count: number;
  series: Array<{
    run_id: string;
    completed_at?: string | null;
    useful_searches: number;
    measured_demand: number;
    visible_searches: number;
    average_position?: number | null;
    average_opportunity_score?: number | null;
  }>;
  comparison?: {
    current_completed_at?: string | null;
    previous_completed_at?: string | null;
    new_searches: number;
    no_longer_seen: number;
    rising_demand: number;
    falling_demand: number;
    improved_positions: number;
    slipped_positions: number;
    demand_change: number;
    new_keyword_examples: string[];
    missing_keyword_examples: string[];
  } | null;
};

type FilterQuality = {
  state: "gathering_feedback" | "measuring" | "reliable";
  headline: string;
  message: string;
  owner_checked: number;
  automatic_decisions_checked: number;
  agreements: number;
  corrections: number;
  agreement_rate?: number | null;
  unclear_searches_resolved: number;
  minimum_sample: number;
};

type GovernedKeywordAction = {
  id: string;
  cluster_key: string;
  cluster_label?: string | null;
  action_id: string;
  status: string;
  rationale: string;
  created_at?: string | null;
};

type ResearchResponse = {
  run: ResearchRun | null;
  items: SearchSuggestion[];
  summary: {
    total: number;
    quick_wins: number;
    new_opportunities: number;
    already_found: number;
    tracked: number;
    best_matches: number;
    needs_review: number;
    hidden_unrelated: number;
  };
  history?: KeywordHistory;
  filter_quality?: FilterQuality;
  governed_actions?: GovernedKeywordAction[];
  ai_review?: {
    state: string;
    reviewed: number;
    best_matches: number;
    hidden_unrelated: number;
    still_unclear: number;
    message: string;
  };
  feedback?: {
    decision: "relevant" | "unrelated" | "cleared";
    keyword: string;
    message: string;
  };
};

type BusinessServiceItem = {
  id: string;
  name: string;
  status: "suggested" | "confirmed" | "rejected";
  source: "manual" | "website" | "business_profile" | "inherited";
  inherited: boolean;
  confidence: number;
  evidence: Array<{ url?: string; title?: string; note?: string }>;
};

type ServiceProfile = {
  campaign_id: string;
  business_location_id?: string | null;
  items: BusinessServiceItem[];
  summary: { confirmed: number; suggested: number; rejected: number };
  discovery?: { pages_reviewed: number; created: number; updated: number; message: string };
};

type BusinessServiceAreaItem = {
  id: string;
  area_type: "city" | "postal_code" | "county" | "radius" | "boundary" | "drive_time";
  name: string;
  region?: string | null;
  country_code: string;
  radius_miles?: number | null;
  travel_minutes?: number | null;
  center_latitude?: number | null;
  center_longitude?: number | null;
  boundary_points?: ServiceBoundaryPoint[];
  relationship: "included" | "excluded";
  status: "suggested" | "confirmed" | "rejected";
  source: "manual" | "website" | "location" | "business_profile" | "map";
  confidence: number;
  evidence: Array<{
    url?: string;
    title?: string;
    note?: string;
    distance_miles?: number;
    radius_miles?: number;
  }>;
};

type ServiceBoundaryPoint = {
  latitude: number;
  longitude: number;
};

type ServiceAreaProfile = {
  campaign_id: string;
  business_location_id?: string | null;
  items: BusinessServiceAreaItem[];
  summary: {
    confirmed_included: number;
    confirmed_excluded: number;
    suggested: number;
  };
  map?: {
    status: "ready" | "setup_required";
    center_latitude?: number | null;
    center_longitude?: number | null;
    radius_miles: number;
    radius_saved: boolean;
    boundary_saved?: boolean;
    boundary_id?: string | null;
    boundary_points?: ServiceBoundaryPoint[];
    boundary_kind?: "boundary" | "drive_time" | null;
    travel_minutes?: number | null;
    drive_time_available?: boolean;
  };
  discovery?: {
    pages_reviewed?: number;
    created: number;
    updated: number;
    reviewed?: number;
    radius_miles?: number;
    boundary_saved?: boolean;
    drive_time_saved?: boolean;
    travel_minutes?: number;
    message: string;
  };
};

type CreditSummary = {
  credits: { remaining: number; blocked: boolean };
  action_prices: Array<{
    code: string;
    credits: number;
    price_type: "up_to" | "per_item" | "fixed_ceiling";
  }>;
};

const FILTERS = [
  { id: "best", label: "Best matches" },
  { id: "needs_review", label: "Needs your review" },
  { id: "tracked", label: "Already tracking" },
  { id: "unrelated", label: "Hidden as unrelated" },
] as const;

function groupLabel(group: SearchSuggestion["opportunity_group"]) {
  return {
    quick_win: "Close to the top",
    new_opportunity: "New opportunity",
    already_found: "Google already finds you",
    tracked: "Already tracking",
  }[group];
}

function groupTone(group: SearchSuggestion["opportunity_group"]) {
  if (group === "quick_win") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (group === "new_opportunity") return "border-accent-500/25 bg-accent-500/10 text-accent-100";
  if (group === "already_found") return "border-sky-500/25 bg-sky-500/10 text-sky-100";
  return "border-[#303137] bg-[#18191c] text-zinc-300";
}

function positionLabel(item: SearchSuggestion) {
  const position = item.current_position ?? item.gsc_position;
  if (position) return `About #${Math.round(position)}`;
  if ((item.gsc_impressions ?? 0) > 0) return "Showing, but low";
  return "Not found yet";
}

function demandLabel(value?: number | null) {
  if (value === null || value === undefined) return "No estimate yet";
  if (value === 0) return "Very low";
  return `About ${value.toLocaleString()}/month`;
}

function intentLabel(intent: string) {
  return {
    commercial: "Comparing options",
    transactional: "Ready to hire",
    local: "Looking nearby",
    informational: "Learning about the service",
    navigational: "Looking for a specific business",
    mixed: "Mixed customer need",
  }[intent.toLowerCase()] ?? "Customer need not clear yet";
}

function trendTone(status?: NonNullable<SearchSuggestion["trend"]>["status"]) {
  if (status === "new" || status === "gaining_demand" || status === "improving_rank") {
    return "bg-emerald-500/10 text-emerald-200";
  }
  if (status === "losing_demand" || status === "slipping_rank") {
    return "bg-rose-500/10 text-rose-200";
  }
  return "bg-[#1a1b1e] text-zinc-400";
}

function shortDate(value?: string | null) {
  if (!value) return "Saved date";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function sourceLabel(source: string) {
  return {
    google_search_console: "Search Console",
    live_rankings: "Live rankings",
    related_searches: "Related searches",
    local_demand: "Search estimates",
    tracked_rankings: "Your tracked list",
    website_content: "Your website",
    competitor_rankings: "Competitor search results",
  }[source] ?? source;
}

function ServiceAreaMap({
  profile,
  busy,
  onSaveBoundary,
}: {
  profile: ServiceAreaProfile;
  busy: boolean;
  onSaveBoundary: (points: ServiceBoundaryPoint[]) => Promise<boolean>;
}) {
  const [drawingBoundary, setDrawingBoundary] = useState(false);
  const [draftBoundary, setDraftBoundary] = useState<ServiceBoundaryPoint[]>([]);
  const centerLatitude = profile.map?.center_latitude;
  const centerLongitude = profile.map?.center_longitude;
  if (
    profile.map?.status !== "ready" ||
    centerLatitude === null ||
    centerLatitude === undefined ||
    centerLongitude === null ||
    centerLongitude === undefined
  ) {
    return (
      <div className="mt-5 rounded-md border border-amber-500/25 bg-amber-500/10 p-4">
        <p className="text-sm font-semibold text-amber-100">Add the location&apos;s map position first</p>
        <p className="mt-1 text-sm leading-6 text-zinc-400">
          Open Locations and finish the address check before using a mileage range or finding nearby towns.
        </p>
      </div>
    );
  }

  const radiusMiles = Math.max(1, profile.map.radius_miles || 25);
  const savedBoundary = profile.map.boundary_points ?? [];
  const boundaryLatitudeSpan = savedBoundary.reduce(
    (maximum, point) => Math.max(maximum, Math.abs(point.latitude - centerLatitude)),
    0,
  );
  const boundaryLongitudeSpan = savedBoundary.reduce(
    (maximum, point) => Math.max(maximum, Math.abs(point.longitude - centerLongitude)),
    0,
  );
  const radiusLatitudeSpan = radiusMiles / 69;
  const radiusLongitudeSpan = radiusLatitudeSpan /
    Math.max(0.25, Math.cos((centerLatitude * Math.PI) / 180));
  const latitudeSpan = Math.max(radiusLatitudeSpan, boundaryLatitudeSpan) * 1.25;
  const longitudeSpan = Math.max(radiusLongitudeSpan, boundaryLongitudeSpan) * 1.25;
  const minimumLatitude = centerLatitude - latitudeSpan;
  const maximumLatitude = centerLatitude + latitudeSpan;
  const minimumLongitude = centerLongitude - longitudeSpan;
  const maximumLongitude = centerLongitude + longitudeSpan;
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${minimumLongitude}%2C${minimumLatitude}%2C${maximumLongitude}%2C${maximumLatitude}&layer=mapnik&marker=${centerLatitude}%2C${centerLongitude}`;
  const mapItems = profile.items.filter(
    (item) =>
      item.area_type !== "radius" &&
      item.area_type !== "boundary" &&
      item.area_type !== "drive_time" &&
      item.status !== "rejected" &&
      item.center_latitude !== null &&
      item.center_latitude !== undefined &&
      item.center_longitude !== null &&
      item.center_longitude !== undefined,
  );
  const visibleBoundary = drawingBoundary ? draftBoundary : savedBoundary;
  const boundarySvgPoints = visibleBoundary
    .map((point) => {
      const x = ((point.longitude - minimumLongitude) / (maximumLongitude - minimumLongitude)) * 100;
      const y = ((maximumLatitude - point.latitude) / (maximumLatitude - minimumLatitude)) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  const beginBoundary = () => {
    setDraftBoundary([]);
    setDrawingBoundary(true);
  };

  const addBoundaryPoint = (event: MouseEvent<SVGSVGElement>) => {
    if (!drawingBoundary || draftBoundary.length >= 24) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    setDraftBoundary((current) => [
      ...current,
      {
        latitude: maximumLatitude - y * (maximumLatitude - minimumLatitude),
        longitude: minimumLongitude + x * (maximumLongitude - minimumLongitude),
      },
    ]);
  };

  const saveBoundary = async () => {
    if (draftBoundary.length < 3) return;
    if (await onSaveBoundary(draftBoundary)) {
      setDrawingBoundary(false);
      setDraftBoundary([]);
    }
  };

  return (
    <div className="mt-5 overflow-hidden rounded-md border border-[#303137] bg-[#111214]">
      <div className="relative h-72 overflow-hidden bg-[#18191c]">
        <iframe
          title="Service area map"
          src={mapUrl}
          className="h-full w-full border-0 opacity-80 grayscale-[0.15]"
          loading="lazy"
        />
        <div className="pointer-events-none absolute inset-0">
          {!savedBoundary.length ? (
            <div className="absolute left-[10%] top-[10%] h-[80%] w-[80%] rounded-full border-2 border-dashed border-accent-500/80 bg-accent-500/5" />
          ) : null}
          {mapItems.map((item) => {
            const left = Math.min(
              98,
              Math.max(2, ((Number(item.center_longitude) - minimumLongitude) / (maximumLongitude - minimumLongitude)) * 100),
            );
            const top = Math.min(
              98,
              Math.max(2, ((maximumLatitude - Number(item.center_latitude)) / (maximumLatitude - minimumLatitude)) * 100),
            );
            return (
              <span
                key={item.id}
                title={`${item.name}: ${item.status === "confirmed" ? "served" : "needs your answer"}`}
                style={{ left: `${left}%`, top: `${top}%` }}
                className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-lg ${
                  item.status === "confirmed" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
            );
          })}
        </div>
        <svg
          aria-label={
            drawingBoundary
              ? "Click the map to add work-area corners"
              : profile.map.boundary_kind === "drive_time"
                ? "Saved driving-time work area"
                : "Saved custom work area"
          }
          role="img"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          onClick={addBoundaryPoint}
          className={`absolute inset-0 z-10 h-full w-full ${
            drawingBoundary ? "pointer-events-auto cursor-crosshair" : "pointer-events-none"
          }`}
        >
          {visibleBoundary.length >= 3 ? (
            <polygon
              points={boundarySvgPoints}
              fill="rgba(16, 185, 129, 0.16)"
              stroke="#34d399"
              strokeWidth="0.8"
              vectorEffect="non-scaling-stroke"
            />
          ) : visibleBoundary.length === 2 ? (
            <polyline
              points={boundarySvgPoints}
              fill="none"
              stroke="#34d399"
              strokeWidth="0.8"
              vectorEffect="non-scaling-stroke"
            />
          ) : null}
          {visibleBoundary.map((point, index) => {
            const x = ((point.longitude - minimumLongitude) / (maximumLongitude - minimumLongitude)) * 100;
            const y = ((maximumLatitude - point.latitude) / (maximumLatitude - minimumLatitude)) * 100;
            return (
              <circle
                key={`${point.latitude}-${point.longitude}-${index}`}
                cx={x}
                cy={y}
                r="1.15"
                fill="#10b981"
                stroke="white"
                strokeWidth="0.45"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
      </div>
      <div className="border-t border-[#303137] px-4 py-3">
        {drawingBoundary ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-zinc-300">
              Click at least 3 corners around the places your crew serves. Keep the shape inside the map.
              {draftBoundary.length ? ` ${draftBoundary.length} corners added.` : ""}
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setDraftBoundary((current) => current.slice(0, -1))}
                disabled={!draftBoundary.length || busy}
                className="rounded-md border border-[#303137] px-3 py-1.5 text-xs font-semibold text-zinc-200 disabled:opacity-40"
              >
                Undo corner
              </button>
              <button
                type="button"
                onClick={() => {
                  setDrawingBoundary(false);
                  setDraftBoundary([]);
                }}
                disabled={busy}
                className="rounded-md border border-[#303137] px-3 py-1.5 text-xs font-semibold text-zinc-200 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void saveBoundary()}
                disabled={draftBoundary.length < 3 || busy}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
              >
                {busy ? "Saving work area..." : "Save this work area"}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs leading-5 text-zinc-400">
              {profile.map.boundary_kind === "drive_time" && profile.map.travel_minutes ? (
                <p>
                  Green outline: about {profile.map.travel_minutes} minutes by road. This does not use live traffic.
                </p>
              ) : profile.map.boundary_kind === "boundary" ? (
                <p>Green outline: the custom work area you drew.</p>
              ) : (
                <p>
                  Dashed circle: about {radiusMiles.toLocaleString(undefined, { maximumFractionDigits: 1 })} miles.
                </p>
              )}
              <p>Orange towns need your answer. Green towns are confirmed.</p>
              <p>Map suggestions never count as service areas until you approve them.</p>
            </div>
            <button
              type="button"
              onClick={beginBoundary}
              disabled={busy}
              className="shrink-0 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:opacity-40"
            >
              {savedBoundary.length ? "Redraw custom work area" : "Draw a custom work area"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function KeywordResearchPage() {
  const pathname = usePathname();
  const router = useRouter();
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const { campaigns, selectedCampaign, selectedCampaignId, loadingLocations } =
    useLocationContext();
  const [data, setData] = useState<ResearchResponse>({
    run: null,
    items: [],
    summary: {
      total: 0,
      quick_wins: 0,
      new_opportunities: 0,
      already_found: 0,
      tracked: 0,
      best_matches: 0,
      needs_review: 0,
      hidden_unrelated: 0,
    },
  });
  const [serviceProfile, setServiceProfile] = useState<ServiceProfile>({
    campaign_id: "",
    items: [],
    summary: { confirmed: 0, suggested: 0, rejected: 0 },
  });
  const [newService, setNewService] = useState("");
  const [serviceBusy, setServiceBusy] = useState<"" | "discover" | "add" | string>("");
  const [serviceAreaProfile, setServiceAreaProfile] = useState<ServiceAreaProfile>({
    campaign_id: "",
    items: [],
    summary: { confirmed_included: 0, confirmed_excluded: 0, suggested: 0 },
  });
  const [newArea, setNewArea] = useState("");
  const [newAreaRegion, setNewAreaRegion] = useState("");
  const [newAreaType, setNewAreaType] = useState<BusinessServiceAreaItem["area_type"]>("city");
  const [newAreaRelationship, setNewAreaRelationship] =
    useState<BusinessServiceAreaItem["relationship"]>("included");
  const [nearbyRadius, setNearbyRadius] = useState("25");
  const [driveTimeMinutes, setDriveTimeMinutes] = useState("30");
  const [areaBusy, setAreaBusy] = useState<"" | "suggest" | "add" | string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "discover" | "track" | "review">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [aiNotice, setAiNotice] = useState<{ message: string; success: boolean } | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("best");
  const [selectedClusterKey, setSelectedClusterKey] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [serviceChoiceBySuggestion, setServiceChoiceBySuggestion] = useState<
    Record<string, string>
  >({});
  const [feedbackBusy, setFeedbackBusy] = useState("");
  const [actionBusy, setActionBusy] = useState("");
  const [creditSummary, setCreditSummary] = useState<CreditSummary | null>(null);

  const loadResearch = useCallback(async (campaignId: string) => {
    setLoading(true);
    setError("");
    try {
      const response = (await platformApi(
        `/keyword-research?campaign_id=${encodeURIComponent(campaignId)}`,
      )) as ResearchResponse;
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search ideas could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadServices = useCallback(async (campaignId: string) => {
    const response = (await platformApi(
      `/business-services?campaign_id=${encodeURIComponent(campaignId)}`,
    )) as ServiceProfile;
    setServiceProfile(response);
  }, []);

  const loadServiceAreas = useCallback(async (campaignId: string) => {
    const response = (await platformApi(
      `/business-service-areas?campaign_id=${encodeURIComponent(campaignId)}`,
    )) as ServiceAreaProfile;
    setServiceAreaProfile(response);
    if (response.map?.radius_saved) setNearbyRadius(String(response.map.radius_miles));
  }, []);

  const loadCredits = useCallback(async () => {
    const response = (await platformApi("/usage/credits", {
      method: "GET",
    })) as CreditSummary;
    setCreditSummary(response);
  }, []);

  useEffect(() => {
    setSelectedIds(new Set());
    setNotice("");
    setAiNotice(null);
    setFilter("best");
    setSelectedClusterKey(null);
    if (!selectedCampaignId) {
      setLoading(false);
      setData({
        run: null,
        items: [],
        summary: {
          total: 0,
          quick_wins: 0,
          new_opportunities: 0,
          already_found: 0,
          tracked: 0,
          best_matches: 0,
          needs_review: 0,
          hidden_unrelated: 0,
        },
      });
      setServiceProfile({
        campaign_id: "",
        items: [],
        summary: { confirmed: 0, suggested: 0, rejected: 0 },
      });
      setServiceAreaProfile({
        campaign_id: "",
        items: [],
        summary: { confirmed_included: 0, confirmed_excluded: 0, suggested: 0 },
      });
      setNearbyRadius("25");
      return;
    }
    void Promise.all([
      loadResearch(selectedCampaignId),
      loadServices(selectedCampaignId),
      loadServiceAreas(selectedCampaignId),
      loadCredits(),
    ]).catch((err) =>
      setError(err instanceof Error ? err.message : "Business details could not be loaded."),
    );
  }, [loadCredits, loadResearch, loadServiceAreas, loadServices, selectedCampaignId]);

  const discoverServices = async () => {
    if (!selectedCampaignId) return;
    setServiceBusy("discover");
    setError("");
    try {
      const response = (await platformApi("/business-services/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId }),
      })) as ServiceProfile;
      setServiceProfile(response);
      setNotice(response.discovery?.message ?? "Review the services found on your website.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Your website services could not be reviewed.");
    } finally {
      setServiceBusy("");
    }
  };

  const addService = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedCampaignId || !newService.trim()) return;
    setServiceBusy("add");
    setError("");
    try {
      const response = (await platformApi("/business-services", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, name: newService.trim() }),
      })) as ServiceProfile;
      setServiceProfile(response);
      setNewService("");
      setNotice("Service added. Saved searches were checked against the updated service list.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The service could not be added.");
    } finally {
      setServiceBusy("");
    }
  };

  const reviewService = async (
    serviceId: string,
    status: "confirmed" | "rejected",
  ) => {
    if (!selectedCampaignId) return;
    setServiceBusy(serviceId);
    setError("");
    try {
      const response = (await platformApi(`/business-services/${serviceId}`, {
        method: "PATCH",
        body: JSON.stringify({ campaign_id: selectedCampaignId, status }),
      })) as ServiceProfile;
      setServiceProfile(response);
      setNotice(
        status === "confirmed"
          ? "Service confirmed. Saved searches were checked again."
          : "That item will not be used as a service for this location.",
      );
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The service choice could not be saved.");
    } finally {
      setServiceBusy("");
    }
  };

  const suggestServiceAreas = async () => {
    if (!selectedCampaignId) return;
    setAreaBusy("suggest");
    setError("");
    try {
      const response = (await platformApi("/business-service-areas/suggest", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNotice(response.discovery?.message ?? "Review the places found for this location.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Service areas could not be checked.");
    } finally {
      setAreaBusy("");
    }
  };

  const addServiceArea = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedCampaignId || !newArea.trim()) return;
    setAreaBusy("add");
    setError("");
    try {
      const response = (await platformApi("/business-service-areas", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          area_type: newAreaType,
          name: newAreaType === "radius" ? null : newArea.trim(),
          region: newAreaRegion.trim() || null,
          radius_miles: newAreaType === "radius" ? Number(newArea) : null,
          relationship: newAreaRelationship,
        }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNewArea("");
      setNewAreaRegion("");
      setNotice(
        newAreaRelationship === "included"
          ? "Service area added. Saved searches were checked again."
          : "Excluded area saved. Searches naming that place will stay out of Best matches.",
      );
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The service area could not be added.");
    } finally {
      setAreaBusy("");
    }
  };

  const suggestNearbyCommunities = async () => {
    if (!selectedCampaignId) return;
    const radius = Number(nearbyRadius);
    if (!Number.isFinite(radius) || radius < 1 || radius > 75) {
      setError("Choose a mileage range from 1 to 75 miles.");
      return;
    }
    setAreaBusy("nearby");
    setError("");
    try {
      const response = (await platformApi("/business-service-areas/nearby", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, radius_miles: radius }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNotice(response.discovery?.message ?? "Review the nearby communities on the map.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nearby communities could not be checked.");
    } finally {
      setAreaBusy("");
    }
  };

  const saveCustomBoundary = async (points: ServiceBoundaryPoint[]) => {
    if (!selectedCampaignId) return false;
    setAreaBusy("boundary");
    setError("");
    try {
      const response = (await platformApi("/business-service-areas/boundary", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, points }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNotice(response.discovery?.message ?? "Your custom work area was saved.");
      await loadResearch(selectedCampaignId);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "The custom work area could not be saved.");
      return false;
    } finally {
      setAreaBusy("");
    }
  };

  const suggestDriveTimeCommunities = async () => {
    if (!selectedCampaignId) return;
    const travelMinutes = Number(driveTimeMinutes);
    if (!Number.isInteger(travelMinutes) || travelMinutes < 10 || travelMinutes > 90) {
      setError("Choose a driving time from 10 to 90 minutes.");
      return;
    }
    setAreaBusy("drive-time");
    setError("");
    try {
      const response = (await platformApi("/business-service-areas/drive-time", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          travel_minutes: travelMinutes,
        }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNotice(response.discovery?.message ?? "Review the towns inside your driving range.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The driving-time map could not be checked.");
    } finally {
      setAreaBusy("");
    }
  };

  const reviewServiceArea = async (
    areaId: string,
    status: "confirmed" | "rejected",
  ) => {
    if (!selectedCampaignId) return;
    setAreaBusy(areaId);
    setError("");
    try {
      const response = (await platformApi(`/business-service-areas/${areaId}`, {
        method: "PATCH",
        body: JSON.stringify({ campaign_id: selectedCampaignId, status }),
      })) as ServiceAreaProfile;
      setServiceAreaProfile(response);
      setNotice(
        status === "confirmed"
          ? "Service area confirmed. Saved searches were checked again."
          : "That place will not be used as a service area.",
      );
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The service-area choice could not be saved.");
    } finally {
      setAreaBusy("");
    }
  };

  const runDiscovery = async () => {
    if (!selectedCampaignId) return;
    setBusy("discover");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/keyword-research/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, max_suggestions: 75 }),
      })) as ResearchResponse;
      setData(response);
      setSelectedIds(new Set());
      setNotice(
        response.items.length
          ? `Found ${response.items.length} searches worth reviewing for this location.`
          : "No useful searches were confirmed yet. Check your services and work area, then try again.",
      );
      await loadCredits();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search discovery could not be completed.");
    } finally {
      setBusy("");
    }
  };

  const trackSelected = async () => {
    if (!selectedCampaignId || selectedIds.size === 0) return;
    setBusy("track");
    setError("");
    try {
      const response = await platformApi("/keyword-research/track", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [...selectedIds],
        }),
      });
      setNotice(
        `${response.created_count ?? 0} added to Search Rankings. ${response.already_tracked_count ?? 0} were already there.`,
      );
      setSelectedIds(new Set());
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The selected searches could not be tracked.");
    } finally {
      setBusy("");
    }
  };

  const reviewUnclearSearches = async () => {
    if (!selectedCampaignId) return;
    setBusy("review");
    setError("");
    setAiNotice(null);
    try {
      const response = (await platformApi("/keyword-research/review-uncertain", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          max_items: 8,
        }),
      })) as ResearchResponse;
      setData(response);
      setSelectedIds(new Set());
      setAiNotice({
        message: response.ai_review?.message ?? "The unclear searches were reviewed.",
        success: response.ai_review?.state === "complete" || response.ai_review?.state === "nothing_to_review",
      });
      await loadCredits();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The unclear searches could not be reviewed.");
    } finally {
      setBusy("");
    }
  };

  const saveSearchFeedback = async (
    item: SearchSuggestion,
    decision: "relevant" | "unrelated" | "cleared",
  ) => {
    if (!selectedCampaignId) return;
    const confirmedServices = serviceProfile.items.filter(
      (service) => service.status === "confirmed",
    );
    const selectedServiceId =
      serviceChoiceBySuggestion[item.id]
      || item.matched_service_id
      || confirmedServices[0]?.id
      || null;
    if (decision === "relevant" && !selectedServiceId) {
      setError("Confirm at least one service before matching this search.");
      return;
    }
    setFeedbackBusy(item.id);
    setError("");
    try {
      const response = (await platformApi("/keyword-research/feedback", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_id: item.id,
          decision,
          service_id: decision === "relevant" ? selectedServiceId : null,
        }),
      })) as ResearchResponse;
      setData(response);
      setSelectedIds(new Set());
      setNotice(response.feedback?.message ?? "Your choice was saved.");
      if (decision === "unrelated") setFilter("unrelated");
      if (decision === "relevant") setFilter("best");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Your choice could not be saved.");
    } finally {
      setFeedbackBusy("");
    }
  };

  const createNextStep = async (cluster: SearchClusterSummary) => {
    if (!selectedCampaignId || cluster.suggestionIds.length === 0) return;
    setActionBusy(cluster.key);
    setError("");
    setNotice("");
    try {
      const response = await platformApi("/keyword-research/create-action", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: cluster.suggestionIds,
        }),
      });
      setNotice(response.message ?? "Added to Next Steps for review.");
      await loadResearch(selectedCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "This group could not be added to Next Steps.");
    } finally {
      setActionBusy("");
    }
  };

  const filteredItems = useMemo(
    () => data.items.filter((item) => {
      const matchesView =
        filter === "best"
          ? item.relevance_status === "relevant"
          : filter === "needs_review"
            ? item.relevance_status === "needs_review"
            : filter === "unrelated"
              ? item.relevance_status === "unrelated"
              : Boolean(item.tracked_at);
      const matchesCluster = !selectedClusterKey || item.cluster?.key === selectedClusterKey;
      return matchesView && matchesCluster;
    }),
    [data.items, filter, selectedClusterKey],
  );
  const chartData = useMemo(
    () =>
      data.items
        .filter((item) => item.relevance_status === "relevant" && (item.search_volume ?? 0) > 0)
        .slice(0, 8)
        .map((item) => ({
          name: item.keyword.length > 30 ? `${item.keyword.slice(0, 28)}…` : item.keyword,
          demand: item.search_volume ?? 0,
        }))
        .reverse(),
    [data.items],
  );
  const searchClusters = useMemo(() => {
    const groups = new Map<string, SearchClusterSummary>();
    data.items
      .filter((item) => item.relevance_status === "relevant" && item.cluster?.key)
      .forEach((item) => {
        const cluster = item.cluster!;
        const position = item.current_position ?? item.gsc_position ?? null;
        const existing = groups.get(cluster.key);
        if (!existing) {
          groups.set(cluster.key, {
            key: cluster.key,
            label: cluster.label,
            problem: cluster.problem,
            locationName: cluster.location_name,
            keywords: [item.keyword],
            keywordCount: 1,
            trackedCount: item.tracked_at ? 1 : 0,
            totalDemand: item.search_volume ?? 0,
            bestPosition: position,
            targetPage: item.target_page,
            suggestionIds: [item.id],
            hasMeasuredEvidence: Boolean(
              (item.search_volume ?? 0) > 0
              || item.current_position !== null && item.current_position !== undefined
              || item.gsc_position !== null && item.gsc_position !== undefined
              || (item.gsc_impressions ?? 0) > 0
              || item.competitor_evidence?.length,
            ),
          });
          return;
        }
        existing.keywordCount += 1;
        existing.trackedCount += item.tracked_at ? 1 : 0;
        existing.totalDemand += item.search_volume ?? 0;
        existing.suggestionIds.push(item.id);
        existing.hasMeasuredEvidence = existing.hasMeasuredEvidence || Boolean(
          (item.search_volume ?? 0) > 0
          || item.current_position !== null && item.current_position !== undefined
          || item.gsc_position !== null && item.gsc_position !== undefined
          || (item.gsc_impressions ?? 0) > 0
          || item.competitor_evidence?.length,
        );
        if (existing.keywords.length < 3) existing.keywords.push(item.keyword);
        if (position !== null && (existing.bestPosition === null || existing.bestPosition === undefined || position < existing.bestPosition)) {
          existing.bestPosition = position;
        }
        if (item.target_page?.status === "existing" && existing.targetPage?.status !== "existing") {
          existing.targetPage = item.target_page;
        }
      });
    return [...groups.values()]
      .sort((a, b) => b.totalDemand - a.totalDemand || b.keywordCount - a.keywordCount || a.label.localeCompare(b.label))
      .slice(0, 8);
  }, [data.items]);
  const selectedCluster = searchClusters.find((item) => item.key === selectedClusterKey) ?? null;
  const actionByCluster = useMemo(
    () => new Map((data.governed_actions ?? []).map((item) => [item.cluster_key, item])),
    [data.governed_actions],
  );
  const trendChartData = useMemo(
    () => (data.history?.series ?? []).map((item) => ({
      ...item,
      date: shortDate(item.completed_at),
    })),
    [data.history?.series],
  );
  const selectableVisible = filteredItems.filter(
    (item) => !item.tracked_at && item.relevance_status !== "unrelated",
  );
  const confirmedServices = serviceProfile.items.filter((item) => item.status === "confirmed");
  const suggestedServices = serviceProfile.items.filter((item) => item.status === "suggested");
  const confirmedIncludedAreas = serviceAreaProfile.items.filter(
    (item) =>
      item.status === "confirmed" &&
      item.relationship === "included" &&
      item.area_type !== "boundary" &&
      item.area_type !== "drive_time",
  );
  const confirmedExcludedAreas = serviceAreaProfile.items.filter(
    (item) => item.status === "confirmed" && item.relationship === "excluded",
  );
  const suggestedAreas = serviceAreaProfile.items.filter((item) => item.status === "suggested");
  const researchCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "keyword_research_refresh",
  );
  const reviewCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "keyword_relevance_review",
  );
  const trustSignals: TrustSignal[] = [];

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No domain"}`
          : "No location selected"
      }
      dateRangeLabel={data.run ? `Latest research: ${data.run.location_name}` : "No research yet"}
      topBarActions={
        <button
          type="button"
          onClick={() => void runDiscovery()}
          disabled={!selectedCampaignId || busy !== "" || creditSummary?.credits.blocked}
          className="rounded-md bg-accent-500 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "discover" ? "Finding searches…" : data.run ? "Refresh search ideas" : "Find search ideas"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Keyword research"
          title="Find searches customers use"
          summary="See what people search for near this location, where your business already appears, and which searches are worth tracking next."
        />

        {researchCreditPrice ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[#26272c] py-3 text-sm">
            <p className="text-zinc-300">
              Refreshing this location uses up to {researchCreditPrice.credits} Insight Credits.
              Unused credits are returned automatically.
            </p>
            <p className="font-semibold text-white">
              {creditSummary?.credits.remaining.toLocaleString()} available
            </p>
          </div>
        ) : null}

        <TruthNotice title="Search counts are estimates, not promised jobs.">
          Use them to compare searches. Confirm the work you sell and the places you serve before
          adding anything to Search Rankings.
        </TruthNotice>

        {selectedCampaignId ? (
          <section className="border-y border-[#26272c] py-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-2xl">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  Your services
                </p>
                <h2 className="mt-1 text-xl font-semibold text-white">
                  What work should these searches match?
                </h2>
                <p className="mt-2 text-sm leading-6 text-zinc-400">
                  Confirm the work this location actually provides. Search ideas that do not match
                  this list will stay out of your best matches.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void discoverServices()}
                disabled={serviceBusy !== ""}
                className="rounded-md border border-[#303137] bg-[#17181b] px-4 py-2 text-sm font-semibold text-zinc-100 hover:border-accent-500/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {serviceBusy === "discover" ? "Checking your website…" : "Find services on your website"}
              </button>
            </div>

            {confirmedServices.length ? (
              <div className="mt-5">
                <p className="text-xs font-semibold text-zinc-300">Confirmed services</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {confirmedServices.map((service) => (
                    <span
                      key={service.id}
                      className="inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-100"
                    >
                      <ProductIcon name="check" size={14} />
                      {service.name}
                      <button
                        type="button"
                        onClick={() => void reviewService(service.id, "rejected")}
                        disabled={serviceBusy !== ""}
                        aria-label={`Remove ${service.name} from this location's services`}
                        className="ml-1 text-xs text-emerald-100/60 hover:text-white disabled:opacity-50"
                      >
                        Remove
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-5 border-l-2 border-amber-400 pl-4">
                <p className="text-sm font-semibold text-amber-100">Confirm at least one service</p>
                <p className="mt-1 text-sm text-zinc-400">
                  Until you do, uncertain searches will wait in Needs your review instead of being
                  presented as strong recommendations.
                </p>
              </div>
            )}

            {suggestedServices.length ? (
              <div className="mt-5">
                <p className="text-xs font-semibold text-zinc-300">
                  We found these on your website. Do you offer them?
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {suggestedServices.map((service) => (
                    <div
                      key={service.id}
                      className="flex flex-col gap-3 rounded-md border border-[#2a2b30] bg-[#141518] p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="font-semibold text-white">{service.name}</p>
                        <p className="mt-1 text-xs text-zinc-500">
                          Found on {service.evidence.length || 1} website page
                          {(service.evidence.length || 1) === 1 ? "" : "s"}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          onClick={() => void reviewService(service.id, "confirmed")}
                          disabled={serviceBusy !== ""}
                          className="rounded-md bg-accent-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                        >
                          We offer this
                        </button>
                        <button
                          type="button"
                          onClick={() => void reviewService(service.id, "rejected")}
                          disabled={serviceBusy !== ""}
                          className="rounded-md border border-[#303137] px-3 py-1.5 text-xs font-semibold text-zinc-300 disabled:opacity-50"
                        >
                          Not a service
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <form onSubmit={addService} className="mt-5 flex max-w-xl flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="new-business-service">
                Add a service
              </label>
              <input
                id="new-business-service"
                value={newService}
                onChange={(event) => setNewService(event.target.value)}
                placeholder="Add a service, such as Appliance Removal"
                maxLength={160}
                className="min-w-0 flex-1 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent-500"
              />
              <button
                type="submit"
                disabled={!newService.trim() || serviceBusy !== ""}
                className="rounded-md border border-accent-500/40 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {serviceBusy === "add" ? "Adding…" : "Add service"}
              </button>
            </form>

            <div className="mt-8 border-t border-[#26272c] pt-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-2xl">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Your service area
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-white">
                    Where do you want these customers to come from?
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">
                    Confirm the cities, ZIP codes, counties, or mileage range where this location
                    takes jobs. You can also name places you do not serve.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void suggestServiceAreas()}
                  disabled={areaBusy !== ""}
                  className="rounded-md border border-[#303137] bg-[#17181b] px-4 py-2 text-sm font-semibold text-zinc-100 hover:border-accent-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {areaBusy === "suggest" ? "Checking saved details…" : "Check website for places"}
                </button>
              </div>

              <div className="mt-5 rounded-md border border-[#2a2b30] bg-[#141518] p-4">
                <p className="text-sm font-semibold text-white">Find towns inside your work range</p>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-400">
                  Choose miles or driving time. We&apos;ll find nearby towns, then you decide which ones
                  this location actually serves.
                </p>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <div className="rounded-md border border-[#2a2b30] bg-[#101113] p-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      By distance
                    </p>
                    <div className="mt-2 flex items-end gap-2">
                      <label className="text-xs font-semibold text-zinc-300" htmlFor="nearby-service-radius">
                        Miles
                        <input
                          id="nearby-service-radius"
                          value={nearbyRadius}
                          onChange={(event) => setNearbyRadius(event.target.value)}
                          type="number"
                          min="1"
                          max="75"
                          step="1"
                          className="mt-1 block w-24 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => void suggestNearbyCommunities()}
                        disabled={areaBusy !== "" || serviceAreaProfile.map?.status !== "ready"}
                        className="rounded-md bg-accent-500 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {areaBusy === "nearby" ? "Checking towns..." : "Use miles"}
                      </button>
                    </div>
                  </div>
                  <div className="rounded-md border border-[#2a2b30] bg-[#101113] p-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      By driving time
                    </p>
                    <div className="mt-2 flex items-end gap-2">
                      <label className="text-xs font-semibold text-zinc-300" htmlFor="service-drive-time">
                        Minutes
                        <select
                          id="service-drive-time"
                          value={driveTimeMinutes}
                          onChange={(event) => setDriveTimeMinutes(event.target.value)}
                          className="mt-1 block w-28 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
                        >
                          {[15, 20, 30, 45, 60, 75, 90].map((minutes) => (
                            <option key={minutes} value={minutes}>{minutes}</option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => void suggestDriveTimeCommunities()}
                        disabled={
                          areaBusy !== "" ||
                          serviceAreaProfile.map?.status !== "ready" ||
                          !serviceAreaProfile.map?.drive_time_available
                        }
                        className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {areaBusy === "drive-time" ? "Checking roads..." : "Use driving time"}
                      </button>
                    </div>
                    {!serviceAreaProfile.map?.drive_time_available ? (
                      <p className="mt-2 text-xs leading-5 text-zinc-500">
                        Driving-time maps will be available after the account connection is finished.
                      </p>
                    ) : (
                      <p className="mt-2 text-xs leading-5 text-zinc-500">
                        Uses the road network, not live traffic.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <ServiceAreaMap
                profile={serviceAreaProfile}
                busy={areaBusy !== ""}
                onSaveBoundary={saveCustomBoundary}
              />

              {confirmedIncludedAreas.length ? (
                <div className="mt-5">
                  <p className="text-xs font-semibold text-zinc-300">Places this location serves</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {confirmedIncludedAreas.map((area) => (
                      <span
                        key={area.id}
                        className="inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-100"
                      >
                        <ProductIcon name="locations" size={14} />
                        {area.name}{area.region && area.area_type !== "radius" ? `, ${area.region}` : ""}
                        <button
                          type="button"
                          onClick={() => void reviewServiceArea(area.id, "rejected")}
                          disabled={areaBusy !== ""}
                          aria-label={`Remove ${area.name} from this location's service area`}
                          className="ml-1 text-xs text-emerald-100/60 hover:text-white disabled:opacity-50"
                        >
                          Remove
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-5 border-l-2 border-amber-400 pl-4">
                  <p className="text-sm font-semibold text-amber-100">Confirm at least one service area</p>
                  <p className="mt-1 text-sm text-zinc-400">
                    Search ideas can match your services, but they will wait for review until we know
                    where this location actually takes jobs.
                  </p>
                </div>
              )}

              {confirmedExcludedAreas.length ? (
                <div className="mt-4">
                  <p className="text-xs font-semibold text-zinc-300">Places this location does not serve</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {confirmedExcludedAreas.map((area) => (
                      <span
                        key={area.id}
                        className="inline-flex items-center gap-2 rounded-full border border-rose-500/25 bg-rose-500/10 px-3 py-1.5 text-sm text-rose-100"
                      >
                        Not {area.name}
                        <button
                          type="button"
                          onClick={() => void reviewServiceArea(area.id, "rejected")}
                          disabled={areaBusy !== ""}
                          aria-label={`Remove the ${area.name} exclusion`}
                          className="ml-1 text-xs text-rose-100/60 hover:text-white disabled:opacity-50"
                        >
                          Remove
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {suggestedAreas.length ? (
                <div className="mt-5">
                  <p className="text-xs font-semibold text-zinc-300">
                    Do you take jobs in these places?
                  </p>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {suggestedAreas.map((area) => (
                      <div
                        key={area.id}
                        className="flex flex-col gap-3 rounded-md border border-[#2a2b30] bg-[#141518] p-4 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="font-semibold text-white">
                            {area.name}{area.region ? `, ${area.region}` : ""}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500">
                            {area.evidence.find((item) => item.distance_miles !== undefined)?.note ??
                              `Found in your saved ${area.area_type === "postal_code" ? "ZIP or postal code" : area.area_type} details`}
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <button
                            type="button"
                            onClick={() => void reviewServiceArea(area.id, "confirmed")}
                            disabled={areaBusy !== ""}
                            className="rounded-md bg-accent-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                          >
                            We serve this area
                          </button>
                          <button
                            type="button"
                            onClick={() => void reviewServiceArea(area.id, "rejected")}
                            disabled={areaBusy !== ""}
                            className="rounded-md border border-[#303137] px-3 py-1.5 text-xs font-semibold text-zinc-300 disabled:opacity-50"
                          >
                            Do not use
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <form onSubmit={addServiceArea} className="mt-5 grid max-w-4xl gap-2 md:grid-cols-[150px_minmax(180px,1fr)_minmax(130px,0.6fr)_150px_auto]">
                <label className="sr-only" htmlFor="service-area-type">Area type</label>
                <select
                  id="service-area-type"
                  value={newAreaType}
                  onChange={(event) => setNewAreaType(event.target.value as BusinessServiceAreaItem["area_type"])}
                  className="rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
                >
                  <option value="city">City or town</option>
                  <option value="postal_code">ZIP code</option>
                  <option value="county">County</option>
                  <option value="radius">Mileage radius</option>
                </select>
                <label className="sr-only" htmlFor="new-service-area">Service area</label>
                <input
                  id="new-service-area"
                  value={newArea}
                  onChange={(event) => setNewArea(event.target.value)}
                  placeholder={newAreaType === "radius" ? "Miles, such as 25" : "Enter the place"}
                  inputMode={newAreaType === "radius" ? "decimal" : "text"}
                  maxLength={160}
                  className="min-w-0 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent-500"
                />
                <label className="sr-only" htmlFor="new-service-area-region">State or region</label>
                <input
                  id="new-service-area-region"
                  value={newAreaRegion}
                  onChange={(event) => setNewAreaRegion(event.target.value)}
                  placeholder="State"
                  maxLength={120}
                  disabled={newAreaType === "radius"}
                  className="min-w-0 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent-500 disabled:opacity-40"
                />
                <label className="sr-only" htmlFor="service-area-relationship">Service choice</label>
                <select
                  id="service-area-relationship"
                  value={newAreaRelationship}
                  onChange={(event) => setNewAreaRelationship(event.target.value as BusinessServiceAreaItem["relationship"])}
                  className="rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
                >
                  <option value="included">We serve here</option>
                  <option value="excluded">We do not serve here</option>
                </select>
                <button
                  type="submit"
                  disabled={!newArea.trim() || areaBusy !== ""}
                  className="rounded-md border border-accent-500/40 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {areaBusy === "add" ? "Adding…" : "Add area"}
                </button>
              </form>
              {newAreaType === "radius" ? (
                <p className="mt-2 text-xs text-zinc-500">
                  Mileage starts from this location&apos;s saved map position.
                </p>
              ) : null}
            </div>
          </section>
        ) : null}

        {loading || loadingLocations ? (
          <LoadingCard
            title="Loading customer searches"
            summary="Checking the saved research for the selected location."
          />
        ) : null}

        {error ? (
          <section className="rounded-md border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}
        {notice ? (
          <section className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            {notice}
          </section>
        ) : null}
        {aiNotice ? (
          <section className={`rounded-md border p-4 text-sm ${
            aiNotice.success
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
              : "border-amber-500/20 bg-amber-500/10 text-amber-100"
          }`}>
            {aiNotice.message}
          </section>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="Add a location before finding searches"
            summary="Keyword research needs a real business, website, and city so results can be matched to the right market."
            actionLabel="Manage locations"
            onAction={() => router.push("/locations")}
          />
        ) : null}

        {!loading && campaigns.length > 0 && !data.run ? (
          <section className="grid gap-6 border-y border-[#26272c] py-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                Ready for {selectedCampaign?.name || "this location"}
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">
                Find real searches without building a list by hand
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                InsightOS checks your website, work area, Google search history, current rankings,
                and monthly search estimates. You confirm the work you sell and where you take jobs.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void runDiscovery()}
              disabled={busy !== ""}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-accent-500 px-5 py-3 font-semibold text-white disabled:opacity-50"
            >
              <ProductIcon name="keyword-research" size={19} />
              {busy === "discover" ? "Finding searches…" : "Find customer searches"}
            </button>
          </section>
        ) : null}

        {!loading && data.run ? (
          <>
            <section className="border-b border-[#26272c] pb-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    What matters now
                  </p>
                  <h2 className="mt-1 text-2xl font-bold tracking-tight text-white">
                    {data.summary.best_matches > 0
                      ? `${data.summary.best_matches} searches match the work you offer`
                      : "No strong matches have been confirmed yet"}
                  </h2>
                  <p className="mt-2 text-sm text-zinc-400">
                    Start with the strongest matches. Unclear and unrelated searches stay in
                    separate views so you do not have to sort through them.
                  </p>
                </div>
                <div className="flex flex-col items-stretch gap-2 sm:items-end">
                  <div className="flex flex-wrap gap-2">
                    {data.summary.needs_review > 0 ? (
                      <button
                        type="button"
                        onClick={() => void reviewUnclearSearches()}
                        disabled={
                          busy !== "" ||
                          serviceProfile.summary.confirmed === 0 ||
                          serviceAreaProfile.summary.confirmed_included === 0
                        }
                        className="rounded-md border border-violet-500/35 bg-violet-500/10 px-4 py-2.5 text-sm font-semibold text-violet-100 hover:bg-violet-500/15 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {busy === "review" ? "Reviewing unclear searches…" : "Review unclear searches"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void trackSelected()}
                      disabled={selectedIds.size === 0 || busy !== ""}
                      className="rounded-md bg-accent-500 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#232428] disabled:text-zinc-500"
                    >
                      {busy === "track" ? "Adding…" : `Track selected${selectedIds.size ? ` (${selectedIds.size})` : ""}`}
                    </button>
                  </div>
                  {data.summary.needs_review > 0 ? (
                    <p className="text-xs text-zinc-500">
                      Checks up to 8 phrases against your confirmed services and service areas. It cannot change your website.
                      {reviewCreditPrice ? (
                        <span className="ml-1 text-violet-200">
                          Uses {reviewCreditPrice.credits} Insight {reviewCreditPrice.credits === 1 ? "Credit" : "Credits"}.
                        </span>
                      ) : null}
                    </p>
                  ) : null}
                </div>
              </div>
              <dl className="mt-6 grid gap-4 sm:grid-cols-4">
                {[
                  ["Best matches", data.summary.best_matches],
                  ["Needs your review", data.summary.needs_review],
                  ["Google finds you", data.summary.already_found],
                  ["Already tracking", data.summary.tracked],
                ].map(([label, value]) => (
                  <div key={String(label)} className="border-l-2 border-[#303137] pl-4 first:border-accent-500">
                    <dt className="text-xs text-zinc-500">{label}</dt>
                    <dd className="mt-1 text-2xl font-bold text-white">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            {data.history ? (
              <section className="border-b border-[#26272c] pb-6">
                <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      Search movement
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-white">
                      What changed since the last research
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                      Compare saved research dates to see which customer searches are growing,
                      slipping, appearing for the first time, or no longer showing up.
                    </p>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {data.history.snapshot_count} saved {data.history.snapshot_count === 1 ? "date" : "dates"}
                  </p>
                </div>

                {data.history.comparison ? (
                  <>
                    <dl className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="border-l-2 border-emerald-500 pl-4">
                        <dt className="text-xs text-zinc-500">New searches found</dt>
                        <dd className="mt-1 text-2xl font-bold text-emerald-300">
                          ↑ {data.history.comparison.new_searches}
                        </dd>
                      </div>
                      <div className="border-l-2 border-emerald-500 pl-4">
                        <dt className="text-xs text-zinc-500">Searches moving up</dt>
                        <dd className="mt-1 text-2xl font-bold text-emerald-300">
                          ↑ {data.history.comparison.improved_positions}
                        </dd>
                      </div>
                      <div className={`border-l-2 pl-4 ${
                        data.history.comparison.demand_change >= 0
                          ? "border-emerald-500"
                          : "border-rose-500"
                      }`}>
                        <dt className="text-xs text-zinc-500">Estimated searches changed</dt>
                        <dd className={`mt-1 text-2xl font-bold ${
                          data.history.comparison.demand_change >= 0
                            ? "text-emerald-300"
                            : "text-rose-300"
                        }`}>
                          {data.history.comparison.demand_change >= 0 ? "↑" : "↓"}{" "}
                          {Math.abs(data.history.comparison.demand_change).toLocaleString()}
                        </dd>
                      </div>
                      <div className="border-l-2 border-[#303137] pl-4">
                        <dt className="text-xs text-zinc-500">No longer found</dt>
                        <dd className="mt-1 text-2xl font-bold text-zinc-200">
                          {data.history.comparison.no_longer_seen}
                        </dd>
                      </div>
                    </dl>

                    {trendChartData.length > 1 ? (
                      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.7fr)]">
                        <div className="h-[280px] min-w-0">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={trendChartData} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
                              <CartesianGrid stroke="#27282d" vertical={false} />
                              <XAxis dataKey="date" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
                              <YAxis yAxisId="demand" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
                              <YAxis yAxisId="count" orientation="right" allowDecimals={false} tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
                              <Tooltip
                                contentStyle={{ background: "#141518", border: "1px solid #303137", borderRadius: 6 }}
                                labelStyle={{ color: "#f4f4f5" }}
                              />
                              <Legend wrapperStyle={{ fontSize: 12, color: "#d4d4d8" }} />
                              <Line yAxisId="demand" type="monotone" dataKey="measured_demand" name="Estimated searches/month" stroke="#ff6a1a" strokeWidth={2.5} dot={{ r: 3 }} />
                              <Line yAxisId="count" type="monotone" dataKey="useful_searches" name="Helpful searches" stroke="#38bdf8" strokeWidth={2} dot={{ r: 3 }} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <div className="border-l border-[#26272c] pl-5 text-sm leading-6 text-zinc-400">
                          <p className="font-semibold text-white">How to read this</p>
                          <p className="mt-2">
                            Orange shows the estimated monthly searches across your confirmed list.
                            Blue shows how many searches match your services and work area.
                          </p>
                          <p className="mt-3 text-xs text-zinc-500">
                            Compared {shortDate(data.history.comparison.previous_completed_at)} with{" "}
                            {shortDate(data.history.comparison.current_completed_at)}. Search counts are estimates, not promised jobs.
                          </p>
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="mt-5 border-l-2 border-sky-500 pl-4">
                    <p className="font-semibold text-white">Your trend line has started</p>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      Refresh this research on another date to see which searches changed. The first saved date is your starting point.
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {data.filter_quality ? (
              <section className="grid gap-4 border-b border-[#26272c] pb-6 lg:grid-cols-[1fr_auto] lg:items-center">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Your saved choices
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-white">
                    {data.filter_quality.headline}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                    {data.filter_quality.message}
                  </p>
                </div>
                <div className="flex gap-6 text-right">
                  <div>
                    <p className="text-2xl font-bold text-white">{data.filter_quality.owner_checked}</p>
                    <p className="text-xs text-zinc-500">choices checked</p>
                  </div>
                  {data.filter_quality.agreement_rate !== null &&
                  data.filter_quality.agreement_rate !== undefined &&
                  data.filter_quality.automatic_decisions_checked >= data.filter_quality.minimum_sample ? (
                    <div>
                      <p className="text-2xl font-bold text-emerald-300">
                        {data.filter_quality.agreement_rate}%
                      </p>
                      <p className="text-xs text-zinc-500">matched your answer</p>
                    </div>
                  ) : null}
                </div>
              </section>
            ) : null}

            {data.run.warnings.length ? (
              <section className="rounded-md border border-amber-500/20 bg-amber-500/8 p-4">
                <p className="text-sm font-semibold text-amber-100">
                  Some search estimates could not update
                </p>
                <p className="mt-2 text-sm text-amber-50/80">
                  Your saved rankings are still shown. Try Refresh search ideas again in a few
                  minutes.
                </p>
              </section>
            ) : null}

            {searchClusters.length ? (
              <section className="border-b border-[#26272c] pb-6">
                <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      Customer needs
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-white">
                      Plan related searches together
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                      Searches are grouped by the service, customer need, and place they mention.
                      Each group also shows whether your website already has a useful page for it.
                    </p>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {searchClusters.length} useful {searchClusters.length === 1 ? "group" : "groups"}
                  </p>
                </div>
                <div className="mt-5 grid gap-x-8 gap-y-5 md:grid-cols-2">
                  {searchClusters.map((cluster) => (
                    <article
                      key={cluster.key}
                      className={`border-l-2 pl-4 ${
                        selectedClusterKey === cluster.key ? "border-accent-500" : "border-[#303137]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="font-semibold text-white">{cluster.label}</h3>
                          <p className="mt-1 text-xs text-zinc-500">
                            {cluster.keywordCount} {cluster.keywordCount === 1 ? "search" : "searches"}
                            {cluster.totalDemand > 0
                              ? ` · about ${cluster.totalDemand.toLocaleString()} searches/month`
                              : " · no search estimate yet"}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setFilter("best");
                              setSelectedClusterKey(cluster.key);
                            }}
                            className="text-xs font-semibold text-accent-300 hover:text-white"
                          >
                            Review group
                          </button>
                          {actionByCluster.has(cluster.key) ? (
                            <button
                              type="button"
                              onClick={() => router.push("/opportunities")}
                              className="text-xs font-semibold text-emerald-300 hover:text-white"
                            >
                              {["GENERATED", "VALIDATED", "APPROVED", "SCHEDULED"].includes(
                                actionByCluster.get(cluster.key)?.status ?? "",
                              )
                                ? "In Next Steps →"
                                : "Already handled →"}
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => void createNextStep(cluster)}
                              disabled={!cluster.hasMeasuredEvidence || actionBusy !== ""}
                              title={
                                cluster.hasMeasuredEvidence
                                  ? "Add a reviewable action backed by these saved searches"
                                  : "Check again after rankings or search estimates are available"
                              }
                              className="rounded-md border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {actionBusy === cluster.key ? "Adding…" : "Add to Next Steps"}
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="mt-3 text-sm leading-5 text-zinc-300">
                        {cluster.keywords.join(" · ")}
                      </p>
                      <div className="mt-3 text-xs leading-5">
                        {cluster.targetPage?.status === "existing" && cluster.targetPage.url ? (
                          <p className="text-emerald-200">
                            Page to improve:{" "}
                            <a
                              href={cluster.targetPage.url}
                              target="_blank"
                              rel="noreferrer"
                              className="underline decoration-emerald-400/40 underline-offset-2 hover:text-white"
                            >
                              {cluster.targetPage.title || cluster.targetPage.url}
                            </a>
                          </p>
                        ) : (
                          <p className="text-amber-200">
                            Page opportunity: your saved website pages do not clearly cover this group yet.
                          </p>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            {chartData.length ? (
              <section className="grid gap-5 border-b border-[#26272c] pb-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.7fr)]">
                <div>
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      Estimated monthly searches
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-white">What customers search most</h2>
                  </div>
                  <div className="h-[280px] min-w-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 25 }}>
                        <CartesianGrid stroke="#27282d" horizontal={false} />
                        <XAxis type="number" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} />
                        <YAxis
                          type="category"
                          dataKey="name"
                          width={170}
                          tick={{ fill: "#d4d4d8", fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip
                          cursor={{ fill: "rgba(255,255,255,0.035)" }}
                          contentStyle={{ background: "#141518", border: "1px solid #303137", borderRadius: 6 }}
                          formatter={(value) => [`About ${Number(value).toLocaleString()} searches/month`, "Estimated searches"]}
                        />
                        <Bar dataKey="demand" fill="#ff6a1a" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="border-l border-[#26272c] pl-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    How to use this
                  </p>
                  <ol className="mt-4 space-y-4 text-sm text-zinc-300">
                    <li className="flex gap-3"><span className="font-bold text-accent-400">1</span><span>Choose searches that describe work you want.</span></li>
                    <li className="flex gap-3"><span className="font-bold text-accent-400">2</span><span>Give priority to searches where you already appear.</span></li>
                    <li className="flex gap-3"><span className="font-bold text-accent-400">3</span><span>Track them so movement shows on Search Rankings.</span></li>
                  </ol>
                </div>
              </section>
            ) : null}

            <section>
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Search list
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Choose what to track</h2>
                  {selectedCluster ? (
                    <p className="mt-2 text-sm text-zinc-400">
                      Showing {selectedCluster.keywordCount} searches in {selectedCluster.label}.{" "}
                      <button
                        type="button"
                        onClick={() => setSelectedClusterKey(null)}
                        className="font-semibold text-accent-300 hover:text-white"
                      >
                        Show every group
                      </button>
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Filter customer searches">
                  {FILTERS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => {
                        setFilter(option.id);
                        setSelectedClusterKey(null);
                      }}
                      aria-pressed={filter === option.id}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                        filter === option.id
                          ? "bg-accent-500 text-white"
                          : "bg-[#18191c] text-zinc-400 hover:text-white"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {selectableVisible.length ? (
                <label className="mt-5 inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-zinc-400 hover:text-white">
                  <input
                    type="checkbox"
                    checked={selectableVisible.every((item) => selectedIds.has(item.id))}
                    onChange={(event) => {
                      const next = new Set(selectedIds);
                      selectableVisible.forEach((item) =>
                        event.target.checked ? next.add(item.id) : next.delete(item.id),
                      );
                      setSelectedIds(next);
                    }}
                    className="accent-orange-500"
                  />
                  Select all shown
                </label>
              ) : null}

              <div className="mt-3 divide-y divide-[#26272c] border-y border-[#26272c]">
                {filteredItems.map((item) => (
                  <article key={item.id} className="grid gap-4 py-5 lg:grid-cols-[28px_minmax(220px,1.2fr)_0.65fr_0.55fr_minmax(260px,1fr)] lg:items-center">
                    <div>
                      {item.tracked_at ? (
                        <ProductIcon name="check" size={19} className="text-emerald-400" label="Already tracked" />
                      ) : item.relevance_status === "unrelated" ? (
                        <span className="text-sm text-zinc-600" aria-label="Hidden as unrelated">—</span>
                      ) : (
                        <input
                          type="checkbox"
                          aria-label={`Track ${item.keyword}`}
                          checked={selectedIds.has(item.id)}
                          onChange={(event) => {
                            const next = new Set(selectedIds);
                            event.target.checked ? next.add(item.id) : next.delete(item.id);
                            setSelectedIds(next);
                          }}
                          className="h-4 w-4 accent-orange-500"
                        />
                      )}
                    </div>
                    <div>
                      <h3 className="font-semibold text-white">{item.keyword}</h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${groupTone(item.opportunity_group)}`}>
                          {groupLabel(item.opportunity_group)}
                        </span>
                        <span className="rounded-full bg-[#1a1b1e] px-2 py-0.5 text-[11px] text-zinc-400">
                          {intentLabel(item.intent)}
                        </span>
                        {item.matched_service_name ? (
                          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200">
                            Matches {item.matched_service_name}
                          </span>
                        ) : null}
                        {item.matched_service_area_name ? (
                          <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                            item.area_match_type === "excluded"
                              ? "bg-rose-500/10 text-rose-200"
                              : "bg-sky-500/10 text-sky-200"
                          }`}>
                            {item.area_match_type === "excluded" ? "Outside area: " : "Serves "}
                            {item.matched_service_area_name}
                          </span>
                        ) : null}
                        {item.ai_review_status === "validated" ? (
                          <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-200">
                            Reviewed
                          </span>
                        ) : null}
                        {item.competitor_evidence?.length ? (
                          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">
                            Competitor opportunity
                          </span>
                        ) : null}
                        {item.trend && item.trend.status !== "not_enough_history" ? (
                          <span className={`rounded-full px-2 py-0.5 text-[11px] ${trendTone(item.trend.status)}`}>
                            {item.trend.status === "new" ||
                            item.trend.status === "gaining_demand" ||
                            item.trend.status === "improving_rank"
                              ? "↑ "
                              : item.trend.status === "losing_demand" ||
                                  item.trend.status === "slipping_rank"
                                ? "↓ "
                                : "→ "}
                            {item.trend.label}
                          </span>
                        ) : null}
                      </div>
                      {item.relevance_reason ? (
                        <p className="mt-2 text-xs leading-5 text-zinc-500">{item.relevance_reason}</p>
                      ) : null}
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Estimated monthly searches</p>
                      <p className="mt-1 text-sm font-semibold text-zinc-100">{demandLabel(item.search_volume)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Where you appear</p>
                      <p className="mt-1 text-sm font-semibold text-zinc-100">{positionLabel(item)}</p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">
                        {simplifyCustomerCopy(item.recommended_action, {
                          fallback: "Review this search before tracking it.",
                        })}
                      </p>
                      <p className="mt-1 text-sm leading-5 text-zinc-400">
                        {simplifyCustomerCopy(item.recommendation_reason, {
                          fallback: "Use your services and work area to decide whether this search belongs on your list.",
                        })}
                      </p>
                      {item.competitor_evidence?.length ? (
                        <p className="mt-2 text-xs leading-5 text-amber-100/80">
                          Seen from {item.competitor_evidence.map((competitor, index) => {
                            const name = competitor.label || competitor.domain;
                            return (
                              <span key={`${competitor.competitor_id}-${competitor.url || index}`}>
                                {index > 0 ? " · " : ""}
                                {competitor.url ? (
                                  <a
                                    href={competitor.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="underline decoration-amber-300/30 underline-offset-2 hover:text-white"
                                  >
                                    {name}
                                  </a>
                                ) : name}
                                {competitor.position
                                  ? ` near #${Math.round(competitor.position)}`
                                  : ""}
                              </span>
                            );
                          })}
                        </p>
                      ) : null}
                      <details className="mt-2 text-xs text-zinc-500">
                        <summary className="cursor-pointer hover:text-zinc-300">Why this search is listed</summary>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                          <span>Priority score: {item.opportunity_score}/100</span>
                          {item.keyword_difficulty !== null && item.keyword_difficulty !== undefined ? (
                            <span>How hard it may be to rank: {item.keyword_difficulty}/100</span>
                          ) : null}
                          {item.cpc ? <span>Ad cost: ${item.cpc.toFixed(2)}/click</span> : null}
                          <span>What we checked: {item.source_types.map(sourceLabel).join(", ")}</span>
                        </div>
                      </details>
                      {!item.tracked_at ? (
                        <div className="mt-3 border-t border-[#26272c] pt-3">
                          {item.owner_feedback ? (
                            <p className="mb-2 text-xs font-semibold text-emerald-200">
                              Saved from your choice
                            </p>
                          ) : null}
                          {item.relevance_status !== "relevant" ? (
                            <select
                              aria-label={`Service matched by ${item.keyword}`}
                              value={
                                serviceChoiceBySuggestion[item.id]
                                || item.matched_service_id
                                || serviceProfile.items.find(
                                  (service) => service.status === "confirmed",
                                )?.id
                                || ""
                              }
                              onChange={(event) => setServiceChoiceBySuggestion((current) => ({
                                ...current,
                                [item.id]: event.target.value,
                              }))}
                              className="mb-2 w-full rounded-md border border-[#303137] bg-[#15161a] px-2.5 py-2 text-xs text-zinc-200"
                            >
                              {serviceProfile.items
                                .filter((service) => service.status === "confirmed")
                                .map((service) => (
                                  <option key={service.id} value={service.id}>
                                    {service.name}
                                  </option>
                                ))}
                            </select>
                          ) : null}
                          <div className="flex flex-wrap gap-2">
                            {item.relevance_status !== "relevant" ? (
                              <button
                                type="button"
                                onClick={() => void saveSearchFeedback(item, "relevant")}
                                disabled={feedbackBusy === item.id}
                                className="rounded-md border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-100 disabled:opacity-40"
                              >
                                Matches this service
                              </button>
                            ) : null}
                            {item.relevance_status !== "unrelated" ? (
                              <button
                                type="button"
                                onClick={() => void saveSearchFeedback(item, "unrelated")}
                                disabled={feedbackBusy === item.id}
                                className="rounded-md border border-[#34353b] px-2.5 py-1.5 text-xs font-semibold text-zinc-300 disabled:opacity-40"
                              >
                                Not relevant
                              </button>
                            ) : null}
                            {item.owner_feedback ? (
                              <button
                                type="button"
                                onClick={() => void saveSearchFeedback(item, "cleared")}
                                disabled={feedbackBusy === item.id}
                                className="px-1 py-1.5 text-xs font-semibold text-zinc-500 hover:text-white disabled:opacity-40"
                              >
                                Undo my choice
                              </button>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>

              {filteredItems.length === 0 ? (
                <p className="py-10 text-center text-sm text-zinc-500">
                  {filter === "best" && serviceProfile.summary.confirmed === 0
                    ? "Confirm the services this location offers to create a useful Best matches list."
                    : filter === "best" && serviceAreaProfile.summary.confirmed_included === 0
                      ? "Confirm where this location takes jobs to create a useful Best matches list."
                      : "No searches match this view."}
                </p>
              ) : null}
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
