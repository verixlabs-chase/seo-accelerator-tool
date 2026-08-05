"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import {
  AppShell,
  EmptyState,
  LoadingCard,
  OwnerDecisionPanel,
  ProductPageIntro,
  TruthNotice,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import {
  getConnectionPortfolioSummary,
  getConnectionStatusView,
} from "../truth/dataConnectionsTruth.mjs";

type Me = {
  organization_id?: string;
  org_role?: string;
};

type Campaign = {
  id: string;
  name: string;
  domain: string;
  setup_state: string;
  business_location_id?: string | null;
};

type SearchConsoleResource = {
  id: string;
  name: string;
  permission_level: string;
  resource_scope: string;
};

type BusinessProfileResource = {
  id: string;
  name: string;
  account_name: string;
  account_role: string;
  permission_level: string;
  verified: boolean;
  address: string;
  website: string;
  phone: string;
  primary_category: string;
};

type DataConnection = {
  id: string;
  provider_name: string;
  business_location_id: string;
  business_location_name?: string | null;
  campaign_id: string;
  campaign_name?: string | null;
  campaign_domain?: string | null;
  external_resource_id: string;
  external_resource_name?: string | null;
  resource_scope: string;
  status: string;
  last_success_at?: string | null;
  next_sync_at?: string | null;
  last_error_message?: string | null;
  source_truth: string;
};

type ConnectionsPayload = {
  google_oauth: {
    connected: boolean;
    approved_access?: {
      search_console: boolean;
      business_profile: boolean;
    };
    updated_at?: string | null;
  };
  connections: DataConnection[];
};

type UsageAllowance = {
  plan: {
    code: string;
    name: string;
  };
  period: {
    start: string;
    end: string;
    resets_at: string;
  };
  credits: {
    name: string;
    monthly: number;
    used: number;
    reserved: number;
    remaining: number;
    percent_committed: number;
    warning_level?: number | null;
    blocked: boolean;
  };
  connected_account_actions: number;
  recovery_actions: string[];
  recent_activity: Array<{
    id: string;
    label: string;
    result: string;
    credits: number;
    state: "completed" | "reserved" | "returned" | "connected_account";
    created_at: string;
  }>;
  action_prices: Array<{
    code: string;
    label: string;
    result: string;
    credits: number;
    price_type: "up_to" | "per_item" | "fixed_ceiling";
  }>;
  important_note: string;
};

const primaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-accent-500/40 bg-accent-500/15 px-4 py-2 text-sm font-semibold text-white transition hover:border-accent-500/70 hover:bg-accent-500/25 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-[#303137] bg-[#17181b] px-3.5 py-2 text-sm font-medium text-zinc-100 transition hover:bg-[#1d1e22] disabled:cursor-not-allowed disabled:opacity-50";
const selectClass =
  "w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2.5 text-sm text-white outline-none transition focus:border-accent-500/60 disabled:opacity-50";

function formatTimestamp(value?: string | null) {
  if (!value) return "Not synced yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function formatResetDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "next month";
  return new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric" }).format(parsed);
}

function toneClasses(tone: string) {
  if (tone === "success") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (tone === "danger") return "border-rose-500/25 bg-rose-500/10 text-rose-100";
  if (tone === "warning") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-sky-500/25 bg-sky-500/10 text-sky-100";
}

export default function SettingsPage() {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [payload, setPayload] = useState<ConnectionsPayload | null>(null);
  const [usageAllowance, setUsageAllowance] = useState<UsageAllowance | null>(null);
  const [resources, setResources] = useState<SearchConsoleResource[]>([]);
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [profileResources, setProfileResources] = useState<BusinessProfileResource[]>([]);
  const [profileDrafts, setProfileDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadingResources, setLoadingResources] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const organizationId = me?.organization_id || "";
  const manageableCampaigns = useMemo(
    () => campaigns.filter((campaign) => Boolean(campaign.business_location_id)),
    [campaigns],
  );
  const connections = payload?.connections || [];
  const searchConsoleConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_search_console"),
    [connections],
  );
  const profileConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_business_profile"),
    [connections],
  );
  const connectionByCampaign = useMemo(
    () => new Map(searchConsoleConnections.map((connection) => [connection.campaign_id, connection])),
    [searchConsoleConnections],
  );
  const profileConnectionByCampaign = useMemo(
    () => new Map(profileConnections.map((connection) => [connection.campaign_id, connection])),
    [profileConnections],
  );
  const portfolioSummary = useMemo(
    () => getConnectionPortfolioSummary(searchConsoleConnections, manageableCampaigns.length),
    [searchConsoleConnections, manageableCampaigns.length],
  );

  const loadConnections = useCallback(async (orgId: string) => {
    const next = (await platformApi(
      `/organizations/${orgId}/data-connections`,
      { method: "GET" },
    )) as ConnectionsPayload;
    setPayload(next);
    setResourceDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_search_console",
      )) {
        if (!seeded[connection.campaign_id]) {
          seeded[connection.campaign_id] = connection.external_resource_id;
        }
      }
      return seeded;
    });
    setProfileDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_business_profile",
      )) {
        if (!seeded[connection.campaign_id]) {
          seeded[connection.campaign_id] = connection.external_resource_id;
        }
      }
      return seeded;
    });
    return next;
  }, []);

  const loadProfileResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-business-profile/resources`,
        { method: "GET" },
      )) as { resources?: BusinessProfileResource[] };
      setProfileResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no business listings were returned. Confirm that this Google account manages the listing.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Google business listings.");
    } finally {
      setLoadingResources(false);
    }
  }, []);

  const loadResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-search-console/resources`,
        { method: "GET" },
      )) as { resources?: SearchConsoleResource[] };
      setResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no Search Console websites were returned. Confirm that this Google account has access to the website.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Search Console websites.");
    } finally {
      setLoadingResources(false);
    }
  }, []);

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        const currentUser = (await platformApi("/auth/me", { method: "GET" })) as Me;
        if (!currentUser.organization_id) {
          throw new Error("An organization is required to manage data connections.");
        }
        setMe(currentUser);
        const [campaignResponse, connectionResponse, allowanceResponse] = await Promise.all([
          platformApi("/campaigns", { method: "GET" }) as Promise<{ items?: Campaign[] }>,
          loadConnections(currentUser.organization_id),
          platformApi("/usage/credits", { method: "GET" }) as Promise<UsageAllowance>,
        ]);
        setCampaigns(campaignResponse.items || []);
        setUsageAllowance(allowanceResponse);
        const returnParams = new URLSearchParams(window.location.search);
        const googleReturned = returnParams.get("google");
        const returnSource = returnParams.get("source");
        if (googleReturned === "connected") {
          setNotice(
            returnSource === "business-profile"
              ? "Google business listings are connected. Match each location to its listing next."
              : "Google Search Console is connected. Match each location to its website next.",
          );
          window.history.replaceState({}, "", "/settings");
          if (returnSource === "business-profile") {
            await loadProfileResources(currentUser.organization_id);
          } else {
            await loadResources(currentUser.organization_id);
          }
        } else if (connectionResponse.google_oauth.connected) {
          setNotice("");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load data connections.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadConnections, loadProfileResources, loadResources]);

  async function connectGoogle(scopeTarget: "gsc" | "gbp" = "gsc") {
    if (!organizationId) return;
    setBusyAction(`oauth-${scopeTarget}`);
    setError("");
    setNotice("");
    try {
      const returnPath = scopeTarget === "gbp" ? "/settings?source=business-profile" : "/settings";
      const response = (await platformApi(
        `/organizations/${organizationId}/providers/google/oauth/start?scope_target=${scopeTarget}&return_path=${encodeURIComponent(returnPath)}`,
        { method: "POST" },
      )) as { authorization_url?: string };
      if (!response.authorization_url) {
        throw new Error("Google did not return a connection link.");
      }
      window.location.assign(response.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start the Google connection.");
      setBusyAction("");
    }
  }

  async function saveProfileMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = profileDrafts[campaign.id] || "";
    const resource = profileResources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose the Google business listing for this location.");
      return;
    }
    setBusyAction(`profile-mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-business-profile/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ external_resource_id: resource.id }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The Google business listing match was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      setNotice(
        syncResponse.job?.status === "completed"
          ? `${campaign.name} is matched and its Google listing check is ready.`
          : `${campaign.name} is matched. Its first Google listing check is queued.`,
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this listing match.");
    } finally {
      setBusyAction("");
    }
  }

  async function saveMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = resourceDrafts[campaign.id] || "";
    const resource = resources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose a Search Console website for this location.");
      return;
    }
    setBusyAction(`mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-search-console/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            external_resource_id: resource.id,
            external_resource_name: resource.name,
          }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The website mapping was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      if (syncResponse.job?.status === "completed") {
        setNotice(`${campaign.name} is connected and its first Search Console history is ready.`);
      } else {
        setNotice(`${campaign.name} is connected. Its first automatic update has been queued.`);
      }
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this website connection.");
    } finally {
      setBusyAction("");
    }
  }

  async function syncConnection(connection: DataConnection) {
    if (!organizationId) return;
    if (connection.status === "reconnect_required") {
      await connectGoogle(
        connection.provider_name === "google_business_profile" ? "gbp" : "gsc",
      );
      return;
    }
    setBusyAction(`sync-${connection.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connection.id}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string; idempotent_replay?: boolean } };
      await loadConnections(organizationId);
      setNotice(
        response.job?.idempotent_replay
          ? `${connection.business_location_name || connection.campaign_name} is already up to date.`
          : response.job?.status === "completed"
            ? `${connection.business_location_name || connection.campaign_name} was updated successfully.`
            : "The update is queued and will continue automatically.",
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to update this connection.");
    } finally {
      setBusyAction("");
    }
  }

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Google",
        value: payload?.google_oauth.connected ? "Connected" : "Not connected",
        tone: payload?.google_oauth.connected ? "success" : "warning",
      },
      {
        label: "Locations mapped",
        value: `${searchConsoleConnections.length}/${manageableCampaigns.length}`,
        tone: searchConsoleConnections.length === manageableCampaigns.length && searchConsoleConnections.length > 0
          ? "success"
          : "warning",
      },
      {
        label: "Automatic data",
        value: portfolioSummary.label,
        tone: portfolioSummary.tone as TrustSignal["tone"],
      },
      {
        label: "Insight Credits",
        value: usageAllowance
          ? `${usageAllowance.credits.remaining.toLocaleString()} available`
          : "Checking",
        tone: usageAllowance?.credits.blocked
          ? "danger"
          : usageAllowance?.credits.warning_level
            ? "warning"
            : "info",
      },
    ],
    [manageableCampaigns.length, payload, portfolioSummary, searchConsoleConnections.length, usageAllowance],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel="Data connections"
      dateRangeLabel="Automatic updates"
      topBarActions={
        <button
          className={primaryButtonClass}
          disabled={busyAction.startsWith("oauth-")}
          onClick={() => void connectGoogle()}
        >
          {payload?.google_oauth.connected ? "Reconnect Google" : "Connect Google"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Data connections"
          title="Keep your search data updated automatically"
          summary="Connect Google once, match each business location to its website, and let InsightOS collect the latest Search Console results on schedule."
        />

        <TruthNotice title="This phase does not connect sales systems." tone="info">
          Search Console is the first automatic source. Call tracking, CRM, job-management,
          booked-job, payment, and revenue connections are intentionally not included.
        </TruthNotice>

        {error ? (
          <div className="rounded-md border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {notice}
          </div>
        ) : null}

        {loading ? (
          <LoadingCard
            title="Loading data connections"
            summary="Checking Google access, location mappings, and the latest automatic updates."
          />
        ) : (
          <>
            <OwnerDecisionPanel
              eyebrow="Connection status"
              title={
                !payload?.google_oauth.connected
                  ? "Connect Google to start automatic updates"
                  : manageableCampaigns.length === 0
                    ? "Add a business location before matching a website"
                    : portfolioSummary.label
              }
              summary={
                !payload?.google_oauth.connected
                  ? "InsightOS cannot collect Search Console visits, appearances, and search positions until read-only Google access is approved."
                  : manageableCampaigns.length === 0
                    ? "Automatic data must belong to a real location so results never get mixed between businesses."
                    : portfolioSummary.summary
              }
              nextStep={
                !payload?.google_oauth.connected
                  ? "Connect Google, then choose the Search Console website that belongs to each location."
                  : manageableCampaigns.length === 0
                    ? "Add the first physical business location and its website."
                    : portfolioSummary.needsAttention > 0
                      ? "Open the location marked as needing attention and try its update again."
                      : portfolioSummary.unmapped > 0
                        ? "Match the next unmapped location to its Search Console website."
                        : "Connections are healthy. Leave them alone unless a location stops updating."
              }
              actionLabel={
                !payload?.google_oauth.connected
                  ? "Connect Google"
                  : manageableCampaigns.length === 0
                    ? "Add a location"
                    : portfolioSummary.needsAttention > 0 || portfolioSummary.unmapped > 0
                      ? "Review location connections"
                      : undefined
              }
              onAction={
                !payload?.google_oauth.connected
                  ? () => void connectGoogle()
                  : manageableCampaigns.length === 0
                    ? () => window.location.assign("/locations")
                    : portfolioSummary.needsAttention > 0 || portfolioSummary.unmapped > 0
                      ? () =>
                          document
                            .getElementById("website-mappings")
                            ?.scrollIntoView({ behavior: "smooth" })
                      : undefined
              }
              tone={
                portfolioSummary.needsAttention > 0
                  ? "urgent"
                  : portfolioSummary.unmapped > 0 || !payload?.google_oauth.connected
                    ? "warning"
                    : portfolioSummary.tone === "success"
                      ? "positive"
                      : "neutral"
              }
              progress={
                manageableCampaigns.length > 0
                  ? {
                      label: "Locations matched to a website",
                      value: searchConsoleConnections.length,
                      total: manageableCampaigns.length,
                      summary: "Each location keeps its own mapping and update history.",
                    }
                  : undefined
              }
            />

            {usageAllowance ? (
              <details className="rounded-md border border-[#292a2f] bg-[#141518] p-4">
                <summary className="cursor-pointer list-none">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Insight Credits available this month
                  </p>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <h2 className="text-base font-semibold text-white">
                      {usageAllowance.credits.remaining.toLocaleString()} credits available
                    </h2>
                    <span className="text-xs text-zinc-400">See usage</span>
                  </div>
                </summary>
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      {usageAllowance.plan.name} plan
                    </p>
                    <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">
                      {usageAllowance.credits.remaining.toLocaleString()} credits left this month
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
                      You have used {usageAllowance.credits.used.toLocaleString()} credits. {" "}
                      {usageAllowance.credits.reserved.toLocaleString()} are set aside for work that
                      is still running. Your balance resets {formatResetDate(usageAllowance.period.resets_at)}.
                    </p>
                  </div>
                  <div className="min-w-[220px]">
                    <div className="flex items-center justify-between text-xs text-zinc-400">
                      <span>{usageAllowance.credits.percent_committed.toFixed(1)}% used or reserved</span>
                      <span>{usageAllowance.credits.monthly.toLocaleString()} each month</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#24252a]">
                      <div
                        className={`h-full rounded-full ${
                          usageAllowance.credits.blocked
                            ? "bg-rose-400"
                            : usageAllowance.credits.warning_level
                              ? "bg-amber-400"
                              : "bg-emerald-400"
                        }`}
                        style={{
                          width: `${Math.min(100, usageAllowance.credits.percent_committed)}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
                {usageAllowance.recovery_actions.length > 0 ? (
                  <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {usageAllowance.recovery_actions[0]}
                  </div>
                ) : null}
                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  {usageAllowance.action_prices.map((action) => (
                    <div key={action.code} className="border-l-2 border-[#303137] pl-3">
                      <p className="text-sm font-semibold text-white">{action.label}</p>
                      <p className="mt-1 text-xs text-zinc-400">{action.result}</p>
                      <p className="mt-2 text-xs font-semibold text-accent-200">
                        {action.price_type === "up_to" ? "Up to " : ""}
                        {action.credits.toLocaleString()} {action.credits === 1 ? "credit" : "credits"}
                        {action.price_type === "per_item" ? " each" : ""}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs leading-5 text-zinc-500">
                  {usageAllowance.important_note} Failed work returns unused credits automatically.
                  Eligible checks made through your own connected account use 0 Insight Credits.
                </p>
              </details>
            ) : null}

            <section className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Google Search Console
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.connected
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.connected ? "Google connected" : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    Shows how often your website appears in Google Search, how many visits it
                    earns, and its average search position. Search Console normally reports with
                    a short delay, so the newest available day may be about two days old.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={!payload?.google_oauth.connected || loadingResources}
                    onClick={() => void loadResources(organizationId)}
                  >
                    {loadingResources ? "Loading websites..." : "Load available websites"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-gsc"}
                    onClick={() => void connectGoogle()}
                  >
                    {payload?.google_oauth.connected ? "Reconnect Google" : "Connect Google"}
                  </button>
                </div>
              </div>
            </section>

            {!payload?.google_oauth.connected ? (
              <EmptyState
                title="Connect Google to begin"
                summary="You will approve read-only Search Console access. InsightOS stores the connection securely and never receives your Google password."
                actionLabel="Connect Google Search Console"
                onAction={() => void connectGoogle()}
              />
            ) : manageableCampaigns.length === 0 ? (
              <EmptyState
                title="Add a business location first"
                summary="Every automatic data source must map to a real business location so results never blend between accounts."
                actionLabel="Manage locations"
                onAction={() => window.location.assign("/locations")}
              />
            ) : (
              <section id="website-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match websites to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Each location keeps its own mapping and sync history. A shared domain property
                    represents the whole website unless that location owns a separate URL-prefix property.
                  </p>
                </div>

                {manageableCampaigns.map((campaign) => {
                  const connection = connectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource = resourceDrafts[campaign.id] || connection?.external_resource_id || "";
                  return (
                    <article
                      key={campaign.id}
                      className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
                    >
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.8fr)_auto] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-semibold text-white">{campaign.name}</h3>
                            {statusView ? (
                              <span
                                className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClasses(statusView.tone)}`}
                              >
                                {statusView.label}
                              </span>
                            ) : (
                              <span className="rounded-full border border-zinc-500/25 bg-zinc-500/10 px-2.5 py-1 text-xs font-semibold text-zinc-300">
                                Website not matched
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-sm text-zinc-400">
                            {connection?.business_location_name || campaign.domain}
                          </p>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful update: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the Search Console property that belongs to this location's website."}
                          </p>
                          {connection?.last_error_message ? (
                            <p className="mt-2 text-xs leading-5 text-rose-200">
                              {connection.last_error_message}
                            </p>
                          ) : null}
                        </div>

                        <div>
                          <label
                            htmlFor={`resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Search Console website
                          </label>
                          <select
                            id={`resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={resources.length === 0 || Boolean(connection?.last_success_at)}
                            onChange={(event) =>
                              setResourceDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {resources.length === 0
                                ? "Load available websites first"
                                : "Choose a website"}
                            </option>
                            {resources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name} · {resource.permission_level.replaceAll("_", " ")}
                              </option>
                            ))}
                            {connection && !resources.some((resource) => resource.id === connection.external_resource_id) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                          {connection ? (
                            <p className="mt-1.5 text-xs text-zinc-500">
                              {connection.resource_scope === "domain_property"
                                ? "Whole-domain website property"
                                : "URL-prefix website property"}
                            </p>
                          ) : null}
                        </div>

                        <div className="flex lg:justify-end">
                          {connection ? (
                            <button
                              className={secondaryButtonClass}
                              disabled={
                                busyAction === `sync-${connection.id}` ||
                                connection.status === "syncing"
                              }
                              onClick={() => void syncConnection(connection)}
                            >
                              {busyAction === `sync-${connection.id}`
                                ? "Updating..."
                                : statusView?.action || "Check now"}
                            </button>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveMapping(campaign)}
                            >
                              {busyAction === `mapping-${campaign.id}`
                                ? "Connecting..."
                                : "Connect and start first sync"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            )}

            <section className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Google business listing
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.approved_access?.business_profile
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.approved_access?.business_profile
                        ? "Access approved"
                        : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    Match each location to the listing customers see on Google. InsightOS will
                    check its details, save changes, and show calls, website clicks, directions,
                    appearances, and customer search terms when Google makes them available.
                  </p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                    InsightOS will not edit the listing automatically. Any future change will
                    require review and approval first.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={
                      !payload?.google_oauth.approved_access?.business_profile || loadingResources
                    }
                    onClick={() => void loadProfileResources(organizationId)}
                  >
                    {loadingResources ? "Loading listings..." : "Load available listings"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-gbp"}
                    onClick={() => void connectGoogle("gbp")}
                  >
                    {payload?.google_oauth.approved_access?.business_profile
                      ? "Reconnect listing access"
                      : "Connect business listings"}
                  </button>
                </div>
              </div>
            </section>

            {!payload?.google_oauth.approved_access?.business_profile ? (
              <EmptyState
                title="Connect the Google account that manages your listings"
                summary="Google requires separate permission before InsightOS can read a business listing. Your Google password is never shared with InsightOS."
                actionLabel="Connect Google business listings"
                onAction={() => void connectGoogle("gbp")}
              />
            ) : manageableCampaigns.length > 0 ? (
              <section id="profile-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match listings to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    One listing can belong to only one location. This prevents results from two
                    locations being mixed together.
                  </p>
                </div>
                {manageableCampaigns.map((campaign) => {
                  const connection = profileConnectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource =
                    profileDrafts[campaign.id] || connection?.external_resource_id || "";
                  const selectedProfile = profileResources.find(
                    (resource) => resource.id === selectedResource,
                  );
                  return (
                    <article
                      key={`profile-${campaign.id}`}
                      className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
                    >
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.9fr)_auto] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-semibold text-white">{campaign.name}</h3>
                            <span
                              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                                statusView
                                  ? toneClasses(statusView.tone)
                                  : "border-zinc-500/25 bg-zinc-500/10 text-zinc-300"
                              }`}
                            >
                              {statusView?.label || "Listing not matched"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful check: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the listing customers see for this business location."}
                          </p>
                          {connection?.last_error_message ? (
                            <p className="mt-2 text-xs leading-5 text-rose-200">
                              {connection.last_error_message}
                            </p>
                          ) : null}
                        </div>
                        <div>
                          <label
                            htmlFor={`profile-resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Google business listing
                          </label>
                          <select
                            id={`profile-resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={
                              profileResources.length === 0 || Boolean(connection?.last_success_at)
                            }
                            onChange={(event) =>
                              setProfileDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {profileResources.length === 0
                                ? "Load available listings first"
                                : "Choose a listing"}
                            </option>
                            {profileResources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name}
                                {resource.address ? ` · ${resource.address}` : ""}
                              </option>
                            ))}
                            {connection &&
                            !profileResources.some(
                              (resource) => resource.id === connection.external_resource_id,
                            ) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                          {selectedProfile ? (
                            <p className="mt-1.5 text-xs leading-5 text-zinc-500">
                              {selectedProfile.primary_category || "Category not returned"}
                              {selectedProfile.verified ? " · Verified listing" : ""}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {connection?.last_success_at ? (
                            <button
                              className={secondaryButtonClass}
                              onClick={() => window.location.assign("/local-visibility")}
                            >
                              See listing results
                            </button>
                          ) : null}
                          {connection ? (
                            <button
                              className={secondaryButtonClass}
                              disabled={
                                busyAction === `sync-${connection.id}` ||
                                connection.status === "syncing"
                              }
                              onClick={() => void syncConnection(connection)}
                            >
                              {busyAction === `sync-${connection.id}`
                                ? "Checking..."
                                : statusView?.action || "Check now"}
                            </button>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `profile-mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveProfileMapping(campaign)}
                            >
                              {busyAction === `profile-mapping-${campaign.id}`
                                ? "Matching..."
                                : "Match and run first check"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : null}

            <section>
              <article className="rounded-md border border-[#292a2f] bg-[#141518] p-5 opacity-80">
                <span className="rounded-full border border-zinc-500/25 bg-zinc-500/10 px-2.5 py-1 text-xs font-semibold text-zinc-300">
                  Planned later
                </span>
                <h2 className="mt-3 text-lg font-semibold text-white">
                  Website analytics and forms
                </h2>
                <p className="mt-2 text-sm leading-6 text-zinc-400">
                  Visits and website form events will be added after Search Console synchronization
                  is proven reliable. No CRM or call-tracking dependency is planned.
                </p>
              </article>
            </section>
          </>
        )}
      </section>
    </AppShell>
  );
}
