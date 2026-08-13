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
import { getTenantId } from "../../lib/authStorage";
import { getConnectionStatusView } from "../truth/dataConnectionsTruth.mjs";
import { requestProductTour } from "../truth/productTour.mjs";

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

type AnalyticsResource = {
  id: string;
  name: string;
  account_name: string;
  property_type: string;
  can_edit: boolean;
  resource_scope: string;
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
  website_event_key_configured?: boolean;
  website_event_key_created_at?: string | null;
};

type WebsiteEventKey = {
  token: string;
  event_path: string;
  created_at: string;
};

type ConnectionsPayload = {
  google_oauth: {
    connected: boolean;
    approved_access?: {
      search_console: boolean;
      business_profile: boolean;
      website_analytics: boolean;
    };
    updated_at?: string | null;
  };
  connections: DataConnection[];
  health: ConnectionHealth;
};

type ConnectionHealthItem = {
  id: string;
  connection_id?: string | null;
  provider_name: string;
  label: string;
  status: string;
  display_state: "healthy" | "updating" | "needs_attention" | "needs_setup";
  summary: string;
  location_id: string;
  location_name: string;
  campaign_id: string;
  campaign_name: string;
  last_success_at?: string | null;
  newest_usable_data_date?: string | null;
  current_failure?: string | null;
  affected_features: string[];
  recovery_action: {
    kind: "none" | "wait" | "reconnect" | "map" | "sync";
    label: string;
    href?: string | null;
    connection_id?: string;
  };
};

type ConnectionHealth = {
  checked_at: string;
  summary: {
    headline: string;
    next_step: string;
    locations: number;
    sources: number;
    healthy: number;
    updating: number;
    needs_attention: number;
    needs_setup: number;
  };
  items: ConnectionHealthItem[];
};

