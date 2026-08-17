"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { platformApi } from "../../platform/api";
import {
  AppShell,
  EmptyState,
  LoadingCard,
  ProductIcon,
  ProductPageIntro,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";

type Me = { organization_id?: string; org_role?: string };
type CommercialCapability = {
  code: string;
  available: boolean;
  required_plan: string;
};
type CommercialSummary = {
  plan: { name: string };
  capabilities: CommercialCapability[];
};
type LocationGroup = { id: string; name: string; member_count: number; status: string };
type CampaignVariant = {
  id: string;
  location_name: string;
  status: "ready" | "blocked";
  status_label: string;
  rendered_payload: Record<string, string | null | boolean>;
  checks: Array<{ code: string; passed: boolean; message: string }>;
  message: string;
};
type ProfileCampaign = {
  id: string;
  name: string;
  action_type: "local_post" | "photo_upload";
  action_label: string;
  status: string;
  status_label: string;
  scheduled_for?: string | null;
  counts: { targeted: number; ready: number; blocked: number };
  variants: CampaignVariant[];
  preflight: { release_gate?: string; provider_changes_enabled?: boolean };
  provider_changes_enabled: boolean;
  can_preflight: boolean;
  can_approve: boolean;
  version: number;
};

const panelClass = "rounded-xl border border-[#292b31] bg-[#141518]";
const inputClass =
  "w-full rounded-lg border border-[#353740] bg-[#0f1012] px-3 py-2.5 text-sm text-white outline-none transition focus:border-accent-500";
const primaryButtonClass =
  "rounded-lg bg-accent-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-45";
const secondaryButtonClass =
  "rounded-lg border border-[#373941] bg-[#17181c] px-3.5 py-2 text-sm font-semibold text-zinc-100 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-45";

function statusTone(status: string) {
  if (status === "ready" || status === "approved_hold") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  if (status === "blocked") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-sky-500/25 bg-sky-500/10 text-sky-100";
}

export default function ProfileCampaignsPage() {
  const pathname = usePathname();
  const [organizationId, setOrganizationId] = useState("");
  const [orgRole, setOrgRole] = useState("");
  const [commercialSummary, setCommercialSummary] = useState<CommercialSummary | null | undefined>(undefined);
  const [groups, setGroups] = useState<LocationGroup[]>([]);
  const [campaigns, setCampaigns] = useState<ProfileCampaign[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [callToAction, setCallToAction] = useState("learn_more");
  const [destinationUrl, setDestinationUrl] = useState("{website}");
  const [scheduledFor, setScheduledFor] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadWorkspace = useCallback(async (orgId: string) => {
    const [groupResponse, campaignResponse, usageResponse] = await Promise.all([
      platformApi(`/organizations/${orgId}/location-groups`, { method: "GET" }),
      platformApi(`/organizations/${orgId}/profile-campaigns?limit=30`, { method: "GET" }),
      platformApi("/usage/credits", { method: "GET" }).catch(() => null),
    ]);
    const nextGroups = ((groupResponse?.items || []) as LocationGroup[]).filter((item) => item.status === "active");
    const nextCampaigns = (campaignResponse?.items || []) as ProfileCampaign[];
    setGroups(nextGroups);
    setCampaigns(nextCampaigns);
    setCommercialSummary(usageResponse as CommercialSummary | null);
    setSelectedGroupId((current) => current || nextGroups[0]?.id || "");
    setSelectedCampaignId((current) => current || nextCampaigns[0]?.id || "");
  }, []);

  useEffect(() => {
    let cancelled = false;
    void platformApi("/auth/me", { method: "GET" })
      .then(async (response) => {
        const orgId = (response as Me)?.organization_id || "";
        if (!orgId || cancelled) return;
        setOrganizationId(orgId);
        setOrgRole((response as Me)?.org_role || "");
        await loadWorkspace(orgId);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Profile campaigns could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadWorkspace]);

  const selectedCampaign = useMemo(
    () => campaigns.find((item) => item.id === selectedCampaignId) || campaigns[0] || null,
    [campaigns, selectedCampaignId],
  );
  const fleetCapability = commercialSummary?.capabilities.find(
    (item) => item.code === "business_profile_fleet_actions",
  );
  const profileFleetAccessAvailable = fleetCapability?.available === true;
  const profileFleetAccessKnown = fleetCapability !== undefined;

  const runAction = useCallback(
    async (key: string, action: () => Promise<void>) => {
      setBusy(key);
      setError("");
      setNotice("");
      try {
        await action();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "That action could not be completed.");
      } finally {
        setBusy("");
      }
    },
    [],
  );

  async function createCampaign(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !selectedGroupId || !name.trim() || !summary.trim()) return;
    await runAction("create", async () => {
      const key = `gbp-${Date.now()}`;
      const snapshotResponse = await platformApi(`/organizations/${organizationId}/target-snapshots`, {
        method: "POST",
        body: JSON.stringify({
          action_key: "gbp_local_post",
          request_key: `${key}-targets`,
          location_group_id: selectedGroupId,
          select_all_active: false,
          regions: [],
          included_location_ids: [],
          excluded_location_ids: [],
        }),
      });
      const draftResponse = await platformApi(`/organizations/${organizationId}/profile-campaigns`, {
        method: "POST",
        body: JSON.stringify({
          target_snapshot_id: snapshotResponse.target_snapshot.id,
          request_key: `${key}-draft`,
          name: name.trim(),
          action_type: "local_post",
          payload_template: {
            post_type: "update",
            summary: summary.trim(),
            call_to_action: callToAction,
            destination_url: callToAction === "none" || callToAction === "call" ? null : destinationUrl.trim(),
          },
          scheduled_for: scheduledFor ? new Date(scheduledFor).toISOString() : null,
        }),
      });
      const draft = draftResponse.profile_campaign as ProfileCampaign;
      const checkedResponse = await platformApi(
        `/organizations/${organizationId}/profile-campaigns/${draft.id}/preflight`,
        {
          method: "POST",
          body: JSON.stringify({ expected_version: draft.version }),
        },
      );
      const checked = checkedResponse.profile_campaign as ProfileCampaign;
      await loadWorkspace(organizationId);
      setSelectedCampaignId(checked.id);
      setName("");
      setSummary("");
      setNotice(
        checked.counts.ready > 0
          ? "The location-by-location preview is ready. Review it before approval."
          : "The draft was saved. The checks below show what must be connected or validated first.",
      );
    });
  }

  async function preflight(campaign: ProfileCampaign) {
    if (!organizationId) return;
    await runAction(`preflight-${campaign.id}`, async () => {
      await platformApi(`/organizations/${organizationId}/profile-campaigns/${campaign.id}/preflight`, {
        method: "POST",
        body: JSON.stringify({ expected_version: campaign.version }),
      });
      await loadWorkspace(organizationId);
      setSelectedCampaignId(campaign.id);
      setNotice("The checks and location previews are up to date.");
    });
  }

  async function approve(campaign: ProfileCampaign) {
    if (!organizationId) return;
    await runAction(`approve-${campaign.id}`, async () => {
      await platformApi(`/organizations/${organizationId}/profile-campaigns/${campaign.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ expected_version: campaign.version }),
      });
      await loadWorkspace(organizationId);
      setSelectedCampaignId(campaign.id);
      setNotice("The exact previews were approved. Publishing remains locked until Google's live action check passes.");
    });
  }

  const trustSignals: TrustSignal[] = error
    ? [{ label: "Profile campaigns", value: "Needs attention", tone: "danger" }]
    : [{ label: "Publishing", value: "Locked until Google validation", tone: "warning" }];

  return (
    <AppShell
      navItems={buildProductNav(pathname)}
      trustSignals={trustSignals}
      accountLabel="Profile operations"
      dateRangeLabel="Saved campaign previews"
    >
      <div className="mx-auto max-w-[1500px] space-y-5">
        <ProductPageIntro
          eyebrow="Multi-location profiles"
          title="Post across locations without opening every listing"
          summary="Write one business update, choose a saved group, and see the exact version for each location before anything can be approved."
        />

        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-50">
          <strong>Publishing is still locked.</strong> You can build, check, and approve exact previews now. No Google listing changes are sent until one owned profile and the production quota pass live validation.
        </div>
        {notice ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">{notice}</div> : null}
        {error ? <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div> : null}

        {loading ? <LoadingCard title="Loading profile campaigns" summary="Checking your saved groups and drafts." /> : null}

        {!loading && groups.length === 0 ? (
          <EmptyState
            icon="locations"
            title="Save a location group first"
            summary="Open Manage locations and group the profiles that should receive the same update."
            actionLabel="Open Manage locations"
            onAction={() => window.location.assign("/locations")}
          />
        ) : null}

        {!loading && groups.length > 0 ? (
          <div className="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
            {profileFleetAccessAvailable ? (
              <form className={`${panelClass} p-5`} onSubmit={createCampaign}>
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-accent-500/10 text-accent-400">
                  <ProductIcon name="profile-campaigns" size={21} />
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">New campaign</p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Write one update</h2>
                  <p className="mt-1 text-sm leading-6 text-zinc-400">Use confirmed location details to personalize it safely.</p>
                </div>
              </div>

              <div className="mt-5 space-y-4">
                <label className="block text-sm font-medium text-zinc-200">
                  Location group
                  <select className={`${inputClass} mt-1.5`} value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
                    {groups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.member_count} locations</option>)}
                  </select>
                </label>
                <label className="block text-sm font-medium text-zinc-200">
                  Campaign name
                  <input className={`${inputClass} mt-1.5`} value={name} onChange={(event) => setName(event.target.value)} placeholder="Example: Fall service reminder" maxLength={160} required />
                </label>
                <label className="block text-sm font-medium text-zinc-200">
                  Business update
                  <textarea className={`${inputClass} mt-1.5 min-h-32 resize-y`} value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="Example: {location_name} now offers same-week service in {city}." maxLength={1500} required />
                </label>
                <div className="rounded-lg border border-[#2b2d33] bg-[#101114] p-3 text-xs leading-5 text-zinc-400">
                  Available details: <span className="text-zinc-200">{"{location_name}"}, {"{city}"}, {"{region}"}, {"{website}"}</span>. If a location is missing a detail, only that location is blocked.
                </div>
                <label className="block text-sm font-medium text-zinc-200">
                  Button
                  <select className={`${inputClass} mt-1.5`} value={callToAction} onChange={(event) => setCallToAction(event.target.value)}>
                    <option value="learn_more">Learn more</option>
                    <option value="book">Book</option>
                    <option value="sign_up">Sign up</option>
                    <option value="call">Call</option>
                    <option value="none">No button</option>
                  </select>
                </label>
                {!(["none", "call"].includes(callToAction)) ? (
                  <label className="block text-sm font-medium text-zinc-200">
                    Button destination
                    <input className={`${inputClass} mt-1.5`} value={destinationUrl} onChange={(event) => setDestinationUrl(event.target.value)} placeholder="{website}/book" required />
                  </label>
                ) : null}
                <label className="block text-sm font-medium text-zinc-200">
                  Planned date and time <span className="font-normal text-zinc-500">(optional)</span>
                  <input className={`${inputClass} mt-1.5`} type="datetime-local" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} />
                </label>
                <button className={`${primaryButtonClass} w-full`} disabled={busy === "create"} type="submit">
                  {busy === "create" ? "Building previews..." : "Build location previews"}
                </button>
                <p className="text-xs leading-5 text-zinc-500">Photo campaigns use the same safe contract, including rights and checksum checks. The customer photo library will be added before photo publishing is opened.</p>
              </div>
              </form>
            ) : (
              <section
                aria-labelledby="profile-campaign-plan-heading"
                className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-amber-50"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-200/75">
                  {profileFleetAccessKnown ? "Growth feature" : "Plan check required"}
                </p>
                <h2 id="profile-campaign-plan-heading" className="mt-1.5 text-xl font-semibold text-white">
                  {profileFleetAccessKnown
                    ? "Bulk profile campaigns need Growth"
                    : "Plan access could not be checked"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-amber-50/85">
                  {profileFleetAccessKnown
                    ? `Your ${commercialSummary?.plan.name || "current"} plan and every saved campaign stay unchanged. Growth or Enterprise is required to create, recheck, approve, retry, or resume bulk profile work.`
                    : "Saved campaigns are still available to review. New campaign actions stay paused until InsightOS can confirm this workspace's plan."}
                </p>
                {profileFleetAccessKnown ? (
                  <div className="mt-4 border-t border-amber-200/15 pt-4">
                    <p className="text-sm font-semibold text-white">Growth supports multi-location profile operations</p>
                    <ul className="mt-2 space-y-1 text-sm leading-6 text-amber-50/80">
                      <li>✓ Prepare one approved update across a saved location group.</li>
                      <li>✓ Review each location&apos;s exact version before approval.</li>
                      <li>✓ Retry or resume governed bulk work without opening every profile.</li>
                    </ul>
                  </div>
                ) : null}
                <div className="mt-4">
                  {!profileFleetAccessKnown ? (
                    <button
                      className={secondaryButtonClass}
                      disabled={busy === "plan-check"}
                      onClick={() => void runAction("plan-check", () => loadWorkspace(organizationId))}
                      type="button"
                    >
                      {busy === "plan-check" ? "Checking..." : "Check plan access again"}
                    </button>
                  ) : orgRole === "org_owner" ? (
                    <Link
                      className="inline-flex rounded-lg border border-amber-200/30 bg-amber-50/10 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-amber-50/15"
                      href="/settings#plan-and-billing"
                    >
                      Review Growth plan
                    </Link>
                  ) : (
                    <p className="text-sm font-medium text-amber-100">Ask the workspace owner to review the plan.</p>
                  )}
                </div>
              </section>
            )}

            <section className={`${panelClass} min-w-0 p-5`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Saved work</p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Review every location</h2>
                  <p className="mt-1 text-sm leading-6 text-zinc-400">A campaign cannot silently grow or change after approval.</p>
                </div>
                {campaigns.length > 0 ? (
                  <select className="rounded-lg border border-[#353740] bg-[#0f1012] px-3 py-2 text-sm text-white" value={selectedCampaign?.id || ""} onChange={(event) => setSelectedCampaignId(event.target.value)}>
                    {campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name} · {campaign.status_label}</option>)}
                  </select>
                ) : null}
              </div>

              {!selectedCampaign ? (
                <div className="mt-5 rounded-lg border border-dashed border-[#353740] p-8 text-center text-sm text-zinc-400">Your first location-by-location preview will appear here.</div>
              ) : (
                <div className="mt-5 space-y-4">
                  <div className="grid gap-px overflow-hidden rounded-lg border border-[#2b2d33] bg-[#2b2d33] sm:grid-cols-3">
                    {[{ label: "Locations", value: selectedCampaign.counts.targeted }, { label: "Ready", value: selectedCampaign.counts.ready }, { label: "Needs setup", value: selectedCampaign.counts.blocked }].map((item) => (
                      <div key={item.label} className="bg-[#101114] p-4"><p className="text-xs text-zinc-500">{item.label}</p><p className="mt-1 text-2xl font-semibold text-white">{item.value}</p></div>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#2b2d33] bg-[#101114] p-4">
                    <div>
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone(selectedCampaign.status)}`}>{selectedCampaign.status_label}</span>
                      <p className="mt-2 text-sm text-zinc-300">{selectedCampaign.scheduled_for ? `Planned for ${new Date(selectedCampaign.scheduled_for).toLocaleString()}` : "No publishing time has been chosen."}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedCampaign.can_preflight && profileFleetAccessAvailable ? <button className={secondaryButtonClass} disabled={busy === `preflight-${selectedCampaign.id}`} onClick={() => preflight(selectedCampaign)}>{busy === `preflight-${selectedCampaign.id}` ? "Checking..." : "Run checks again"}</button> : null}
                      {selectedCampaign.can_approve && profileFleetAccessAvailable ? <button className={primaryButtonClass} disabled={busy === `approve-${selectedCampaign.id}`} onClick={() => approve(selectedCampaign)}>{busy === `approve-${selectedCampaign.id}` ? "Approving..." : "Approve exact previews"}</button> : null}
                    </div>
                  </div>
                  {!profileFleetAccessAvailable && (selectedCampaign.can_preflight || selectedCampaign.can_approve) ? (
                    <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm leading-6 text-amber-50">
                      This saved preview remains available. Bulk actions stay paused until plan access is confirmed.
                    </p>
                  ) : null}
                  <div className="space-y-3">
                    {selectedCampaign.variants.map((variant) => (
                      <article key={variant.id} className="rounded-lg border border-[#2b2d33] bg-[#101114] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="font-semibold text-white">{variant.location_name}</h3>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone(variant.status)}`}>{variant.status_label}</span>
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-200">{String(variant.rendered_payload.summary || "Photo details saved for review.")}</p>
                        {variant.rendered_payload.destination_url ? <p className="mt-2 break-all text-xs text-sky-300">{String(variant.rendered_payload.destination_url)}</p> : null}
                        {variant.status === "blocked" ? <p className="mt-3 text-sm text-amber-100">Next: {variant.message}</p> : null}
                        <details className="mt-3 border-t border-[#292b31] pt-3 text-xs text-zinc-400">
                          <summary className="cursor-pointer font-semibold text-zinc-300">See all checks</summary>
                          <ul className="mt-2 space-y-2">
                            {variant.checks.map((check) => <li key={check.code} className="flex gap-2"><ProductIcon name={check.passed ? "check" : "warning"} size={15} className={check.passed ? "text-emerald-400" : "text-amber-400"} /><span>{check.message}</span></li>)}
                          </ul>
                        </details>
                      </article>
                    ))}
                  </div>
                  {selectedCampaign.preflight?.release_gate ? <p className="rounded-lg border border-[#2b2d33] bg-[#101114] p-3 text-xs leading-5 text-zinc-400">{selectedCampaign.preflight.release_gate}</p> : null}
                </div>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
