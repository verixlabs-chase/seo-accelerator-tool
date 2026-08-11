"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
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
import {
  flattenBusinessLocations,
  getHierarchyTruth,
} from "../truth/hierarchyTruth.mjs";

type Me = {
  organization_id?: string;
};

type Campaign = {
  id: string;
  name: string;
  domain: string;
  setup_state: string;
};

type ExecutionLocation = {
  id: string;
  status: string;
};

type BusinessLocation = {
  id: string;
  sub_account_id?: string | null;
  subaccount_name?: string;
  name: string;
  domain?: string | null;
  primary_city?: string | null;
  city?: string | null;
  region?: string | null;
  country_code?: string | null;
  address_line1?: string | null;
  postal_code?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  coordinate_precision?: string | null;
  provider_location_code?: string | null;
  provider_location_name?: string | null;
  status: string;
  campaigns: Campaign[];
  execution_locations: ExecutionLocation[];
  performance: {
    data_available: boolean;
    as_of?: string | null;
    avg_position?: number | null;
    sessions: number;
    conversions: number;
    technical_issue_count: number;
    reviews_last_30d: number;
    avg_rating_last_30d?: number | null;
  };
};

type SubAccount = {
  id: string;
  name: string;
  status: string;
  business_locations: BusinessLocation[];
  unassigned_campaigns: Campaign[];
  counts: {
    business_locations: number;
    campaigns: number;
    execution_locations: number;
  };
};

type Hierarchy = {
  organization_id: string;
  subaccounts: SubAccount[];
  unassigned: {
    business_locations: BusinessLocation[];
    execution_locations: ExecutionLocation[];
    campaigns: Campaign[];
  };
  totals: {
    subaccounts: number;
    business_locations: number;
    execution_locations: number;
    campaigns: number;
    active_business_locations: number;
    unassigned_business_locations: number;
    integrity_issues: number;
  };
  integrity_issues: Array<{
    entity_type: string;
    entity_id: string;
    reason_code: string;
  }>;
};

type PortfolioReason = {
  code: string;
  severity: "urgent" | "needs_attention" | "watch" | "on_track";
  title: string;
  detail: string;
  action_label: string;
  action_href: string;
  evidence?: { label: string; value: string | number } | null;
};

type PortfolioLocation = {
  location_id: string;
  location_name: string;
  location_status: string;
  city?: string | null;
  region?: string | null;
  account_group?: { id: string; name: string } | null;
  campaign_id?: string | null;
  campaign_ids: string[];
  attention_state: "urgent" | "needs_attention" | "watch" | "on_track";
  attention_label: string;
  reason_count: number;
  reasons: PortfolioReason[];
  next_action: { label: string; href: string; campaign_id?: string | null };
  connections: {
    healthy: number;
    updating: number;
    needs_attention: number;
    needs_setup: number;
  };
  open_actions: number;
  performance: {
    data_available: boolean;
    as_of?: string | null;
    clicks: number;
    impressions: number;
    avg_position?: number | null;
    technical_issue_count: number;
    reviews_last_30d: number;
    avg_rating_last_30d?: number | null;
  };
};

type SharedIssueLocation = {
  location_id: string;
  location_name: string;
  city?: string | null;
  region?: string | null;
  campaign_id?: string | null;
  detail: string;
  evidence?: { label: string; value: string | number } | null;
  action_label: string;
  action_href: string;
};

type SharedIssue = {
  code: string;
  severity: PortfolioLocation["attention_state"];
  attention_label: string;
  title: string;
  summary: string;
  location_count: number;
  locations: SharedIssueLocation[];
};

type RepeatableWin = {
  code: string;
  title: string;
  summary: string;
  source: {
    location_id: string;
    location_name: string;
    campaign_id?: string | null;
    metric: { label: string; value: string | number };
  };
  targets: Array<{
    location_id: string;
    location_name: string;
    campaign_id?: string | null;
    metric: { label: string; value: string | number };
  }>;
  action: { label: string; href: string; campaign_id?: string | null };
  guardrail: string;
};

type PortfolioTrendMetric = {
  code: "daily_clicks" | "daily_impressions" | "avg_position" | "website_issues";
  label: string;
  current?: number | null;
  previous?: number | null;
  change?: number | null;
  change_percent?: number | null;
  direction: "improved" | "declined" | "steady" | "not_measured";
  tone: "positive" | "negative" | "neutral";
  unit: string;
};

type PortfolioTrendPoint = {
  date: string;
  clicks: number;
  impressions: number;
  avg_position?: number | null;
  website_issues: number;
  locations_reporting: number;
};

type PortfolioChangeAlert = {
  code: string;
  tone: "positive" | "negative";
  location_id: string;
  location_name: string;
  campaign_id?: string | null;
  title: string;
  detail: string;
  evidence: { label: string; value: string | number };
  action: { label: string; href: string };
};

type PortfolioTrends = {
  data_state: "ready" | "collecting_history" | "no_history";
  window_days: number;
  minimum_reporting_days: number;
  date_from?: string | null;
  date_to?: string | null;
  comparison_date_from?: string | null;
  comparison_date_to?: string | null;
  locations_compared: number;
  locations_excluded: number;
  coverage_note: string;
  summary: PortfolioTrendMetric[];
  points: PortfolioTrendPoint[];
  alerts: PortfolioChangeAlert[];
};

type PortfolioOverview = {
  generated_at: string;
  summary: {
    headline: string;
    next_step?: string | null;
    active_locations: number;
    archived_locations: number;
    locations_with_saved_performance: number;
    locations_needing_attention: number;
    urgent: number;
    needs_attention: number;
    watch: number;
    on_track: number;
  };
  top_attention: PortfolioLocation[];
  shared_issues: SharedIssue[];
  repeatable_wins: RepeatableWin[];
  trends: PortfolioTrends;
  locations: PortfolioLocation[];
};

const EMPTY_TOTALS: Hierarchy["totals"] = {
  subaccounts: 0,
  business_locations: 0,
  execution_locations: 0,
  campaigns: 0,
  active_business_locations: 0,
  unassigned_business_locations: 0,
  integrity_issues: 0,
};

const inputClass =
  "mt-1.5 w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm text-white outline-none transition placeholder:text-zinc-600 focus:border-accent-500/55";
const labelClass =
  "block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500";
const primaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-accent-500/35 bg-accent-500/12 px-3.5 py-2 text-sm font-semibold text-white transition hover:border-accent-500/60 hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-[#303137] bg-[#17181b] px-3 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-[#1d1e22] disabled:opacity-50";

function titleCase(value?: string) {
  return (value || "unknown")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function statusClasses(status?: string) {
  if (status === "active" || status === "Active") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-100";
  }
  if (status === "archived") {
    return "border-zinc-500/20 bg-zinc-500/10 text-zinc-300";
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-100";
}

function attentionClasses(state: PortfolioLocation["attention_state"]) {
  if (state === "urgent") return "border-rose-500/30 bg-rose-500/10 text-rose-100";
  if (state === "needs_attention") return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  if (state === "watch") return "border-sky-500/25 bg-sky-500/10 text-sky-100";
  return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
}

function positionLabel(value?: number | null) {
  return value == null ? "Not measured" : `#${Number(value).toFixed(1)}`;
}

function ratingLabel(value?: number | null) {
  return value == null ? "Not measured" : `${Number(value).toFixed(1)} stars`;
}

function shortDate(value?: string | null) {
  if (!value) return "Not available";
  return new Date(`${value}T12:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function trendValue(item: PortfolioTrendMetric) {
  if (item.current == null) return "Not measured";
  if (item.code === "avg_position") return `#${item.current.toFixed(1)}`;
  return Math.round(item.current).toLocaleString();
}

function trendChangeLabel(item: PortfolioTrendMetric) {
  if (item.direction === "not_measured") return "Not enough information";
  if (item.direction === "steady") return "→ No clear change";
  const arrow = item.direction === "improved" ? "↑" : "↓";
  const label = item.direction === "improved" ? "Improved" : "Needs attention";
  if (item.code === "avg_position" && item.change != null) {
    return `${arrow} ${label} by ${Math.abs(item.change).toFixed(1)} positions`;
  }
  if (item.code === "website_issues" && item.change != null) {
    return `${arrow} ${label} by ${Math.abs(item.change).toFixed(0)} problems`;
  }
  if (item.change_percent != null) {
    return `${arrow} ${label} ${Math.abs(item.change_percent).toFixed(0)}%`;
  }
  return `${arrow} ${label}`;
}

export default function LocationsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { reloadLocations, setSelectedCampaignId } = useLocationContext();
  const [me, setMe] = useState<Me | null>(null);
  const [hierarchy, setHierarchy] = useState<Hierarchy | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioOverview | null>(null);
  const [portfolioSort, setPortfolioSort] = useState("attention");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [subaccountName, setSubaccountName] = useState("");
  const [locationName, setLocationName] = useState("");
  const [locationDomain, setLocationDomain] = useState("");
  const [locationCity, setLocationCity] = useState("");
  const [locationRegion, setLocationRegion] = useState("");
  const [locationCountryCode, setLocationCountryCode] = useState("US");
  const [locationSubaccountId, setLocationSubaccountId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");
  const [campaignLocationId, setCampaignLocationId] = useState("");
  const [editingLocationId, setEditingLocationId] = useState("");
  const [geoDraft, setGeoDraft] = useState({
    city: "",
    region: "",
    country_code: "US",
    address_line1: "",
    postal_code: "",
    latitude: "",
    longitude: "",
  });

  const organizationId = me?.organization_id || "";

  const loadHierarchy = useCallback(async (orgId: string) => {
    const [hierarchyResponse, portfolioResponse] = await Promise.all([
      platformApi(`/organizations/${orgId}/hierarchy`, { method: "GET" }),
      platformApi(`/organizations/${orgId}/portfolio-overview`, { method: "GET" }),
    ]);
    const nextHierarchy = (hierarchyResponse?.hierarchy || null) as Hierarchy | null;
    setHierarchy(nextHierarchy);
    setPortfolio((portfolioResponse?.portfolio || null) as PortfolioOverview | null);
    return nextHierarchy;
  }, []);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        const currentUser = (await platformApi("/auth/me", { method: "GET" })) as Me;
        if (!currentUser?.organization_id) {
          throw new Error("An organization context is required to manage locations.");
        }
        setMe(currentUser);
        await loadHierarchy(currentUser.organization_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load locations.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadHierarchy]);

  const activeSubaccounts = useMemo(
    () => (hierarchy?.subaccounts || []).filter((item) => item.status === "active"),
    [hierarchy],
  );
  const allBusinessLocations = useMemo(
    () => flattenBusinessLocations(hierarchy) as BusinessLocation[],
    [hierarchy],
  );
  const activeBusinessLocations = useMemo(
    () => allBusinessLocations.filter((item) => item.status === "active" && item.sub_account_id),
    [allBusinessLocations],
  );
  const sortedPortfolioLocations = useMemo(() => {
    const rows = [...(portfolio?.locations || [])].filter(
      (item) => item.location_status === "active",
    );
    const attentionOrder = { urgent: 0, needs_attention: 1, watch: 2, on_track: 3 };
    return rows.sort((left, right) => {
      if (portfolioSort === "name") return left.location_name.localeCompare(right.location_name);
      if (portfolioSort === "position") {
        return (left.performance.avg_position ?? 9999) - (right.performance.avg_position ?? 9999);
      }
      if (portfolioSort === "rating") {
        return (right.performance.avg_rating_last_30d ?? -1) -
          (left.performance.avg_rating_last_30d ?? -1);
      }
      if (portfolioSort === "issues") {
        return right.performance.technical_issue_count - left.performance.technical_issue_count;
      }
      return (
        attentionOrder[left.attention_state] - attentionOrder[right.attention_state] ||
        right.reason_count - left.reason_count ||
        left.location_name.localeCompare(right.location_name)
      );
    });
  }, [portfolio, portfolioSort]);

  useEffect(() => {
    if (!locationSubaccountId && activeSubaccounts.length > 0) {
      setLocationSubaccountId(activeSubaccounts[0].id);
    }
  }, [activeSubaccounts, locationSubaccountId]);

  useEffect(() => {
    if (!campaignLocationId && activeBusinessLocations.length > 0) {
      setCampaignLocationId(activeBusinessLocations[0].id);
    }
  }, [activeBusinessLocations, campaignLocationId]);

  async function runMutation(action: string, callback: () => Promise<string>) {
    setBusyAction(action);
    setError("");
    setNotice("");
    try {
      const message = await callback();
      if (organizationId) {
        await loadHierarchy(organizationId);
      }
      setNotice(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The change could not be saved.");
    } finally {
      setBusyAction("");
    }
  }

  async function createSubaccount(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !subaccountName.trim()) return;
    await runMutation("subaccount", async () => {
      const response = await platformApi(`/organizations/${organizationId}/subaccounts`, {
        method: "POST",
        body: JSON.stringify({ name: subaccountName.trim() }),
      });
      const createdId = response?.subaccount?.id || "";
      setSubaccountName("");
      if (createdId) setLocationSubaccountId(createdId);
      return "Account group created. Add its first physical location next.";
    });
  }

  async function createLocation(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !locationName.trim() || !locationSubaccountId) return;
    await runMutation("location", async () => {
      const response = await platformApi(
        `/organizations/${organizationId}/business-locations`,
        {
          method: "POST",
          body: JSON.stringify({
            name: locationName.trim(),
            sub_account_id: locationSubaccountId,
            domain: locationDomain.trim() || null,
            primary_city: locationCity.trim() || null,
            city: locationCity.trim() || null,
            region: locationRegion.trim() || null,
            country_code: locationCountryCode.trim().toUpperCase() || "US",
          }),
        },
      );
      const createdId = response?.business_location?.id || "";
      setLocationName("");
      setLocationDomain("");
      setLocationCity("");
      setLocationRegion("");
      setLocationCountryCode("US");
      if (createdId) setCampaignLocationId(createdId);
      return "Business location created with its internal execution scope.";
    });
  }

  async function createCampaign(event: FormEvent) {
    event.preventDefault();
    if (!campaignName.trim() || !campaignDomain.trim() || !campaignLocationId) return;
    await runMutation("campaign", async () => {
      const response = await platformApi("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          name: campaignName.trim(),
          domain: campaignDomain.trim(),
          business_location_id: campaignLocationId,
        }),
      });
      if (!response?.id) {
        throw new Error("The campaign could not be assigned to this location.");
      }
      setCampaignName("");
      setCampaignDomain("");
      await reloadLocations();
      return "Campaign created and assigned to the selected business location.";
    });
  }

  async function archiveLocation(location: BusinessLocation) {
    if (!organizationId) return;
    await runMutation(`archive-${location.id}`, async () => {
      await platformApi(
        `/organizations/${organizationId}/business-locations/${location.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: "archived" }),
        },
      );
      return `${location.name} was archived. Historical campaigns remain available.`;
    });
  }

  function beginEditLocation(location: BusinessLocation) {
    setEditingLocationId(location.id);
    setGeoDraft({
      city: location.city || location.primary_city || "",
      region: location.region || "",
      country_code: location.country_code || "US",
      address_line1: location.address_line1 || "",
      postal_code: location.postal_code || "",
      latitude: location.latitude == null ? "" : String(location.latitude),
      longitude: location.longitude == null ? "" : String(location.longitude),
    });
  }

  async function saveLocationDetails(location: BusinessLocation) {
    if (!organizationId) return;
    const hasLatitude = geoDraft.latitude.trim() !== "";
    const hasLongitude = geoDraft.longitude.trim() !== "";
    if (hasLatitude !== hasLongitude) {
      setError("Latitude and longitude must be saved together.");
      return;
    }
    await runMutation(`geo-${location.id}`, async () => {
      await platformApi(
        `/organizations/${organizationId}/business-locations/${location.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            city: geoDraft.city.trim() || null,
            region: geoDraft.region.trim() || null,
            country_code: geoDraft.country_code.trim().toUpperCase() || "US",
            address_line1: geoDraft.address_line1.trim() || null,
            postal_code: geoDraft.postal_code.trim() || null,
            latitude: hasLatitude ? Number(geoDraft.latitude) : null,
            longitude: hasLongitude ? Number(geoDraft.longitude) : null,
          }),
        },
      );
      setEditingLocationId("");
      return `${location.name} map details were saved. Provider targeting will resolve automatically from this structured location.`;
    });
  }

  function openPortfolioPath(campaignId: string | null | undefined, href: string) {
    if (campaignId) setSelectedCampaignId(campaignId);
    router.push(href || "/dashboard");
  }

  function openPortfolioAction(item: PortfolioLocation) {
    openPortfolioPath(
      item.next_action.campaign_id || item.campaign_id,
      item.next_action.href,
    );
  }

  const totals = hierarchy?.totals || EMPTY_TOTALS;
  const hierarchyTruth = getHierarchyTruth(hierarchy);
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Hierarchy",
        value: hierarchyTruth.label,
        tone: hierarchyTruth.tone as TrustSignal["tone"],
      },
      {
        label: "Account groups",
        value: String(totals.subaccounts),
        tone: totals.subaccounts > 0 ? "success" : "warning",
      },
      {
        label: "Locations",
        value: String(totals.business_locations),
        tone: totals.business_locations > 0 ? "success" : "warning",
      },
      {
        label: "Campaigns",
        value: String(totals.campaigns),
        tone: totals.campaigns > 0 ? "success" : "info",
      },
    ],
    [hierarchyTruth.label, hierarchyTruth.tone, totals],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel="Multi-location portfolio"
      dateRangeLabel="Live account hierarchy"
      topBarActions={
        <button
          className={primaryButtonClass}
          onClick={() =>
            document.getElementById("location-setup")?.scrollIntoView({ behavior: "smooth" })
          }
        >
          Add location
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Business locations"
          title="Manage every location in one place"
          summary="Keep the main business and each physical location connected, while giving every location its own website, search results, and recommended actions."
        />

        <TruthNotice
          title={
            hierarchyTruth.label === "Structured"
              ? "Your location hierarchy is structured."
              : "Finish organizing the location hierarchy."
          }
          tone={hierarchyTruth.tone === "success" ? "info" : "warning"}
        >
          {hierarchyTruth.summary} InsightOS handles the behind-the-scenes records automatically.
        </TruthNotice>

        {loading ? (
          <LoadingCard
            title="Loading locations"
            summary="Reading account groups, locations, and assigned campaigns."
          />
        ) : null}

        {error ? (
          <div className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        {notice ? (
          <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            {notice}
          </div>
        ) : null}

        {!loading ? (
          <>
            <OwnerDecisionPanel
              eyebrow="Portfolio readiness"
              title={
                totals.business_locations === 0
                  ? "Add the first business location"
                  : totals.unassigned_business_locations > 0
                    ? `${totals.unassigned_business_locations} ${totals.unassigned_business_locations === 1 ? "location needs" : "locations need"} an account group`
                    : totals.campaigns < totals.business_locations
                      ? `${totals.business_locations - totals.campaigns} ${totals.business_locations - totals.campaigns === 1 ? "location needs" : "locations need"} search tracking`
                      : portfolio?.summary.headline || "Every location is organized and being tracked"
              }
              summary={
                totals.business_locations === 0
                  ? "Each physical branch needs its own location record before results and recommendations can stay separate."
                  : totals.unassigned_business_locations > 0 || totals.campaigns < totals.business_locations
                    ? hierarchyTruth.summary
                    : "InsightOS compares saved results across your locations and puts the locations needing help first."
              }
              nextStep={
                totals.business_locations === 0
                  ? "Open the guided setup and add the first account group, location, and website."
                  : totals.unassigned_business_locations > 0
                    ? "Assign the unorganized location to the correct business group."
                    : totals.campaigns < totals.business_locations
                      ? "Connect the next location's website so it can receive its own results and actions."
                      : portfolio?.summary.next_step ||
                        "Choose a location below whenever you want to review its individual performance."
              }
              actionLabel={
                totals.campaigns < totals.business_locations || totals.unassigned_business_locations > 0
                  ? "Finish location setup"
                  : portfolio?.top_attention[0]?.next_action.label
              }
              onAction={
                totals.campaigns < totals.business_locations || totals.unassigned_business_locations > 0
                  ? () =>
                      document
                        .getElementById("location-setup")
                        ?.scrollIntoView({ behavior: "smooth" })
                  : portfolio?.top_attention[0]
                    ? () => openPortfolioAction(portfolio.top_attention[0])
                    : undefined
              }
              tone={
                totals.unassigned_business_locations > 0
                  ? "urgent"
                  : totals.business_locations === 0 || totals.campaigns < totals.business_locations
                    ? "warning"
                    : portfolio && portfolio.summary.locations_needing_attention > 0
                      ? "warning"
                      : "positive"
              }
              progress={
                totals.business_locations > 0
                  ? {
                      label: "Locations with individual search tracking",
                      value: totals.campaigns,
                      total: totals.business_locations,
                      summary: "Tracked locations keep their results and recommendations separate.",
                    }
                  : undefined
              }
            />

            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="Needs attention"
                value={String(portfolio?.summary.locations_needing_attention || 0)}
                summary="Locations with a setup, connection, or measured performance problem."
                tone={(portfolio?.summary.locations_needing_attention || 0) > 0 ? "highlight" : undefined}
              />
              <KpiCard
                label="Keep an eye on"
                value={String(portfolio?.summary.watch || 0)}
                summary="Locations with a smaller issue or unfinished action worth watching."
              />
              <KpiCard
                label="On track"
                value={String(portfolio?.summary.on_track || 0)}
                summary="Active locations without a current saved warning."
              />
              <KpiCard
                label="Ready to compare"
                value={`${portfolio?.summary.locations_with_saved_performance || 0}/${portfolio?.summary.active_locations || totals.active_business_locations}`}
                summary="Locations with saved performance data in this comparison."
              />
            </div>

            {portfolio && portfolio.summary.active_locations > 0 ? (
              <section className="mt-6 rounded-md border border-[#2c2d32] bg-[#121316] p-4 shadow-[0_0_30px_rgba(0,0,0,0.3)]">
                <div className="flex flex-col gap-3 border-b border-[#26272c] pb-4 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Multi-location performance
                    </p>
                    <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                      Start with these locations
                    </h2>
                    <p className="mt-1 max-w-2xl text-sm leading-5 text-zinc-400">
                      These are ordered from real saved setup, connection, search, website, and review facts. There is no hidden portfolio score.
                    </p>
                  </div>
                  <span className="text-xs text-zinc-500">
                    Showing up to 3 locations needing attention
                  </span>
                </div>

                {portfolio.top_attention.length > 0 ? (
                  <div className="mt-4 grid gap-3 xl:grid-cols-3">
                    {portfolio.top_attention.map((item, index) => {
                      const reason = item.reasons[0];
                      return (
                        <article
                          key={item.location_id}
                          className="rounded-md border border-[#303137] bg-[#17181b] p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                                Priority {index + 1}
                              </p>
                              <h3 className="mt-1 text-base font-semibold text-white">
                                {item.location_name}
                              </h3>
                              <p className="mt-1 text-xs text-zinc-500">
                                {[item.city, item.region, item.account_group?.name]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </p>
                            </div>
                            <span
                              className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${attentionClasses(item.attention_state)}`}
                            >
                              {item.attention_label}
                            </span>
                          </div>
                          <p className="mt-4 text-sm font-semibold text-white">{reason?.title}</p>
                          <p className="mt-1 text-xs leading-5 text-zinc-400">{reason?.detail}</p>
                          <div className="mt-4 grid grid-cols-3 gap-2 border-y border-[#292a2f] py-3 text-xs">
                            <div>
                              <p className="text-zinc-600">Google position</p>
                              <p className="mt-1 font-semibold text-zinc-200">
                                {positionLabel(item.performance.avg_position)}
                              </p>
                            </div>
                            <div>
                              <p className="text-zinc-600">Recent rating</p>
                              <p className="mt-1 font-semibold text-zinc-200">
                                {ratingLabel(item.performance.avg_rating_last_30d)}
                              </p>
                            </div>
                            <div>
                              <p className="text-zinc-600">Website problems</p>
                              <p className="mt-1 font-semibold text-zinc-200">
                                {item.performance.technical_issue_count}
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            className={`${primaryButtonClass} mt-4 w-full`}
                            onClick={() => openPortfolioAction(item)}
                          >
                            {item.next_action.label}
                          </button>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4">
                    <p className="text-sm font-semibold text-emerald-100">
                      Every active location is on track.
                    </p>
                    <p className="mt-1 text-xs leading-5 text-zinc-400">
                      No current setup, connection, website, ranking, or review warning was found in the saved comparison.
                    </p>
                  </div>
                )}

                {portfolio.trends.data_state === "ready" ? (
                  <section className="mt-4 rounded-md border border-[#2b2c31] bg-[#151619] p-4">
                    <div className="flex flex-col gap-3 border-b border-[#292a2f] pb-4 lg:flex-row lg:items-end lg:justify-between">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                          Recent movement
                        </p>
                        <h3 className="mt-1.5 text-base font-semibold text-white">
                          What changed across your locations
                        </h3>
                        <p className="mt-1 text-xs leading-5 text-zinc-400">
                          {shortDate(portfolio.trends.date_from)}–{shortDate(portfolio.trends.date_to)} compared with {shortDate(portfolio.trends.comparison_date_from)}–{shortDate(portfolio.trends.comparison_date_to)}.
                        </p>
                      </div>
                      <p className="max-w-xl text-xs leading-5 text-zinc-500">
                        {portfolio.trends.coverage_note}
                      </p>
                    </div>

                    <div className="grid border-b border-[#292a2f] md:grid-cols-2 xl:grid-cols-4">
                      {portfolio.trends.summary.map((item) => (
                        <div
                          key={item.code}
                          className="border-b border-[#292a2f] px-3 py-4 last:border-b-0 md:[&:nth-last-child(-n+2)]:border-b-0 xl:border-b-0 xl:border-r xl:last:border-r-0"
                        >
                          <p className="text-[11px] text-zinc-500">{item.label}</p>
                          <div className="mt-1 flex flex-wrap items-baseline gap-2">
                            <p className="text-xl font-semibold text-white">{trendValue(item)}</p>
                            <p
                              className={`text-xs font-semibold ${
                                item.tone === "positive"
                                  ? "text-emerald-300"
                                  : item.tone === "negative"
                                    ? "text-rose-300"
                                    : "text-zinc-500"
                              }`}
                            >
                              {trendChangeLabel(item)}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
                      <div className="rounded-md border border-[#292a2f] bg-[#111215] p-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">
                              Daily Google visits and average position
                            </p>
                            <p className="mt-1 text-[11px] text-zinc-500">
                              Orange shows visits. Blue shows position; a smaller position number is better.
                            </p>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-zinc-400">
                            <span className="inline-flex items-center gap-1.5">
                              <span className="h-2 w-2 rounded-full bg-[#ff6b18]" /> Visits
                            </span>
                            <span className="inline-flex items-center gap-1.5">
                              <span className="h-2 w-2 rounded-full bg-sky-400" /> Position
                            </span>
                          </div>
                        </div>
                        <div className="mt-3 h-64 w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                              data={portfolio.trends.points}
                              margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
                            >
                              <XAxis
                                dataKey="date"
                                tickFormatter={(value) => shortDate(String(value))}
                                minTickGap={28}
                                tick={{ fill: "#71717a", fontSize: 10 }}
                                axisLine={{ stroke: "#292a2f" }}
                                tickLine={false}
                              />
                              <YAxis
                                yAxisId="visits"
                                tick={{ fill: "#71717a", fontSize: 10 }}
                                axisLine={false}
                                tickLine={false}
                                allowDecimals={false}
                              />
                              <YAxis
                                yAxisId="position"
                                orientation="right"
                                reversed
                                tick={{ fill: "#71717a", fontSize: 10 }}
                                axisLine={false}
                                tickLine={false}
                              />
                              <Tooltip
                                contentStyle={{
                                  background: "#111215",
                                  border: "1px solid #303137",
                                  borderRadius: "6px",
                                  color: "#fff",
                                  fontSize: "12px",
                                }}
                                labelFormatter={(value) => shortDate(String(value))}
                              />
                              <Line
                                yAxisId="visits"
                                type="monotone"
                                dataKey="clicks"
                                name="Google visits"
                                stroke="#ff6b18"
                                strokeWidth={2}
                                dot={false}
                                connectNulls={false}
                              />
                              <Line
                                yAxisId="position"
                                type="monotone"
                                dataKey="avg_position"
                                name="Average position"
                                stroke="#38bdf8"
                                strokeWidth={2}
                                dot={false}
                                connectNulls={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <p className="mt-2 text-[11px] leading-4 text-zinc-600">
                          The chart shows saved daily totals. The change cards only compare locations with enough information in both periods.
                        </p>
                      </div>

                      <div className="rounded-md border border-[#292a2f] bg-[#111215] p-3">
                        <p className="text-sm font-semibold text-white">Meaningful location changes</p>
                        <p className="mt-1 text-[11px] leading-4 text-zinc-500">
                          Only larger changes with enough history appear here. At most one change is shown for each location.
                        </p>
                        {portfolio.trends.alerts.length > 0 ? (
                          <div className="mt-3 space-y-2">
                            {portfolio.trends.alerts.map((alert) => (
                              <article
                                key={`${alert.location_id}-${alert.code}`}
                                className={`rounded-md border p-3 ${
                                  alert.tone === "positive"
                                    ? "border-emerald-500/20 bg-emerald-500/10"
                                    : "border-rose-500/20 bg-rose-500/10"
                                }`}
                              >
                                <p
                                  className={`text-xs font-semibold ${
                                    alert.tone === "positive"
                                      ? "text-emerald-100"
                                      : "text-rose-100"
                                  }`}
                                >
                                  {alert.tone === "positive" ? "↑" : "↓"} {alert.title}
                                </p>
                                <p className="mt-1 text-[11px] leading-4 text-zinc-400">
                                  {alert.detail}
                                </p>
                                <p className="mt-1 text-[11px] font-medium text-zinc-300">
                                  {alert.evidence.label}: {String(alert.evidence.value)}
                                </p>
                                <button
                                  type="button"
                                  className={`${secondaryButtonClass} mt-2`}
                                  onClick={() =>
                                    openPortfolioPath(alert.campaign_id, alert.action.href)
                                  }
                                >
                                  {alert.action.label}
                                </button>
                              </article>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-3 rounded-md border border-[#292a2f] bg-[#17181b] p-3 text-xs leading-5 text-zinc-500">
                            No location crossed a meaningful change threshold in this comparison.
                          </p>
                        )}
                      </div>
                    </div>
                  </section>
                ) : (
                  <section className="mt-4 rounded-md border border-[#2b2c31] bg-[#151619] p-4">
                    <p className="text-sm font-semibold text-white">Building location history</p>
                    <p className="mt-1 text-xs leading-5 text-zinc-400">
                      {portfolio.trends.coverage_note}
                    </p>
                  </section>
                )}

                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <section className="rounded-md border border-[#2b2c31] bg-[#151619] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      Shared work
                    </p>
                    <h3 className="mt-1.5 text-base font-semibold text-white">
                      Problems affecting more than one location
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-zinc-400">
                      Start here when the same problem appears across several locations. Each location keeps its own proof and next step.
                    </p>

                    {portfolio.shared_issues.length > 0 ? (
                      <div className="mt-4 space-y-2">
                        {portfolio.shared_issues.slice(0, 4).map((issue) => (
                          <details
                            key={issue.code}
                            className="rounded-md border border-[#2d2e33] bg-[#111215] p-3"
                          >
                            <summary className="cursor-pointer list-none">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-semibold text-white">{issue.title}</p>
                                  <p className="mt-1 text-xs leading-5 text-zinc-500">
                                    {issue.location_count} locations · open to see each one
                                  </p>
                                </div>
                                <span
                                  className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${attentionClasses(issue.severity)}`}
                                >
                                  {issue.attention_label}
                                </span>
                              </div>
                            </summary>
                            <p className="mt-3 border-t border-[#292a2f] pt-3 text-xs leading-5 text-zinc-400">
                              {issue.summary}
                            </p>
                            <div className="mt-3 space-y-2">
                              {issue.locations.map((location) => (
                                <div
                                  key={location.location_id}
                                  className="flex flex-col gap-3 rounded-md border border-[#292a2f] bg-[#17181b] p-3 sm:flex-row sm:items-center sm:justify-between"
                                >
                                  <div>
                                    <p className="text-xs font-semibold text-white">
                                      {location.location_name}
                                    </p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-500">
                                      {location.detail}
                                    </p>
                                    {location.evidence ? (
                                      <p className="mt-1 text-[11px] text-zinc-400">
                                        {location.evidence.label}: {String(location.evidence.value)}
                                      </p>
                                    ) : null}
                                  </div>
                                  <button
                                    type="button"
                                    className={secondaryButtonClass}
                                    onClick={() =>
                                      openPortfolioPath(
                                        location.campaign_id,
                                        location.action_href,
                                      )
                                    }
                                  >
                                    {location.action_label}
                                  </button>
                                </div>
                              ))}
                            </div>
                          </details>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs leading-5 text-emerald-100">
                        No saved problem currently affects more than one active location.
                      </p>
                    )}
                  </section>

                  <section className="rounded-md border border-[#2b2c31] bg-[#151619] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                      What is working
                    </p>
                    <h3 className="mt-1.5 text-base font-semibold text-white">
                      Locations worth learning from
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-zinc-400">
                      These are measured examples to inspect. InsightOS does not claim that one tactic caused the result.
                    </p>

                    {portfolio.repeatable_wins.length > 0 ? (
                      <div className="mt-4 space-y-3">
                        {portfolio.repeatable_wins.map((win) => (
                          <article
                            key={win.code}
                            className="rounded-md border border-[#2d2e33] bg-[#111215] p-3"
                          >
                            <p className="text-sm font-semibold text-white">{win.title}</p>
                            <p className="mt-1 text-xs leading-5 text-zinc-400">{win.summary}</p>
                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                              <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3">
                                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-200">
                                  Example to inspect
                                </p>
                                <p className="mt-1 text-xs font-semibold text-white">
                                  {win.source.location_name}
                                </p>
                                <p className="mt-1 text-[11px] text-zinc-400">
                                  {win.source.metric.label}: {String(win.source.metric.value)}
                                </p>
                              </div>
                              <div className="rounded-md border border-[#2b2c31] bg-[#17181b] p-3">
                                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                  Locations to compare
                                </p>
                                <p className="mt-1 text-xs leading-5 text-zinc-300">
                                  {win.targets.map((target) => target.location_name).join(", ")}
                                </p>
                              </div>
                            </div>
                            <div className="mt-3 flex flex-col gap-2 border-t border-[#292a2f] pt-3 sm:flex-row sm:items-center sm:justify-between">
                              <p className="max-w-xl text-[11px] leading-4 text-zinc-600">
                                {win.guardrail}
                              </p>
                              <button
                                type="button"
                                className={secondaryButtonClass}
                                onClick={() =>
                                  openPortfolioPath(win.action.campaign_id, win.action.href)
                                }
                              >
                                {win.action.label}
                              </button>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-4 rounded-md border border-[#2d2e33] bg-[#111215] p-3 text-xs leading-5 text-zinc-500">
                        More saved performance history is needed before one location can be used as a fair comparison.
                      </p>
                    )}
                  </section>
                </div>

                <details className="mt-4 rounded-md border border-[#2b2c31] bg-[#151619] p-4">
                  <summary className="cursor-pointer list-none text-sm font-semibold text-white">
                    Compare all {portfolio.summary.active_locations} active locations
                  </summary>
                  <div className="mt-4 flex flex-col gap-3 border-b border-[#292a2f] pb-4 sm:flex-row sm:items-end sm:justify-between">
                    <p className="max-w-2xl text-xs leading-5 text-zinc-500">
                      Sort the same saved facts without changing any location or running a paid check.
                    </p>
                    <label className={labelClass}>
                      Sort locations by
                      <select
                        value={portfolioSort}
                        onChange={(event) => setPortfolioSort(event.target.value)}
                        className={`${inputClass} min-w-52`}
                      >
                        <option value="attention">Needs attention first</option>
                        <option value="name">Location name</option>
                        <option value="position">Best Google position</option>
                        <option value="rating">Best recent rating</option>
                        <option value="issues">Most website problems</option>
                      </select>
                    </label>
                  </div>
                  <div className="divide-y divide-[#292a2f]">
                    {sortedPortfolioLocations.map((item) => (
                      <div
                        key={item.location_id}
                        className="grid gap-3 py-4 md:grid-cols-[minmax(180px,1.4fr)_repeat(3,minmax(110px,0.7fr))_auto] md:items-center"
                      >
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-white">{item.location_name}</p>
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${attentionClasses(item.attention_state)}`}
                            >
                              {item.attention_label}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-zinc-500">
                            {item.reasons[0]?.title || "No current warning"}
                          </p>
                        </div>
                        <div className="text-xs">
                          <p className="text-zinc-600">Google position</p>
                          <p className="mt-1 font-semibold text-zinc-200">
                            {positionLabel(item.performance.avg_position)}
                          </p>
                        </div>
                        <div className="text-xs">
                          <p className="text-zinc-600">Recent reviews</p>
                          <p className="mt-1 font-semibold text-zinc-200">
                            {item.performance.reviews_last_30d} · {ratingLabel(item.performance.avg_rating_last_30d)}
                          </p>
                        </div>
                        <div className="text-xs">
                          <p className="text-zinc-600">Work waiting</p>
                          <p className="mt-1 font-semibold text-zinc-200">
                            {item.performance.technical_issue_count} website · {item.open_actions} actions
                          </p>
                        </div>
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          onClick={() => openPortfolioAction(item)}
                        >
                          Open location
                        </button>
                      </div>
                    ))}
                  </div>
                </details>
              </section>
            ) : null}
          </>
        ) : null}

        {!loading ? (
          <details
            id="location-setup"
            open={totals.business_locations === 0 ? true : undefined}
            className="rounded-md border border-[#2c2d32] bg-[#121316] p-4 shadow-[0_0_30px_rgba(0,0,0,0.35)]"
          >
            <summary className="flex cursor-pointer list-none flex-col gap-2 border-b border-[#26272c] pb-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Guided setup
                </p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                  Add a business location in three steps
                </h2>
              </div>
              <p className="max-w-xl text-sm leading-5 text-zinc-400">
                Choose the business group, add the physical location, then connect its website.
                InsightOS handles the technical setup behind the scenes.
              </p>
            </summary>

            <div className="mt-4 grid gap-4 xl:grid-cols-3">
              <form
                onSubmit={createSubaccount}
                className="rounded-md border border-[#26272c] bg-[#17181b] p-4"
              >
                <p className="text-xs font-semibold text-accent-400">Step 1</p>
                <h3 className="mt-1 text-base font-semibold text-white">Create account group</h3>
                <p className="mt-1 text-xs leading-5 text-zinc-400">
                  Use a client, brand, region, or division name.
                </p>
                <label className={`${labelClass} mt-4`}>
                  Group name
                  <input
                    value={subaccountName}
                    onChange={(event) => setSubaccountName(event.target.value)}
                    placeholder="North Region"
                    className={inputClass}
                  />
                </label>
                <button
                  type="submit"
                  disabled={!subaccountName.trim() || busyAction === "subaccount"}
                  className={`${primaryButtonClass} mt-4 w-full`}
                >
                  {busyAction === "subaccount" ? "Creating…" : "Create group"}
                </button>
              </form>

              <form
                onSubmit={createLocation}
                className="rounded-md border border-[#3a2a20] bg-[#171518] p-4"
              >
                <p className="text-xs font-semibold text-accent-400">Step 2</p>
                <h3 className="mt-1 text-base font-semibold text-white">Add business location</h3>
                <p className="mt-1 text-xs leading-5 text-zinc-400">
                  This is the physical branch users will see throughout the product.
                </p>
                <label className={`${labelClass} mt-4`}>
                  Account group
                  <select
                    value={locationSubaccountId}
                    onChange={(event) => setLocationSubaccountId(event.target.value)}
                    className={inputClass}
                  >
                    <option value="">Choose a group</option>
                    {activeSubaccounts.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={`${labelClass} mt-3`}>
                  Location name
                  <input
                    value={locationName}
                    onChange={(event) => setLocationName(event.target.value)}
                    placeholder="Dallas - Main Street"
                    className={inputClass}
                  />
                </label>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className={labelClass}>
                    City
                    <input
                      value={locationCity}
                      onChange={(event) => setLocationCity(event.target.value)}
                      placeholder="Dallas"
                      className={inputClass}
                    />
                  </label>
                  <label className={labelClass}>
                    State / region
                    <input
                      value={locationRegion}
                      onChange={(event) => setLocationRegion(event.target.value)}
                      placeholder="Texas"
                      className={inputClass}
                    />
                  </label>
                  <label className={labelClass}>
                    Country code
                    <input
                      value={locationCountryCode}
                      onChange={(event) => setLocationCountryCode(event.target.value)}
                      placeholder="US"
                      maxLength={2}
                      className={inputClass}
                    />
                  </label>
                  <label className={labelClass}>
                    Domain
                    <input
                      value={locationDomain}
                      onChange={(event) => setLocationDomain(event.target.value)}
                      placeholder="dallas.example.com"
                      className={inputClass}
                    />
                  </label>
                </div>
                <button
                  type="submit"
                  disabled={
                    !locationName.trim() ||
                    !locationSubaccountId ||
                    busyAction === "location"
                  }
                  className={`${primaryButtonClass} mt-4 w-full`}
                >
                  {busyAction === "location" ? "Creating…" : "Add location"}
                </button>
              </form>

              <form
                onSubmit={createCampaign}
                className="rounded-md border border-[#26272c] bg-[#17181b] p-4"
              >
                <p className="text-xs font-semibold text-accent-400">Step 3</p>
                <h3 className="mt-1 text-base font-semibold text-white">Start location campaign</h3>
                <p className="mt-1 text-xs leading-5 text-zinc-400">
                  Assign SEO tracking and recommendations to the physical location.
                </p>
                <label className={`${labelClass} mt-4`}>
                  Business location
                  <select
                    value={campaignLocationId}
                    onChange={(event) => setCampaignLocationId(event.target.value)}
                    className={inputClass}
                  >
                    <option value="">Choose a location</option>
                    {activeBusinessLocations.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.subaccount_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={`${labelClass} mt-3`}>
                  Campaign name
                  <input
                    value={campaignName}
                    onChange={(event) => setCampaignName(event.target.value)}
                    placeholder="Dallas Local SEO"
                    className={inputClass}
                  />
                </label>
                <label className={`${labelClass} mt-3`}>
                  Domain
                  <input
                    value={campaignDomain}
                    onChange={(event) => setCampaignDomain(event.target.value)}
                    placeholder="dallas.example.com"
                    className={inputClass}
                  />
                </label>
                <button
                  type="submit"
                  disabled={
                    !campaignName.trim() ||
                    !campaignDomain.trim() ||
                    !campaignLocationId ||
                    busyAction === "campaign"
                  }
                  className={`${primaryButtonClass} mt-4 w-full`}
                >
                  {busyAction === "campaign" ? "Creating…" : "Create campaign"}
                </button>
              </form>
            </div>
          </details>
        ) : null}

        {!loading && (hierarchy?.subaccounts.length || 0) === 0 ? (
          <EmptyState
            title="Start with an account group"
            summary="Create a client, brand, region, or division above. Then add physical business locations without exposing the internal execution structure."
            actionLabel="Go to setup"
            onAction={() =>
              document.getElementById("location-setup")?.scrollIntoView({ behavior: "smooth" })
            }
          />
        ) : null}

        {!loading && (hierarchy?.subaccounts.length || 0) > 0 ? (
          <section className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Portfolio structure
              </p>
              <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
                Account groups and locations
              </h2>
            </div>

            {hierarchy?.subaccounts.map((subaccount) => (
              <article
                key={subaccount.id}
                className="rounded-md border border-[#26272c] bg-[#121316] p-4"
              >
                <div className="flex flex-col gap-3 border-b border-[#26272c] pb-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-white">{subaccount.name}</h3>
                      <span
                        className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${statusClasses(subaccount.status)}`}
                      >
                        {titleCase(subaccount.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-zinc-400">
                      {subaccount.counts.business_locations} locations ·{" "}
                      {subaccount.counts.campaigns} campaigns
                    </p>
                  </div>
                  <button
                    className={secondaryButtonClass}
                    onClick={() => {
                      setLocationSubaccountId(subaccount.id);
                      document
                        .getElementById("location-setup")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    Add location here
                  </button>
                </div>

                {subaccount.business_locations.length === 0 ? (
                  <p className="py-5 text-sm text-zinc-500">
                    No physical locations have been added to this group.
                  </p>
                ) : (
                  <div className="mt-4 grid gap-3 xl:grid-cols-2">
                    {subaccount.business_locations.map((location) => (
                      <section
                        key={location.id}
                        className="rounded-md border border-[#2b2c31] bg-[#17181b] p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <h4 className="font-semibold text-white">{location.name}</h4>
                              <span
                                className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${statusClasses(location.status)}`}
                              >
                                {titleCase(location.status)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-zinc-500">
                              {[location.primary_city, location.domain]
                                .filter(Boolean)
                                .join(" · ") || "Location details not added"}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              className={secondaryButtonClass}
                              onClick={() => beginEditLocation(location)}
                            >
                              Map details
                            </button>
                            {location.status === "active" ? (
                              <button
                                className={secondaryButtonClass}
                                disabled={busyAction === `archive-${location.id}`}
                                onClick={() => void archiveLocation(location)}
                              >
                                Archive
                              </button>
                            ) : null}
                          </div>
                        </div>

                        {editingLocationId === location.id ? (
                          <div className="mt-4 rounded-md border border-accent-500/20 bg-[#111214] p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-white">Map search area</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-500">
                                  City, state/region, and country match this business to the right local search area. Coordinates may be left blank and resolved from Local Visibility.
                                </p>
                              </div>
                              <button
                                className={secondaryButtonClass}
                                onClick={() => setEditingLocationId("")}
                              >
                                Close
                              </button>
                            </div>
                            <div className="mt-3 grid gap-3 sm:grid-cols-3">
                              <label className={labelClass}>
                                City
                                <input
                                  value={geoDraft.city}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({ ...current, city: event.target.value }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={labelClass}>
                                State / region
                                <input
                                  value={geoDraft.region}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({ ...current, region: event.target.value }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={labelClass}>
                                Country
                                <input
                                  value={geoDraft.country_code}
                                  maxLength={2}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({
                                      ...current,
                                      country_code: event.target.value,
                                    }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={`${labelClass} sm:col-span-2`}>
                                Street address (optional)
                                <input
                                  value={geoDraft.address_line1}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({
                                      ...current,
                                      address_line1: event.target.value,
                                    }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={labelClass}>
                                Postal code
                                <input
                                  value={geoDraft.postal_code}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({
                                      ...current,
                                      postal_code: event.target.value,
                                    }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={labelClass}>
                                Latitude (optional)
                                <input
                                  type="number"
                                  step="any"
                                  value={geoDraft.latitude}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({
                                      ...current,
                                      latitude: event.target.value,
                                    }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                              <label className={labelClass}>
                                Longitude (optional)
                                <input
                                  type="number"
                                  step="any"
                                  value={geoDraft.longitude}
                                  onChange={(event) =>
                                    setGeoDraft((current) => ({
                                      ...current,
                                      longitude: event.target.value,
                                    }))
                                  }
                                  className={inputClass}
                                />
                              </label>
                            </div>
                            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                              <p className="text-xs text-zinc-500">
                                {location.provider_location_name
                                  ? `Search area: ${location.provider_location_name} (${location.provider_location_code})`
                                  : "The local search area has not been matched yet."}
                              </p>
                              <button
                                className={primaryButtonClass}
                                disabled={
                                  !geoDraft.city.trim() ||
                                  !geoDraft.region.trim() ||
                                  busyAction === `geo-${location.id}`
                                }
                                onClick={() => void saveLocationDetails(location)}
                              >
                                {busyAction === `geo-${location.id}` ? "Saving…" : "Save map details"}
                              </button>
                            </div>
                          </div>
                        ) : null}

                        {location.performance?.data_available ? (
                          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                            <div className="rounded-md border border-[#26272c] bg-[#111214] p-2.5">
                              <p className="text-[9px] uppercase tracking-[0.13em] text-zinc-600">
                                Avg position
                              </p>
                              <p className="mt-1 text-base font-semibold text-white">
                                {location.performance.avg_position ?? "—"}
                              </p>
                            </div>
                            <div className="rounded-md border border-[#26272c] bg-[#111214] p-2.5">
                              <p className="text-[9px] uppercase tracking-[0.13em] text-zinc-600">
                                Sessions
                              </p>
                              <p className="mt-1 text-base font-semibold text-white">
                                {location.performance.sessions}
                              </p>
                            </div>
                            <div className="rounded-md border border-[#26272c] bg-[#111214] p-2.5">
                              <p className="text-[9px] uppercase tracking-[0.13em] text-zinc-600">
                                Reviews
                              </p>
                              <p className="mt-1 text-base font-semibold text-white">
                                {location.performance.reviews_last_30d}
                              </p>
                            </div>
                            <div className="rounded-md border border-[#26272c] bg-[#111214] p-2.5">
                              <p className="text-[9px] uppercase tracking-[0.13em] text-zinc-600">
                                Tech issues
                              </p>
                              <p
                                className={`mt-1 text-base font-semibold ${
                                  location.performance.technical_issue_count > 0
                                    ? "text-amber-200"
                                    : "text-emerald-200"
                                }`}
                              >
                                {location.performance.technical_issue_count}
                              </p>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-4 rounded-md border border-dashed border-[#303137] bg-[#111214] px-3 py-2.5 text-xs text-zinc-500">
                            Performance comparison will appear after the first campaign data collection.
                          </div>
                        )}

                        <div className="mt-2 grid grid-cols-2 gap-2">
                          <div className="rounded-md border border-[#26272c] bg-[#111214] p-3">
                            <p className="text-[10px] uppercase tracking-[0.15em] text-zinc-600">
                              Campaigns
                            </p>
                            <p className="mt-1 text-lg font-semibold text-white">
                              {location.campaigns.length}
                            </p>
                          </div>
                          <div className="rounded-md border border-[#26272c] bg-[#111214] p-3">
                            <p className="text-[10px] uppercase tracking-[0.15em] text-zinc-600">
                              Execution
                            </p>
                            <p className="mt-1 text-sm font-semibold text-emerald-200">
                              {location.execution_locations.length > 0 ? "Connected" : "Needs repair"}
                            </p>
                          </div>
                        </div>

                        {location.campaigns.length > 0 ? (
                          <div className="mt-3 space-y-2">
                            {location.campaigns.map((campaign) => (
                              <div
                                key={campaign.id}
                                className="flex items-center justify-between gap-3 rounded-md border border-[#26272c] bg-[#111214] px-3 py-2"
                              >
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-medium text-zinc-100">
                                    {campaign.name}
                                  </p>
                                  <p className="truncate text-xs text-zinc-500">
                                    {campaign.domain}
                                  </p>
                                </div>
                                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                  {titleCase(campaign.setup_state)}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <button
                            className={`${secondaryButtonClass} mt-3 w-full`}
                            onClick={() => {
                              setCampaignLocationId(location.id);
                              setCampaignDomain(location.domain || "");
                              document
                                .getElementById("location-setup")
                                ?.scrollIntoView({ behavior: "smooth" });
                            }}
                          >
                            Create first campaign
                          </button>
                        )}
                      </section>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </section>
        ) : null}

        {!loading && totals.campaigns > 0 ? (
          <div className="flex justify-end">
            <button className={secondaryButtonClass} onClick={() => router.push("/dashboard")}>
              Open campaign dashboard
            </button>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
