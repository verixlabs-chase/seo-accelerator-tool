import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(255,106,26,0.18),transparent_22%),linear-gradient(180deg,#09090a_0%,#0b0b0c_52%,#101114_100%)] px-6 py-20 text-zinc-50">
      <div className="mx-auto max-w-5xl">
        <div className="max-w-3xl rounded-2xl border border-[#26272c] bg-[#111214]/90 p-8 shadow-[0_0_30px_rgba(0,0,0,0.35)] backdrop-blur">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">
            InsightOS
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white md:text-5xl">
            Local search visibility, explained in plain English.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-zinc-300">
            Track how customers find your business, see what changed, and get a
            clear next step without digging through SEO tooling.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-accent-500/15"
            >
              Sign in
            </Link>
            <Link
              href="/dashboard"
              className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200 transition hover:border-[#33353b] hover:text-white"
            >
              Open dashboard
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