type UsageAllowance = {
  plan: {
    code: string;
    name: string;
    monthly_price: number;
    included_locations: number;
    active_locations: number;
    remaining_locations: number;
    additional_locations_require_custom_terms: boolean;
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
  commercial_catalog_version: string;
  capabilities: Array<{
    code: string;
    label: string;
    summary: string;
    available: boolean;
    required_plan: string;
  }>;
  upgrade?: {
    plan_code: string;
    plan_name: string;
    monthly_price: number;
    headline: string;
    reasons: string[];
  } | null;
};

type BillingSummary = {
  provider_configured: boolean;
  plan_code: string;
  plan_name: string;
  status: string;
  status_label: string;
  portal_available: boolean;
  checkout_available: boolean;
  available_checkout_plans: string[];
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  recovery_message?: string | null;
};

type MigrationReview = {
  mode: "dry_run";
  review_hash: string;
  source_sha256: string;
  writes_performed: number;
  next_step: string;
  summary: {
    total_rows: number;
    ready: number;
    already_saved: number;
    duplicates_in_file: number;
    needs_attention: number;
    locations: number;
    keywords: number;
    competitors: number;
    ranking_history: number;
    listing_history: number;
  };
  ignored_columns: Array<{
    column: string;
    populated_rows: number;
    reason: string;
  }>;
  rows: Array<{
    row_number: number;
    record_type: string;
    location_name: string;
    status: "ready" | "already_saved" | "duplicate" | "needs_attention";
    detail: string;
    matched_location_name?: string | null;
    values: Record<string, string>;
    issues: Array<{ code: string; message: string }>;
  }>;
};

type MigrationBatch = {
  id: string;
  source_system: string;
  source_filename?: string | null;
  status: "applied" | "rolled_back";
  applied_at: string;
  rolled_back_at?: string | null;
  rollback_available: boolean;
  summary: MigrationReview["summary"] & {
    records_applied?: number;
    locations_created?: number;
    keywords_created?: number;
    competitors_created?: number;
    ranking_history_created?: number;
    listing_history_created?: number;
  };
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

function formatDataDate(value?: string | null) {
  if (!value) return "No usable data saved yet";
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function healthStatusLabel(item: ConnectionHealthItem) {
  if (item.display_state === "healthy") return "Healthy";
  if (item.display_state === "updating") return "Updating";
  if (item.display_state === "needs_attention") return "Needs attention";
  return "Finish setup";
}

function healthTone(item: ConnectionHealthItem) {
  if (item.display_state === "healthy") return "success";
  if (item.display_state === "needs_attention") return "danger";
  return item.display_state === "needs_setup" ? "warning" : "info";
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
  const [billingSummary, setBillingSummary] = useState<BillingSummary | null>(null);
  const [resources, setResources] = useState<SearchConsoleResource[]>([]);
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [profileResources, setProfileResources] = useState<BusinessProfileResource[]>([]);
  const [profileDrafts, setProfileDrafts] = useState<Record<string, string>>({});
  const [analyticsResources, setAnalyticsResources] = useState<AnalyticsResource[]>([]);
  const [analyticsDrafts, setAnalyticsDrafts] = useState<Record<string, string>>({});
  const [websiteEventKeys, setWebsiteEventKeys] = useState<Record<string, WebsiteEventKey>>({});
  const [loading, setLoading] = useState(true);
  const [loadingResources, setLoadingResources] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [guidedConnectionSetup, setGuidedConnectionSetup] = useState(false);
  const [migrationSource, setMigrationSource] = useState<"semrush" | "brightlocal" | "other">("other");
  const [migrationCsv, setMigrationCsv] = useState("");
  const [migrationFileName, setMigrationFileName] = useState("");
  const [migrationReview, setMigrationReview] = useState<MigrationReview | null>(null);
  const [migrationConfirmed, setMigrationConfirmed] = useState(false);
  const [migrationRequestId, setMigrationRequestId] = useState("");
  const [migrationBatch, setMigrationBatch] = useState<MigrationBatch | null>(null);
  const [migrationHistory, setMigrationHistory] = useState<MigrationBatch[]>([]);

  useEffect(() => {
    setGuidedConnectionSetup(
      new URLSearchParams(window.location.search).get("setup") === "connections",
    );
  }, []);

  const organizationId = me?.organization_id || "";
  const manageableCampaigns = useMemo(
    () => campaigns.filter((campaign) => Boolean(campaign.business_location_id)),
    [campaigns],
  );
  const connections = useMemo(() => payload?.connections || [], [payload?.connections]);
  const connectionHealth = payload?.health || null;
  const connectionItemsNeedingWork = useMemo(
    () => (connectionHealth?.items || []).filter((item) => item.display_state !== "healthy"),
    [connectionHealth],
  );
  const healthyConnectionItems = useMemo(
    () => (connectionHealth?.items || []).filter((item) => item.display_state === "healthy"),
    [connectionHealth],
  );
  const searchConsoleConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_search_console"),
    [connections],
  );
  const profileConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_business_profile"),
    [connections],
  );
  const analyticsConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_analytics"),
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
  const analyticsConnectionByCampaign = useMemo(
    () => new Map(analyticsConnections.map((connection) => [connection.campaign_id, connection])),
    [analyticsConnections],
  );
  const websiteMappingsComplete =
    manageableCampaigns.length > 0 &&
    manageableCampaigns.every((campaign) => connectionByCampaign.has(campaign.id));
  const profileMappingsComplete =
    manageableCampaigns.length > 0 &&
    manageableCampaigns.every((campaign) => profileConnectionByCampaign.has(campaign.id));
  const guidedStepsComplete = [
    Boolean(payload?.google_oauth.connected),
    websiteMappingsComplete,
    Boolean(payload?.google_oauth.approved_access?.business_profile) && profileMappingsComplete,
  ].filter(Boolean).length;

  function scrollToConnectionStep(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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
    setAnalyticsDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_analytics",
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

  const loadAnalyticsResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-analytics/resources`,
        { method: "GET" },
      )) as { resources?: AnalyticsResource[] };
      setAnalyticsResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no website analytics properties were returned. Confirm that this Google account can view the correct property.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load website analytics properties.");
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
        const [campaignResponse, connectionResponse, allowanceResponse, billingResponse, migrationResponse] = await Promise.all([
          platformApi("/campaigns", { method: "GET" }) as Promise<{ items?: Campaign[] }>,
          loadConnections(currentUser.organization_id),
          platformApi("/usage/credits", { method: "GET" }) as Promise<UsageAllowance>,
          (platformApi("/billing/summary", { method: "GET" }) as Promise<BillingSummary>)
            .catch(() => null),
          (platformApi(`/organizations/${currentUser.organization_id}/migration-imports`, {
            method: "GET",
          }) as Promise<{ items?: MigrationBatch[] }>).catch(() => ({ items: [] })),
        ]);
        setCampaigns(campaignResponse.items || []);
        setUsageAllowance(allowanceResponse);
        setBillingSummary(billingResponse);
        setMigrationHistory(migrationResponse.items || []);
        const returnParams = new URLSearchParams(window.location.search);
        const billingReturned = returnParams.get("billing");
        const googleReturned = returnParams.get("google");
        const returnSource = returnParams.get("source");
        if (billingReturned === "success") {
          setNotice("Checkout finished. We are confirming your plan now; access changes only after confirmation.");
          window.history.replaceState({}, "", "/settings");
        } else if (billingReturned === "cancelled") {
          setNotice("Checkout was closed. Your current plan and saved work were not changed.");
          window.history.replaceState({}, "", "/settings");
        } else if (googleReturned === "connected") {
          setNotice(
            returnSource === "business-profile"
              ? "Google business listings are connected. Match each location to its listing next."
              : returnSource === "analytics"
                ? "Website analytics is connected. Match each location to its analytics property next."
              : "Google Search Console is connected. Match each location to its website next.",
          );
          window.history.replaceState({}, "", "/settings");
          if (returnSource === "business-profile") {
            await loadProfileResources(currentUser.organization_id);
          } else if (returnSource === "analytics") {
            await loadAnalyticsResources(currentUser.organization_id);
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
  }, [loadAnalyticsResources, loadConnections, loadProfileResources, loadResources]);

  async function startCheckout(planCode: string) {
    setBusyAction("billing-checkout");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan_code: planCode }),
      })) as { url?: string };
      if (!response.url) throw new Error("The secure checkout link was not created.");
      window.location.assign(response.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open secure checkout.");
      setBusyAction("");
    }
  }

  async function manageBilling() {
    setBusyAction("billing-portal");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/billing/portal", {
        method: "POST",
      })) as { url?: string };
      if (!response.url) throw new Error("The secure billing link was not created.");
      window.location.assign(response.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open billing settings.");
      setBusyAction("");
    }
  }

  function downloadMigrationTemplate() {
    const template = [
      "Record Type,Location Name,Website,City,State,Country,Postal Code,Keyword,Group,Competitor,Position,Captured At,Source Record ID,Directory Name,Listing URL,Listing Status,Listing Business Name,Listing Address,Listing City,Listing Region,Listing Postal Code,Listing Phone,Listing Website,Primary Category,Directory Importance",
      "location,Reno Location,example.com,Reno,NV,US,89501,,,",
      "keyword,Reno Location,,,,,,junk removal reno,Core service,",
      "competitor,Reno Location,,,,,,,,competitor.com",
      "ranking,Reno Location,,,,,,junk removal reno,,,12,2026-07-31,legacy-row-101",
      "listing,Reno Location,,,,US,,,,,,2026-07-31,legacy-listing-101,Google Business Profile,https://example.com/profile,live,Example Junk Removal,123 Main St,Reno,NV,89501,775-555-0100,example.com,Junk Removal,essential",
    ].join("\r\n");
    const url = URL.createObjectURL(new Blob([template], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "insightos-migration-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function chooseMigrationFile(file?: File) {
    setMigrationReview(null);
    setMigrationConfirmed(false);
    setMigrationRequestId("");
    setMigrationBatch(null);
    setMigrationCsv("");
    setMigrationFileName("");
    if (!file) return;
    if (file.size > 1_500_000) {
      setError("Choose a CSV file smaller than 1.5 MB.");
      return;
    }
    setError("");
    setMigrationFileName(file.name);
    setMigrationCsv(await file.text());
  }

  async function reviewMigrationFile() {
    if (!organizationId || !migrationCsv) return;
    setBusyAction("migration-dry-run");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/dry-run`,
        {
          method: "POST",
          body: JSON.stringify({ source_system: migrationSource, csv_text: migrationCsv }),
        },
      )) as MigrationReview;
      setMigrationReview(response);
      setMigrationConfirmed(false);
      setMigrationRequestId(crypto.randomUUID());
    } catch (err) {
      setMigrationReview(null);
      setError(err instanceof Error ? err.message : "Unable to review this migration file.");
    } finally {
      setBusyAction("");
    }
  }

  async function applyMigrationFile() {
    if (!organizationId || !migrationCsv || !migrationReview || !migrationConfirmed) return;
    setBusyAction("migration-apply");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/apply`,
        {
          method: "POST",
          body: JSON.stringify({
            source_system: migrationSource,
            source_filename: migrationFileName || null,
            csv_text: migrationCsv,
            review_hash: migrationReview.review_hash,
            client_request_id: migrationRequestId,
            confirmed: true,
          }),
        },
      )) as { batch: MigrationBatch };
      setMigrationBatch(response.batch);
      setMigrationHistory((current) => [
        response.batch,
        ...current.filter((item) => item.id !== response.batch.id),
      ]);
      setNotice(
        `Import complete: ${response.batch.summary.records_applied || 0} reviewed rows were added.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to apply this migration file.");
    } finally {
      setBusyAction("");
    }
  }

  async function rollbackMigration(batch: MigrationBatch) {
    if (!organizationId || !batch.rollback_available) return;
    if (!window.confirm("Remove only the records created by this import? Newer attached work will be protected.")) {
      return;
    }
    setBusyAction(`migration-rollback-${batch.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/${batch.id}/rollback`,
        {
          method: "POST",
          body: JSON.stringify({ confirmed: true }),
        },
      )) as { batch: MigrationBatch };
      setMigrationBatch((current) => current?.id === batch.id ? response.batch : current);
      setMigrationHistory((current) => current.map((item) => (
        item.id === batch.id ? response.batch : item
      )));
      setNotice("The records created by this import were removed. The review history was kept.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to roll back this import.");
    } finally {
      setBusyAction("");
    }
  }

  async function connectGoogle(scopeTarget: "gsc" | "gbp" | "analytics" = "gsc") {
    if (!organizationId) return;
    setBusyAction(`oauth-${scopeTarget}`);
    setError("");
    setNotice("");
    try {
      const returnPath = guidedConnectionSetup
        ? scopeTarget === "gbp"
          ? "/settings?setup=connections&source=business-profile"
          : scopeTarget === "analytics"
            ? "/settings?setup=connections&source=analytics"
          : "/settings?setup=connections"
        : scopeTarget === "gbp"
          ? "/settings?source=business-profile"
          : scopeTarget === "analytics"
            ? "/settings?source=analytics"
          : "/settings";
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

  async function saveAnalyticsMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = analyticsDrafts[campaign.id] || "";
    const resource = analyticsResources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose the website analytics property for this location.");
      return;
    }
    setBusyAction(`analytics-mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-analytics/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            external_resource_id: resource.id,
            external_resource_name: resource.name,
          }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The website analytics match was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      setNotice(
        syncResponse.job?.status === "completed"
          ? `${campaign.name} is matched and its first website visit history is ready.`
          : `${campaign.name} is matched. Its first website visit update is queued.`,
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this analytics match.");
    } finally {
      setBusyAction("");
    }
  }

  async function createWebsiteEventKey(connection: DataConnection) {
    if (!organizationId) return;
    setBusyAction(`website-event-key-${connection.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connection.id}/website-events/key`,
        { method: "POST" },
      )) as WebsiteEventKey;
      if (!response.token || !response.event_path) {
        throw new Error("The secure form connection was not created.");
      }
      setWebsiteEventKeys((current) => ({ ...current, [connection.id]: response }));
      await loadConnections(organizationId);
      setNotice(
        "The secure form connection is ready. Copy it now; the private key will not be shown again.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the form connection.");
    } finally {
      setBusyAction("");
    }
  }

  async function syncConnection(connection: DataConnection) {
    if (!organizationId) return;
    if (connection.status === "reconnect_required") {
      await connectGoogle(
        connection.provider_name === "google_business_profile"
          ? "gbp"
          : connection.provider_name === "google_analytics"
            ? "analytics"
            : "gsc",
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

  async function handleHealthAction(item: ConnectionHealthItem) {
    if (item.recovery_action.kind === "none" || item.recovery_action.kind === "wait") return;
    if (item.recovery_action.kind === "sync" && item.connection_id) {
      const connection = connections.find((row) => row.id === item.connection_id);
      if (connection) await syncConnection(connection);
      return;
    }
    const href = item.recovery_action.href;
    if (!href) return;
    if (href.startsWith("/settings#")) {
      const anchor = href.split("#")[1];
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    if (item.provider_name === "google_business_profile") {
      await connectGoogle("gbp");
      return;
    }
    if (item.provider_name === "google_analytics") {
      await connectGoogle("analytics");
      return;
    }
    await connectGoogle("gsc");
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
        label: "Healthy sources",
        value: connectionHealth
          ? `${connectionHealth.summary.healthy}/${connectionHealth.summary.sources}`
          : "Checking",
        tone:
          connectionHealth && connectionHealth.summary.healthy === connectionHealth.summary.sources
            ? "success"
            : "warning",
      },
      {
        label: "Needs action",
        value: connectionHealth
          ? String(connectionHealth.summary.needs_attention + connectionHealth.summary.needs_setup)
          : "Checking",
        tone:
          connectionHealth && connectionHealth.summary.needs_attention > 0
            ? "danger"
            : connectionHealth && connectionHealth.summary.needs_setup > 0
              ? "warning"
              : "success",
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
    [connectionHealth, payload, usageAllowance],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel="Connection health"
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
          eyebrow="Connection health"
          title="Keep your business data flowing"
          summary="See what is working, what stopped updating, and the one step needed to fix each location."
        />

        <TruthNotice title="Use this page when your data stops updating" tone="info">
          InsightOS puts broken and unfinished connections first. Healthy connections stay out of
          the way because there is nothing you need to do with them.
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

        {guidedConnectionSetup && !loading ? (
          <section className="rounded-md border border-accent-500/30 bg-accent-500/5 p-5" aria-labelledby="guided-connections-title">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-200">
                  Finish setup
                </p>
                <h2 id="guided-connections-title" className="mt-1 text-xl font-semibold text-white">
                  Connect the information that keeps your results current
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                  Work from top to bottom. InsightOS will show the websites and listings your Google account can access, then keep every location&apos;s results separate.
                </p>
              </div>
              <span className="shrink-0 rounded-full border border-accent-500/25 bg-accent-500/10 px-3 py-1.5 text-xs font-semibold text-accent-100">
                {guidedStepsComplete} of 3 complete
              </span>
            </div>

            <ol className="mt-5 divide-y divide-[#303137] border-y border-[#303137]">
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">1</span>
                <div>
                  <p className="font-semibold text-white">Approve Google access</p>
                  <p className="mt-1 text-sm text-zinc-400">This securely connects your account. InsightOS never receives your Google password.</p>
                </div>
                {payload?.google_oauth.connected ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : (
                  <button type="button" className={primaryButtonClass} onClick={() => void connectGoogle()}>
                    Connect Google
                  </button>
                )}
              </li>
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">2</span>
                <div>
                  <p className="font-semibold text-white">Match each website to its location</p>
                  <p className="mt-1 text-sm text-zinc-400">This brings in Google appearances, website visits, and average position without mixing locations.</p>
                </div>
                {websiteMappingsComplete ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : payload?.google_oauth.connected ? (
                  <button type="button" className={primaryButtonClass} onClick={() => scrollToConnectionStep("website-mappings")}>
                    Match websites
                  </button>
                ) : (
                  <span className="text-sm text-zinc-500">Finish step 1 first</span>
                )}
              </li>
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">3</span>
                <div>
                  <p className="font-semibold text-white">Match each Google business listing</p>
                  <p className="mt-1 text-sm text-zinc-400">This connects listing details and customer actions. No listing changes are made automatically.</p>
                </div>
                {profileMappingsComplete && payload?.google_oauth.approved_access?.business_profile ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : payload?.google_oauth.approved_access?.business_profile ? (
                  <button type="button" className={primaryButtonClass} onClick={() => scrollToConnectionStep("profile-mappings")}>
                    Match listings
                  </button>
                ) : payload?.google_oauth.connected ? (
                  <button type="button" className={primaryButtonClass} onClick={() => void connectGoogle("gbp")}>
                    Approve listing access
                  </button>
                ) : (
                  <span className="text-sm text-zinc-500">Finish step 1 first</span>
                )}
              </li>
            </ol>

            {guidedStepsComplete === 3 ? (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4">
                <p className="text-sm font-medium text-emerald-100">Setup is complete. Your connected information will now update automatically.</p>
                <button
                  type="button"
                  className={primaryButtonClass}
                  onClick={() => {
                    requestProductTour(window.localStorage, getTenantId() || organizationId);
                    window.location.assign("/dashboard");
                  }}
                >
                  Open your dashboard
                </button>
              </div>
            ) : null}
          </section>
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
              title={connectionHealth?.summary.headline || "Checking your connections"}
              summary={
                connectionHealth
                  ? `${connectionHealth.summary.healthy} of ${connectionHealth.summary.sources} connected sources are healthy across ${connectionHealth.summary.locations} ${connectionHealth.summary.locations === 1 ? "location" : "locations"}.`
                  : "InsightOS is checking the latest saved connection history."
              }
              nextStep={connectionHealth?.summary.next_step || "Wait for the connection check to finish."}
              actionLabel={
                manageableCampaigns.length === 0
                  ? "Add a location"
                  : connectionItemsNeedingWork[0]?.recovery_action.label
              }
              onAction={
                manageableCampaigns.length === 0
                  ? () => window.location.assign("/locations")
                  : connectionItemsNeedingWork[0]
                    ? () => void handleHealthAction(connectionItemsNeedingWork[0])
                    : undefined
              }
              tone={
                (connectionHealth?.summary.needs_attention || 0) > 0
                  ? "urgent"
                  : (connectionHealth?.summary.needs_setup || 0) > 0
                    ? "warning"
                    : (connectionHealth?.summary.sources || 0) > 0
                      ? "positive"
                      : "neutral"
              }
              progress={
                connectionHealth && connectionHealth.summary.sources > 0
                  ? {
                      label: "Connected sources working normally",
                      value: connectionHealth.summary.healthy,
                      total: connectionHealth.summary.sources,
                      summary: "A source only counts as healthy after a successful update.",
                    }
                  : undefined
              }
            />

            {connectionItemsNeedingWork.length > 0 ? (
              <section aria-labelledby="connections-needing-work" className="space-y-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Do this next
                  </p>
                  <h2 id="connections-needing-work" className="mt-1 text-xl font-semibold text-white">
                    Fix these connections
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Work from the top. Each row shows what is affected and the next safe step.
                  </p>
                </div>
                <div className="divide-y divide-[#292a2f] border-y border-[#292a2f]">
                  {connectionItemsNeedingWork.map((item) => (
                    <article key={item.id} className="grid gap-4 py-4 lg:grid-cols-[1fr_auto] lg:items-center">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-white">{item.location_name} · {item.label}</h3>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClasses(healthTone(item))}`}>
                            {healthStatusLabel(item)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-zinc-300">{item.summary}</p>
                        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
                          <span>Last successful update: {formatTimestamp(item.last_success_at)}</span>
                          <span>Newest usable data: {formatDataDate(item.newest_usable_data_date)}</span>
                        </div>
                        {item.affected_features.length > 0 ? (
                          <p className="mt-2 text-xs text-amber-100/80">
                            May affect: {item.affected_features.join(", ")}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className={primaryButtonClass}
                        disabled={item.recovery_action.kind === "wait" || busyAction === `sync-${item.connection_id}`}
                        onClick={() => void handleHealthAction(item)}
                      >
                        {busyAction === `sync-${item.connection_id}` ? "Checking..." : item.recovery_action.label}
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            {healthyConnectionItems.length > 0 ? (
              <details className="border-y border-[#292a2f] py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-white">
                  <span>{healthyConnectionItems.length} healthy {healthyConnectionItems.length === 1 ? "connection" : "connections"}</span>
                  <span className="text-xs font-medium text-emerald-300">No action needed</span>
                </summary>
                <div className="mt-3 divide-y divide-[#292a2f]">
                  {healthyConnectionItems.map((item) => (
                    <div key={item.id} className="flex flex-col gap-1 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                      <span className="font-medium text-zinc-200">{item.location_name} · {item.label}</span>
                      <span className="text-xs text-zinc-500">Usable data through {formatDataDate(item.newest_usable_data_date)}</span>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}

            {usageAllowance ? (
              <section aria-labelledby="current-plan-heading" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
                {billingSummary?.recovery_message ? (
                  <div className="mb-5 rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-50">
                    <p className="font-semibold">Payment needs attention</p>
                    <p className="mt-1 leading-6 text-amber-100/80">{billingSummary.recovery_message}</p>
                    {billingSummary.portal_available ? (
                      <button
                        type="button"
                        className={`${primaryButtonClass} mt-3`}
                        disabled={busyAction === "billing-portal"}
                        onClick={() => void manageBilling()}
                      >
                        {busyAction === "billing-portal" ? "Opening..." : "Update payment method"}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Your plan
                    </p>
                    <h2 id="current-plan-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      {usageAllowance.plan.name} · ${usageAllowance.plan.monthly_price.toLocaleString()}/month
                    </h2>
                    <p className="mt-2 text-sm text-zinc-300">
                      {usageAllowance.plan.active_locations} of {usageAllowance.plan.included_locations} included {usageAllowance.plan.included_locations === 1 ? "location" : "locations"} in use
                    </p>
                    {billingSummary ? (
                      <p className="mt-1 text-xs text-zinc-500">
                        Billing: {billingSummary.status_label}
                        {billingSummary.cancel_at_period_end ? " · Ends after the current billing period" : ""}
                      </p>
                    ) : null}
                  </div>
                  <div className="grid gap-2 text-sm sm:grid-cols-2 lg:max-w-2xl">
                    {usageAllowance.capabilities.filter((item) => item.available).slice(0, 4).map((item) => (
                      <div key={item.code} className="border-l-2 border-emerald-500/40 pl-3">
                        <p className="font-semibold text-white">{item.label}</p>
                        <p className="mt-1 text-xs leading-5 text-zinc-400">{item.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
                {usageAllowance.upgrade ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-accent-200">
                          {usageAllowance.upgrade.plan_name} · ${usageAllowance.upgrade.monthly_price.toLocaleString()}/month
                        </p>
                        <h3 className="mt-1 font-semibold text-white">{usageAllowance.upgrade.headline}</h3>
                        <ul className="mt-2 space-y-1 text-sm leading-6 text-zinc-300">
                          {usageAllowance.upgrade.reasons.map((reason) => (
                            <li key={reason}>✓ {reason}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {billingSummary?.provider_configured &&
                        billingSummary.available_checkout_plans.includes(usageAllowance.upgrade.plan_code) ? (
                          <button
                            type="button"
                            className={primaryButtonClass}
                            disabled={busyAction === "billing-checkout"}
                            onClick={() => void startCheckout(usageAllowance.upgrade!.plan_code)}
                          >
                            {busyAction === "billing-checkout" ? "Opening checkout..." : "Upgrade securely"}
                          </button>
                        ) : (
                          <button type="button" className={secondaryButtonClass} onClick={() => window.location.assign("/help")}>Ask about upgrading</button>
                        )}
                        {billingSummary?.portal_available ? (
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === "billing-portal"}
                            onClick={() => void manageBilling()}
                          >
                            {busyAction === "billing-portal" ? "Opening..." : "Manage billing"}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : billingSummary?.portal_available ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4">
                    <button
                      type="button"
                      className={secondaryButtonClass}
                      disabled={busyAction === "billing-portal"}
                      onClick={() => void manageBilling()}
                    >
                      {busyAction === "billing-portal" ? "Opening..." : "Manage billing"}
                    </button>
                  </div>
                ) : null}
              </section>
            ) : null}

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

            <section id="google-search-console-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
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

            <section id="google-business-profile-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
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

            <section id="google-analytics-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Website visits and inquiries
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.approved_access?.website_analytics
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.approved_access?.website_analytics
                        ? "Access approved"
                        : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    See how many people visit the website, how many stay and engage, and how many
                    complete an approved inquiry action. Each location keeps its own history.
                  </p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                    This is read-only. CRM, call tracking, sales, and payment data are not included.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={
                      !payload?.google_oauth.approved_access?.website_analytics || loadingResources
                    }
                    onClick={() => void loadAnalyticsResources(organizationId)}
                  >
                    {loadingResources ? "Loading properties..." : "Load analytics properties"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-analytics"}
                    onClick={() => void connectGoogle("analytics")}
                  >
                    {payload?.google_oauth.approved_access?.website_analytics
                      ? "Reconnect website analytics"
                      : "Connect website analytics"}
                  </button>
                </div>
              </div>
            </section>

            {payload?.google_oauth.approved_access?.website_analytics && manageableCampaigns.length > 0 ? (
              <section id="analytics-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match analytics to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Choose the property that measures each location&apos;s website. This keeps results
                    from separate businesses from being mixed together.
                  </p>
                </div>
                {manageableCampaigns.map((campaign) => {
                  const connection = analyticsConnectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource =
                    analyticsDrafts[campaign.id] || connection?.external_resource_id || "";
                  return (
                    <article
                      key={`analytics-${campaign.id}`}
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
                              {statusView?.label || "Analytics not matched"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful update: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the website analytics property for this business location."}
                          </p>
                          {connection?.website_event_key_configured ? (
                            <p className="mt-2 text-xs font-medium text-emerald-200">
                              Secure website inquiry connection created
                            </p>
                          ) : null}
                          {connection && websiteEventKeys[connection.id] ? (
                            <div className="mt-3 rounded-md border border-amber-500/25 bg-amber-500/10 p-3">
                              <p className="text-xs font-semibold text-amber-100">
                                Copy this private form key now
                              </p>
                              <code className="mt-2 block break-all text-xs leading-5 text-amber-50">
                                {websiteEventKeys[connection.id].token}
                              </code>
                              <p className="mt-2 text-xs leading-5 text-amber-100/75">
                                Event address: {websiteEventKeys[connection.id].event_path}
                              </p>
                            </div>
                          ) : null}
                        </div>
                        <div>
                          <label
                            htmlFor={`analytics-resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Website analytics property
                          </label>
                          <select
                            id={`analytics-resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={
                              analyticsResources.length === 0 || Boolean(connection?.last_success_at)
                            }
                            onChange={(event) =>
                              setAnalyticsDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {analyticsResources.length === 0
                                ? "Load available properties first"
                                : "Choose a property"}
                            </option>
                            {analyticsResources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name} · {resource.account_name}
                              </option>
                            ))}
                            {connection &&
                            !analyticsResources.some(
                              (resource) => resource.id === connection.external_resource_id,
                            ) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                        </div>
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {connection ? (
                            <>
                              <button
                                className={secondaryButtonClass}
                                disabled={busyAction === `website-event-key-${connection.id}`}
                                onClick={() => void createWebsiteEventKey(connection)}
                              >
                                {busyAction === `website-event-key-${connection.id}`
                                  ? "Creating..."
                                  : connection.website_event_key_configured
                                    ? "Replace form key"
                                    : "Create form connection"}
                              </button>
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
                            </>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `analytics-mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveAnalyticsMapping(campaign)}
                            >
                              {busyAction === `analytics-mapping-${campaign.id}`
                                ? "Connecting..."
                                : "Match and start first update"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : null}

            <section aria-labelledby="migration-heading" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Moving from another SEO tool
                  </p>
                  <h2 id="migration-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                    Bring over locations, searches, and competitors
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    Put your existing setup into the InsightOS template, then check every match before anything is added.
                  </p>
                </div>
                <button type="button" className={secondaryButtonClass} onClick={downloadMigrationTemplate}>
                  Download CSV template
                </button>
              </div>

              <div className="mt-5 grid gap-4 border-t border-[#292a2f] pt-5 lg:grid-cols-[220px_minmax(0,1fr)_auto] lg:items-end">
                <div>
                  <label htmlFor="migration-source" className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Coming from
                  </label>
                  <select
                    id="migration-source"
                    className={selectClass}
                    value={migrationSource}
                    onChange={(event) => setMigrationSource(event.target.value as "semrush" | "brightlocal" | "other")}
                  >
                    <option value="other">Another spreadsheet</option>
                    <option value="semrush">Semrush</option>
                    <option value="brightlocal">BrightLocal</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="migration-file" className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Completed template
                  </label>
                  <input
                    id="migration-file"
                    type="file"
                    accept=".csv,text/csv"
                    className="block w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm text-zinc-200 file:mr-3 file:rounded file:border-0 file:bg-accent-500/15 file:px-3 file:py-1.5 file:font-semibold file:text-accent-100"
                    onChange={(event) => void chooseMigrationFile(event.target.files?.[0])}
                  />
                  <p className="mt-1.5 text-xs text-zinc-500">
                    {migrationFileName || "CSV only · up to 2,500 rows · no changes are made during review"}
                  </p>
                </div>
                <button
                  type="button"
                  className={primaryButtonClass}
                  disabled={!migrationCsv || busyAction === "migration-dry-run"}
                  onClick={() => void reviewMigrationFile()}
                >
                  {busyAction === "migration-dry-run" ? "Checking file..." : "Review file"}
                </button>
              </div>

              {migrationReview ? (
                <div className="mt-5 border-t border-[#292a2f] pt-5">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
                    {[
                      ["Ready to add", migrationReview.summary.ready, "text-emerald-200"],
                      ["Already saved", migrationReview.summary.already_saved, "text-sky-200"],
                      ["Repeated rows", migrationReview.summary.duplicates_in_file, "text-zinc-300"],
                      ["Needs attention", migrationReview.summary.needs_attention, "text-amber-200"],
                      ["Past rankings", migrationReview.summary.ranking_history, "text-violet-200"],
                      ["Past listings", migrationReview.summary.listing_history, "text-violet-200"],
                    ].map(([label, value, color]) => (
                      <div key={String(label)} className="border-l-2 border-[#35363c] pl-3">
                        <p className="text-xs text-zinc-500">{label}</p>
                        <p className={`mt-1 text-2xl font-semibold ${color}`}>{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-4 text-sm leading-6 text-zinc-300">{migrationReview.next_step}</p>

                  {migrationReview.ignored_columns.length > 0 ? (
                    <div className="mt-4 rounded-md border border-amber-500/25 bg-amber-500/5 p-4">
                      <p className="text-sm font-semibold text-amber-100">
                        {migrationReview.ignored_columns.length} file column{migrationReview.ignored_columns.length === 1 ? " is" : "s are"} not being imported
                      </p>
                      <p className="mt-1 text-sm leading-6 text-zinc-300">
                        These columns stay in your original file and are listed here so nothing is silently treated as an InsightOS measurement.
                      </p>
                      <ul className="mt-3 space-y-2 text-sm text-zinc-300">
                        {migrationReview.ignored_columns.map((item) => (
                          <li key={item.column}>
                            <strong className="text-white">{item.column}</strong> · {item.populated_rows} filled row{item.populated_rows === 1 ? "" : "s"} · {item.reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="mt-4 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                    {migrationReview.rows
                      .filter((row) => row.status === "needs_attention" || row.status === "duplicate")
                      .slice(0, 50)
                      .map((row) => (
                        <article key={`${row.row_number}-${row.record_type}`} className="grid gap-2 py-3 sm:grid-cols-[90px_minmax(0,1fr)]">
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Row {row.row_number}</p>
                          <div>
                            <p className="text-sm font-semibold text-white">
                              {row.location_name || "Location name missing"} · {row.record_type || "Unknown row"}
                            </p>
                            <p className="mt-1 text-sm text-amber-100">
                              {row.issues[0]?.message || row.detail}
                            </p>
                          </div>
                        </article>
                      ))}
                    {migrationReview.summary.needs_attention === 0 && migrationReview.summary.duplicates_in_file === 0 ? (
                      <p className="py-4 text-sm font-medium text-emerald-200">
                        Every row is ready for final review. Nothing has been imported yet.
                      </p>
                    ) : null}
                  </div>

                  {migrationReview.summary.needs_attention === 0 && migrationReview.summary.ready > 0 && !migrationBatch ? (
                    <div className="mt-5 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-4">
                      <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-zinc-200">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-orange-500"
                          checked={migrationConfirmed}
                          onChange={(event) => setMigrationConfirmed(event.target.checked)}
                        />
                        <span>
                          I reviewed this file. Add the {migrationReview.summary.ready} ready rows and skip anything already saved or repeated.
                        </span>
                      </label>
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          className={primaryButtonClass}
                          disabled={!migrationConfirmed || !migrationRequestId || busyAction === "migration-apply"}
                          onClick={() => void applyMigrationFile()}
                        >
                          {busyAction === "migration-apply" ? "Adding reviewed rows..." : "Import reviewed rows"}
                        </button>
                        <p className="text-xs leading-5 text-zinc-500">
                          The reviewed file is locked to this action. If it changes, InsightOS will require a new review.
                        </p>
                      </div>
                    </div>
                  ) : null}

                  {migrationBatch ? (
                    <div className="mt-5 flex flex-col gap-4 rounded-md border border-sky-500/25 bg-sky-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-sky-100">
                          {migrationBatch.status === "rolled_back" ? "Import removed safely" : "Import complete"}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-zinc-300">
                          {migrationBatch.status === "rolled_back"
                            ? "The records created by this import were removed, and its audit history was kept."
                            : `${migrationBatch.summary.locations_created || 0} locations, ${migrationBatch.summary.keywords_created || 0} searches, ${migrationBatch.summary.competitors_created || 0} competitors, ${migrationBatch.summary.ranking_history_created || 0} past ranking points, and ${migrationBatch.summary.listing_history_created || 0} past listing records were added.`}
                        </p>
                      </div>
                      {migrationBatch.rollback_available ? (
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          disabled={busyAction === `migration-rollback-${migrationBatch.id}`}
                          onClick={() => void rollbackMigration(migrationBatch)}
                        >
                          {busyAction === `migration-rollback-${migrationBatch.id}` ? "Checking rollback..." : "Undo this import"}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {migrationHistory.length > 0 ? (
                <div className="mt-5 border-t border-[#292a2f] pt-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Recent imports
                  </p>
                  <div className="mt-3 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                    {migrationHistory.slice(0, 5).map((batch) => (
                      <div key={batch.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <p className="text-sm font-medium text-white">
                            {batch.source_filename || "Imported setup"}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500">
                            {formatTimestamp(batch.applied_at)} · {batch.summary.records_applied || 0} rows · {batch.status === "rolled_back" ? "Undone" : "Applied"}
                          </p>
                        </div>
                        {batch.rollback_available ? (
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === `migration-rollback-${batch.id}`}
                            onClick={() => void rollbackMigration(batch)}
                          >
                            Undo import
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="mt-5 border-t border-[#292a2f] pt-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                  Switching checklist
                </p>
                <h3 className="mt-1 text-lg font-semibold text-white">Finish the move with fresh measurements</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-400">
                  Imported rankings and listings give you background history. They never count as a new InsightOS check. Complete these steps before using the new workspace as your current source of truth.
                </p>
                <ol className="mt-4 grid gap-3 lg:grid-cols-2">
                  {[
                    {
                      title: "Review and import the old setup",
                      detail: "Keep the source file and confirm every row before adding it.",
                      done: migrationHistory.some((batch) => batch.status === "applied"),
                    },
                    {
                      title: "Connect the business Google account",
                      detail: "This allows current website and business profile data to be collected.",
                      done: Boolean(payload?.google_oauth.connected),
                    },
                    {
                      title: "Match each location to its live source",
                      detail: "A saved location needs its own website or business profile connection.",
                      done: connections.length > 0,
                    },
                    {
                      title: "Run the first fresh checks",
                      detail: "Use the new results as the baseline; use imported history only for context.",
                      done: healthyConnectionItems.some((item) => Boolean(item.last_success_at)),
                    },
                  ].map((step, index) => (
                    <li key={step.title} className="flex gap-3 rounded-md border border-[#292a2f] bg-[#101114] p-4">
                      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${step.done ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-100" : "border-zinc-700 text-zinc-400"}`}>
                        {step.done ? "✓" : index + 1}
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-white">{step.title}</p>
                        <p className="mt-1 text-sm leading-5 text-zinc-400">{step.detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </section>
          </>
        )}
      </section>
    </AppShell>
  );
}
