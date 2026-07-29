"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
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

export default function LocationsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { reloadLocations } = useLocationContext();
  const [me, setMe] = useState<Me | null>(null);
  const [hierarchy, setHierarchy] = useState<Hierarchy | null>(null);
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
    const response = await platformApi(`/organizations/${orgId}/hierarchy`, {
      method: "GET",
    });
    const nextHierarchy = (response?.hierarchy || null) as Hierarchy | null;
    setHierarchy(nextHierarchy);
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
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Account groups"
              value={String(totals.subaccounts)}
              summary="Brands, clients, or divisions connected to the main account."
            />
            <KpiCard
              label="Business locations"
              value={String(totals.business_locations)}
              summary={`${totals.active_business_locations} currently active and available for campaign work.`}
              tone={totals.business_locations > 0 ? "highlight" : undefined}
            />
            <KpiCard
              label="Tracking workspaces"
              value={String(totals.campaigns)}
              summary="Locations with their own website and search tracking."
            />
            <KpiCard
              label="Needs assignment"
              value={String(totals.unassigned_business_locations)}
              summary={
                totals.unassigned_business_locations > 0
                  ? "Legacy locations still need an account group."
                  : "Every business location belongs to an account group."
              }
            />
          </div>
        ) : null}

        {!loading ? (
          <section
            id="location-setup"
            className="rounded-md border border-[#2c2d32] bg-[#121316] p-4 shadow-[0_0_30px_rgba(0,0,0,0.35)]"
          >
            <div className="flex flex-col gap-2 border-b border-[#26272c] pb-4 md:flex-row md:items-end md:justify-between">
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
            </div>

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
          </section>
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
                                <p className="text-sm font-semibold text-white">Map and provider location</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-500">
                                  City, state/region, and country drive automatic DataForSEO matching. Coordinates may be left blank and resolved from Local Visibility.
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
                                  ? `DataForSEO: ${location.provider_location_name} (${location.provider_location_code})`
                                  : "DataForSEO location has not been resolved yet."}
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
