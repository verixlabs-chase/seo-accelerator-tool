"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { setAuthSession } from "../lib/authStorage";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
      setAuthSession({
        tenantId: json.data.user.tenant_id,
      });
      router.push("/dashboard");
    } catch {
      setError("Unable to sign in right now. Please try again.");
    } finally {
      setLoading(false);
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
          Open your dashboard to review visibility changes, recommended actions,
          and report delivery status.
        </p>

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

        {error ? (
          <p className="mt-4 rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
            {error}
          </p>
        ) : null}

        <p className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm leading-6 text-amber-50">
          This workspace now uses a server-backed httpOnly session cookie. The browser no longer
          keeps your auth tokens in JS-accessible storage.
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
