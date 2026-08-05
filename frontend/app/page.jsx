import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(255,106,26,0.18),transparent_22%),linear-gradient(180deg,#09090a_0%,#0b0b0c_52%,#101114_100%)] px-6 py-20 text-zinc-50">
      <div className="mx-auto max-w-5xl">
        <div className="max-w-3xl rounded-2xl border border-[#26272c] bg-[#111214]/90 p-8 shadow-[0_0_30px_rgba(0,0,0,0.35)] backdrop-blur">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">
            InsightOS local-search platform
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white md:text-5xl">
            InsightOS helps service businesses improve how they appear on Google.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-zinc-300">
            InsightOS connects to Google Search Console and Google Business Profile,
            measures search rankings and website health for each business location,
            and turns those results into clear, practical next steps.
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
          <section
            aria-labelledby="what-insightos-does"
            className="mt-8 border-t border-[#26272c] pt-6"
          >
            <h2
              id="what-insightos-does"
              className="text-lg font-semibold tracking-[-0.02em] text-white"
            >
              What InsightOS does
            </h2>
            <ul className="mt-3 grid gap-3 text-sm leading-6 text-zinc-300 md:grid-cols-3">
              <li className="rounded-lg border border-[#26272c] bg-[#141518] p-4">
                Shows how customers find and visit your business from Google Search.
              </li>
              <li className="rounded-lg border border-[#26272c] bg-[#141518] p-4">
                Tracks rankings, local visibility, business listings, and website
                health by location.
              </li>
              <li className="rounded-lg border border-[#26272c] bg-[#141518] p-4">
                Recommends prioritized work in plain language so you know what to do
                and why it matters.
              </li>
            </ul>
          </section>
          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 border-t border-[#26272c] pt-5 text-xs text-zinc-500">
            <Link className="transition hover:text-zinc-200" href="/privacy">
              Privacy policy
            </Link>
            <Link className="transition hover:text-zinc-200" href="/terms">
              Terms of service
            </Link>
            <a
              className="transition hover:text-zinc-200"
              href="mailto:chase@topdogdigitalsolutions.com"
            >
              Support
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
