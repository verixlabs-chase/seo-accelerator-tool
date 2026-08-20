"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";

import { PlatformApiError, platformApi } from "../../platform/api";
import { AppShell, DataState, LoadingCard, ProductPageIntro } from "../components";
import { buildProductNav } from "../nav.config";

type Me = { organization_id?: string; org_role?: string };
type LocationGroup = { id: string; name: string; member_count: number; status: string };
type Invitation = {
  id: string;
  email: string;
  location_group_id: string;
  location_group_name: string;
  location_count: number;
  status: "active" | "accepted" | "revoked" | "expired";
  version: number;
  expires_at: string;
  accepted_at?: string | null;
  created_at: string;
};
type InvitationList = { items: Invitation[]; count: number };

const panelClass = "rounded-xl border border-[#292b31] bg-[#141518]";
const inputClass =
  "w-full rounded-lg border border-[#353740] bg-[#0f1012] px-3 py-2.5 text-sm text-white outline-none transition focus:border-accent-500";

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function statusClasses(status: Invitation["status"]) {
  if (status === "active") return "border-sky-500/25 bg-sky-500/10 text-sky-200";
  if (status === "accepted") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  return "border-[#34363d] bg-[#191a1e] text-zinc-400";
}

export default function ClientAccessPage() {
  const pathname = usePathname();
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const [organizationId, setOrganizationId] = useState("");
  const [orgRole, setOrgRole] = useState("");
  const [groups, setGroups] = useState<LocationGroup[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [groupId, setGroupId] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("7");
  const [setupUrl, setSetupUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [accessState, setAccessState] = useState<"ready" | "owner" | "upgrade" | "error">("ready");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadWorkspace = useCallback(async (orgId: string) => {
    const [groupResponse, inviteResponse] = await Promise.all([
      platformApi(`/organizations/${orgId}/location-groups`, { method: "GET" }),
      platformApi("/enterprise/client-invitations", { method: "GET" }),
    ]);
    const nextGroups = ((groupResponse?.items || []) as LocationGroup[]).filter(
      (item) => item.status === "active" && item.member_count > 0,
    );
    setGroups(nextGroups);
    setGroupId((current) => current || nextGroups[0]?.id || "");
    setInvitations((inviteResponse as InvitationList).items || []);
    setAccessState("ready");
  }, []);

  useEffect(() => {
    let cancelled = false;
    void platformApi("/auth/me", { method: "GET" })
      .then(async (response) => {
        const me = response as Me;
        if (cancelled) return;
        setOrganizationId(me.organization_id || "");
        setOrgRole(me.org_role || "");
        if (me.org_role !== "org_owner") {
          setAccessState("owner");
          return;
        }
        if (me.organization_id) await loadWorkspace(me.organization_id);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof PlatformApiError && caught.reasonCode === "authenticated_client_reports_upgrade_required") {
          setAccessState("upgrade");
        } else {
          setAccessState("error");
          setError(caught instanceof Error ? caught.message : "Client access could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadWorkspace]);

  async function createInvitation(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !groupId || !email.trim()) return;
    setBusy("create");
    setError("");
    setNotice("");
    setSetupUrl("");
    try {
      const response = await platformApi("/enterprise/client-invitations", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          location_group_id: groupId,
          expires_in_days: Number(expiresInDays),
        }),
      });
      setSetupUrl(response.setup_url || "");
      setNotice(
        response.created
          ? "The setup link is ready. Send it to the client through a trusted message."
          : "The old setup link was replaced. Only this new link will work.",
      );
      setEmail("");
      await loadWorkspace(organizationId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The client invitation could not be created.");
    } finally {
      setBusy("");
    }
  }

  async function revokeInvitation(item: Invitation) {
    setBusy(item.id);
    setError("");
    setNotice("");
    try {
      await platformApi(`/enterprise/client-invitations/${item.id}/revoke`, {
        method: "POST",
        body: JSON.stringify({ expected_version: item.version }),
      });
      setNotice(
        item.status === "accepted"
          ? "That client can no longer open reports for this saved location group."
          : "That unused setup link can no longer be used.",
      );
      await loadWorkspace(organizationId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The invitation could not be turned off.");
    } finally {
      setBusy("");
    }
  }

  async function copySetupLink() {
    try {
      await navigator.clipboard.writeText(setupUrl);
      setNotice("Setup link copied.");
    } catch {
      setNotice("Select the setup link below and copy it.");
    }
  }

  return (
    <AppShell
      navItems={navItems}
      trustSignals={[]}
      accountLabel="Enterprise workspace"
      dateRangeLabel="Read-only client reports"
    >
      <div className="mx-auto max-w-6xl space-y-5">
        <ProductPageIntro
          eyebrow="Enterprise"
          title="Give clients their own report sign-in"
          summary="Create read-only access for one saved group of locations. Clients see assigned reports, not your workspace tools or private settings."
        />

        {loading ? <LoadingCard summary="Loading saved client access." /> : null}

        {!loading && accessState === "owner" ? (
          <DataState
            state="unsupported"
            title="Only the workspace owner can manage client access"
            summary="Ask the workspace owner to create or revoke client report invitations."
          />
        ) : null}

        {!loading && accessState === "upgrade" ? (
          <DataState
            state="unsupported"
            title="Client report sign-ins are available with Enterprise"
            summary="Enterprise lets each client sign in to read only the reports assigned to their saved location group."
            action={
              <Link href="/settings#plan-and-billing" className="inline-flex rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-white hover:bg-accent-400">
                Review Enterprise options
              </Link>
            }
          />
        ) : null}

        {!loading && accessState === "error" ? (
          <DataState state="error" title="Client access is unavailable right now" summary={error || "Try again in a moment."} />
        ) : null}

        {!loading && accessState === "ready" ? (
          <>
            <section className={`${panelClass} p-5`} aria-labelledby="invite-client-heading">
              <div className="max-w-3xl">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent-400">Private setup</p>
                <h2 id="invite-client-heading" className="mt-1 text-xl font-semibold text-white">Invite one client</h2>
                <p className="mt-2 text-sm leading-6 text-zinc-400">
                  InsightOS never shows you the client&apos;s password. The setup link works once and expires automatically.
                </p>
              </div>

              {groups.length === 0 ? (
                <DataState
                  state="unsupported"
                  title="Save a location group first"
                  summary="Create a saved group with at least one location, then return here to invite its client."
                  action={<Link href="/locations" className="text-sm font-semibold text-accent-300 underline underline-offset-4">Manage saved location groups</Link>}
                />
              ) : (
                <form onSubmit={createInvitation} className="mt-5 grid gap-4 md:grid-cols-2">
                  <label className="block text-sm font-medium text-zinc-200">
                    Client email
                    <input
                      className={`${inputClass} mt-2`}
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="email"
                      required
                      placeholder="client@example.com"
                    />
                  </label>
                  <label className="block text-sm font-medium text-zinc-200">
                    Reports they can see
                    <select className={`${inputClass} mt-2`} value={groupId} onChange={(event) => setGroupId(event.target.value)} required>
                      {groups.map((group) => (
                        <option key={group.id} value={group.id}>{group.name} · {group.member_count} {group.member_count === 1 ? "location" : "locations"}</option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm font-medium text-zinc-200">
                    Link expires in
                    <select className={`${inputClass} mt-2`} value={expiresInDays} onChange={(event) => setExpiresInDays(event.target.value)}>
                      <option value="3">3 days</option>
                      <option value="7">7 days</option>
                      <option value="14">14 days</option>
                    </select>
                  </label>
                  <div className="flex items-end">
                    <button type="submit" disabled={busy === "create"} className="w-full rounded-lg bg-accent-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50">
                      {busy === "create" ? "Creating secure link…" : "Create setup link"}
                    </button>
                  </div>
                </form>
              )}

              {setupUrl ? (
                <div className="mt-5 rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-4" role="status">
                  <h3 className="font-semibold text-emerald-100">Send this link now</h3>
                  <p className="mt-1 text-sm leading-5 text-emerald-100/80">For safety, InsightOS will not show this setup link again.</p>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <input readOnly value={setupUrl} aria-label="One-time client setup link" className="min-w-0 flex-1 rounded-md border border-emerald-400/25 bg-black/20 px-3 py-2 text-sm text-emerald-50" onFocus={(event) => event.currentTarget.select()} />
                    <button type="button" onClick={copySetupLink} className="rounded-md bg-emerald-400 px-4 py-2 text-sm font-semibold text-emerald-950 hover:bg-emerald-300">Copy link</button>
                  </div>
                </div>
              ) : null}

              {notice ? <p className="mt-4 text-sm text-emerald-300" role="status">{notice}</p> : null}
              {error ? <p className="mt-4 text-sm text-rose-300" role="alert">{error}</p> : null}
            </section>

            <section className={`${panelClass} p-5`} aria-labelledby="client-invitations-heading">
              <h2 id="client-invitations-heading" className="text-xl font-semibold text-white">Client setup history</h2>
              <p className="mt-1 text-sm text-zinc-400">Invitation links are never shown here again.</p>
              {invitations.length === 0 ? (
                <p className="mt-5 rounded-lg border border-dashed border-[#34363d] p-5 text-sm text-zinc-400">No client invitations have been created yet.</p>
              ) : (
                <ul className="mt-5 divide-y divide-[#292b31]">
                  {invitations.map((item) => (
                    <li key={item.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-medium text-white">{item.email}</p>
                          <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${statusClasses(item.status)}`}>{item.status}</span>
                        </div>
                        <p className="mt-1 text-sm text-zinc-400">{item.location_group_name} · {item.location_count} {item.location_count === 1 ? "location" : "locations"}</p>
                        <p className="mt-1 text-xs text-zinc-500">{item.status === "accepted" && item.accepted_at ? `Activated ${formatDate(item.accepted_at)}` : `Expires ${formatDate(item.expires_at)}`}</p>
                      </div>
                      {item.status === "active" || item.status === "accepted" ? (
                        <button type="button" disabled={busy === item.id} onClick={() => void revokeInvitation(item)} className="rounded-md border border-[#3a3c44] px-3 py-2 text-sm font-semibold text-zinc-200 hover:border-rose-400/50 hover:text-rose-200 disabled:opacity-50">
                          {busy === item.id
                            ? "Turning off…"
                            : item.status === "accepted"
                              ? "Remove report access"
                              : "Turn off link"}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}

        <p className="sr-only">Current role: {orgRole || "unavailable"}</p>
      </div>
    </AppShell>
  );
}
