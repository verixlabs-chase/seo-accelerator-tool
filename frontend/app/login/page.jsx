"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { setAuthSession } from "../lib/authStorage";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "/api/v1" : "http://localhost:8000/api/v1");

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaces, setWorkspaces] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectingWorkspaceId, setSelectingWorkspaceId] = useState("");

  function finishSignIn(user) {
    setAuthSession({ tenantId: user.tenant_id });
    router.replace("/dashboard");
    router.refresh();
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      const json = await res.json();
      if (!res.ok) {
        setError(json?.error?.message || "Login failed");
        return;
      }
      if (json.data.requires_org_selection) {
        setWorkspaces(json.data.organizations || []);
        return;
      }
      finishSignIn(json.data.user);
    } catch {
      setError("Unable to sign in right now. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function selectWorkspace(organizationId) {
    setError("");
    setSelectingWorkspaceId(organizationId);
    try {
      const res = await fetch(`${API_BASE}/auth/select-org`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId })
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(json?.error?.message || "That workspace could not be opened. Please try again.");
        return;
      }
      finishSignIn(json.data.user);
    } catch {
      setError("Unable to open that workspace right now. Please try again.");
    } finally {
      setSelectingWorkspaceId("");
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(255,106,26,0.16),transparent_22%),linear-gradient(180deg,#09090a_0%,#0b0b0c_52%,#101114_100%)] px-6 py-20 text-zinc-50">
      <div className="mx-auto max-w-md rounded-2xl border border-[#26272c] bg-[#111214]/92 p-8 shadow-[0_0_30px_rgba(0,0,0,0.35)] backdrop-blur">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">
          InsightOS
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">
          Sign in to your workspace
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-300">
          See what changed on Google, what needs attention, and what to work on next.
        </p>

        {workspaces.length ? (
          <div className="mt-8 space-y-3">
            <div>
              <p className="text-sm font-medium text-white">Choose the business you want to open</p>
              <p className="mt-1 text-sm leading-6 text-zinc-400">
                Your sign-in works with more than one business. Pick one to continue.
              </p>
            </div>
            {workspaces.map((workspace) => (
              <button
                key={workspace.organization_id}
                type="button"
                disabled={Boolean(selectingWorkspaceId)}
                onClick={() => selectWorkspace(workspace.organization_id)}
                className="flex w-full items-center justify-between gap-4 rounded-md border border-[#2c2d32] bg-[#0b0b0c] px-4 py-3 text-left transition hover:border-accent-500/40 hover:bg-accent-500/5 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span>
                  <span className="block text-sm font-medium text-zinc-100">
                    {workspace.name || "Business workspace"}
                  </span>
                  <span className="mt-1 block text-xs text-zinc-500">
                    {workspace.role === "org_owner" || workspace.role === "org_admin"
                      ? "You manage this business"
                      : "You have access to this business"}
                  </span>
                </span>
                <span className="text-sm text-zinc-300">
                  {selectingWorkspaceId === workspace.organization_id ? "Opening..." : "Open"}
                </span>
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                setWorkspaces([]);
                setPassword("");
              }}
              className="text-sm text-zinc-400 transition hover:text-white"
            >
              Use a different sign-in
            </button>
          </div>
        ) : (
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Email
            </label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
              className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2.5 text-sm font-medium text-zinc-100 transition hover:bg-accent-500/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
        )}

        {error ? (
          <p className="mt-4 rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
            {error}
          </p>
        ) : null}

        <p className="mt-4 text-xs leading-5 text-zinc-500">
          Your sign-in stays protected in a secure browser session.
        </p>

        <div className="mt-6 flex items-center justify-between gap-3 text-sm text-zinc-400">
          <span>Wrong workspace?</span>
          <Link href="/" className="text-zinc-200 transition hover:text-white">
            Back to home
          </Link>
        </div>
      </div>
    </main>
  );
}
