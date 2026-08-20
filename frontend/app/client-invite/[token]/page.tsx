"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";

import {
  LOADING_CLIENT_PORTAL_IDENTITY,
  safeClientPortalIdentity,
  type ClientPortalIdentity,
} from "../../clientPortalIdentity";
import { setAuthSession } from "../../lib/authStorage";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "/api/v1" : "http://localhost:8000/api/v1");

type Preview = {
  status: "active";
  email_hint: string;
  location_group_name: string;
  expires_at: string;
  identity?: ClientPortalIdentity;
};

async function invitationRequest(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = payload?.errors?.[0]?.details || payload?.detail || {};
    throw new Error(details.message || payload?.errors?.[0]?.message || "This invitation could not be opened.");
  }
  return payload.data;
}

export default function ClientInvitationPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const token = typeof params?.token === "string" ? params.token : "";
  const [preview, setPreview] = useState<Preview | null>(null);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const identity = preview
    ? safeClientPortalIdentity(preview.identity)
    : LOADING_CLIENT_PORTAL_IDENTITY;
  const existingPasswordLabel = identity.platform_attribution_visible
    ? "current InsightOS password"
    : "current report sign-in password";

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setError("This invitation link is incomplete.");
      setLoading(false);
      return;
    }
    void invitationRequest(`/client-invitations/${encodeURIComponent(token)}`)
      .then((response) => {
        if (!cancelled) setPreview(response as Preview);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "This invitation is no longer available.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function acceptInvitation(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password !== passwordConfirmation) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await invitationRequest(`/client-invitations/${encodeURIComponent(token)}/accept`, {
        method: "POST",
        body: JSON.stringify({ password, password_confirmation: passwordConfirmation }),
      });
      setAuthSession({ tenantId: response?.user?.tenant_id || response?.user?.organization_id || "" });
      router.replace("/client-reports");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Client access could not be activated.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.06),transparent_24%),#0d0e10] px-4 py-10 text-zinc-100">
      <section className="relative mx-auto max-w-lg overflow-hidden rounded-2xl border border-[#2b2d33] bg-[#141518] p-6 shadow-2xl md:p-8">
        <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: identity.accent_color }} />
        <div className="flex min-w-0 items-center gap-3">
          {identity.logo_data_url ? (
            // Stored invitation logos are server-verified still PNGs and never load an external origin.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={identity.logo_data_url} alt={`${identity.display_name} logo`} className="max-h-10 max-w-40 object-contain" />
          ) : null}
          <div className="min-w-0">
            <p className="truncate text-sm font-bold tracking-tight text-white">{identity.display_name}</p>
            <p className="mt-0.5 truncate text-xs text-zinc-500">{identity.portal_title}</p>
          </div>
        </div>
        <p className="mt-8 text-xs font-semibold uppercase tracking-[0.16em] text-zinc-400">Private client reports</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">Set up your report sign-in</h1>

        {loading ? <p className="mt-6 text-sm text-zinc-400" role="status">Checking this private invitation…</p> : null}

        {!loading && error && !preview ? (
          <div className="mt-6 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4" role="alert">
            <h2 className="font-semibold text-amber-100">This setup link is not available</h2>
            <p className="mt-1 text-sm leading-5 text-amber-100/80">{error}</p>
            <p className="mt-3 text-sm text-amber-100/80">Ask the person who invited you to create a new setup link.</p>
          </div>
        ) : null}

        {!loading && preview ? (
          <>
            <div className="mt-6 rounded-lg border border-sky-500/20 bg-sky-500/10 p-4">
              <p className="text-sm text-sky-50">This sign-in is for <strong>{preview.email_hint}</strong>.</p>
              <p className="mt-1 text-sm text-sky-100/75">You will only be able to read reports assigned to <strong>{preview.location_group_name}</strong>.</p>
            </div>
            <form onSubmit={acceptInvitation} className="mt-6 space-y-4">
              <label className="block text-sm font-medium text-zinc-200">
                Choose a password or enter your {existingPasswordLabel}
                <input
                  className="mt-2 w-full rounded-lg border border-[#373941] bg-[#0e0f11] px-3 py-3 text-white outline-none focus:border-zinc-400"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={1}
                  maxLength={128}
                  autoComplete="current-password"
                  required
                />
              </label>
              <label className="block text-sm font-medium text-zinc-200">
                Enter it again
                <input
                  className="mt-2 w-full rounded-lg border border-[#373941] bg-[#0e0f11] px-3 py-3 text-white outline-none focus:border-zinc-400"
                  type="password"
                  value={passwordConfirmation}
                  onChange={(event) => setPasswordConfirmation(event.target.value)}
                  minLength={1}
                  maxLength={128}
                  autoComplete="current-password"
                  required
                />
              </label>
              <p className="text-xs leading-5 text-zinc-500">
                New passwords need at least 12 characters with a letter and a number. If you already have a report sign-in, enter your current password. The person who invited you cannot see it.
              </p>
              {error ? <p className="text-sm text-rose-300" role="alert">{error}</p> : null}
              <button type="submit" disabled={submitting} className="w-full rounded-lg bg-white px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-200 disabled:opacity-50">
                {submitting ? "Activating private access…" : "Activate report access"}
              </button>
            </form>
          </>
        ) : null}

        {!loading && identity.platform_attribution_visible ? (
          <p className="mt-8 text-xs text-zinc-600">Private report access provided through InsightOS.</p>
        ) : null}
      </section>
    </main>
  );
}
