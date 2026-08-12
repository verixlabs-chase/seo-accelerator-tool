"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  AppShell,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
} from "../components";
import { buildProductNav } from "../nav.config";
import {
  GLOSSARY_TERMS,
  HELP_AUDIENCES,
  HELP_GUIDES,
  matchesHelpSearch,
  type HelpAudience,
} from "./helpContent";

export default function HelpPage() {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState<HelpAudience>("solo");
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);

  const visibleGuides = useMemo(
    () =>
      HELP_GUIDES.filter(
        (guide) =>
          guide.audiences.includes(audience) &&
          matchesHelpSearch(
            [
              guide.title,
              guide.summary,
              guide.category,
              ...guide.steps,
              ...guide.searchTerms,
            ],
            query,
          ),
      ),
    [audience, query],
  );

  const visibleTerms = useMemo(
    () =>
      GLOSSARY_TERMS.filter((item) =>
        matchesHelpSearch(
          [item.term, item.meaning, item.usefulBecause, ...item.searchTerms],
          query,
        ),
      ),
    [query],
  );

  const categories = useMemo(
    () =>
      ["Get started", "Understand results", "Take action", "Fix a problem"].map(
        (category) => ({
          category,
          guides: visibleGuides.filter((guide) => guide.category === category),
        }),
      ),
    [visibleGuides],
  );

  const resultCount = visibleGuides.length + visibleTerms.length;

  return (
    <AppShell
      navItems={navItems}
      trustSignals={[]}
      accountLabel="Help for your workspace"
      dateRangeLabel="Practical guides"
      topBarActions={
        <a
          href="mailto:support@verixlabs.com?subject=InsightOS%20help"
          className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
        >
          Email support
        </a>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Help Center"
          title="Find the answer and keep moving"
          summary="Search by the job you are trying to finish. Every guide uses the same words you see inside InsightOS."
        />

        <TruthNotice title="Search by the task, problem, or number on your screen.">
          Try words such as connect Google, track searches, local map, website problem, report, or stale information.
        </TruthNotice>

        <section className="rounded-lg border border-[#2b2c31] bg-[#141518] p-5 md:p-6">
          <label
            htmlFor="help-search"
            className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400"
          >
            What do you need help with?
          </label>
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <div className="relative flex-1">
              <ProductIcon
                name="keyword-research"
                size={19}
                className="pointer-events-none absolute left-3 top-3 text-zinc-500"
              />
              <input
                id="help-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Example: connect Google, understand position, or create a report"
                className="w-full rounded-md border border-[#303137] bg-[#0b0b0c] py-2.5 pl-10 pr-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-accent-500/60"
              />
            </div>
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="rounded-md border border-[#303137] bg-[#111214] px-4 py-2 text-sm font-medium text-zinc-300 hover:text-white"
              >
                Clear search
              </button>
            ) : null}
          </div>
          <p className="mt-3 text-sm text-zinc-400" aria-live="polite">
            {query
              ? `${resultCount} helpful result${resultCount === 1 ? "" : "s"} found.`
              : "Choose the kind of work you manage, then open the guide that matches your next job."}
          </p>
        </section>

        <section aria-labelledby="help-audience-title">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
            Show the most useful guides for
          </p>
          <h2 id="help-audience-title" className="mt-1.5 text-xl font-semibold text-white">
            Your type of workspace
          </h2>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {HELP_AUDIENCES.map((item) => {
              const selected = audience === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setAudience(item.id)}
                  className={`rounded-md border p-4 text-left transition ${
                    selected
                      ? "border-accent-500/50 bg-accent-500/10 text-white"
                      : "border-[#2b2c31] bg-[#141518] text-zinc-300 hover:border-[#3a3b42]"
                  }`}
                >
                  <span className="text-sm font-semibold">{item.label}</span>
                  <span className="mt-1.5 block text-sm leading-6 text-zinc-400">
                    {item.description}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {visibleGuides.length > 0 ? (
          <section className="space-y-6" aria-labelledby="help-guides-title">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                Step-by-step help
              </p>
              <h2 id="help-guides-title" className="mt-1.5 text-xl font-semibold text-white">
                Open the guide that matches your next job
              </h2>
            </div>

            {categories.map(({ category, guides }) =>
              guides.length > 0 ? (
                <div key={category}>
                  <h3 className="mb-3 text-sm font-semibold text-zinc-200">{category}</h3>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {guides.map((guide) => (
                      <details
                        key={guide.id}
                        className="group rounded-md border border-[#2b2c31] bg-[#141518] open:border-accent-500/30"
                      >
                        <summary className="flex cursor-pointer list-none items-start gap-3 p-4">
                          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-md bg-accent-500/10 text-accent-400 ring-1 ring-inset ring-accent-500/20">
                            <ProductIcon name={guide.icon} size={18} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-semibold text-white">
                              {guide.title}
                            </span>
                            <span className="mt-1.5 block text-sm leading-6 text-zinc-400">
                              {guide.summary}
                            </span>
                          </span>
                          <span
                            aria-hidden="true"
                            className="mt-1 text-lg text-zinc-500 transition group-open:rotate-45"
                          >
                            +
                          </span>
                        </summary>
                        <div className="border-t border-[#2b2c31] px-4 pb-4 pt-4">
                          <ol className="space-y-3">
                            {guide.steps.map((step, index) => (
                              <li key={step} className="flex gap-3 text-sm leading-6 text-zinc-300">
                                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#202126] text-xs font-semibold text-zinc-200">
                                  {index + 1}
                                </span>
                                <span>{step}</span>
                              </li>
                            ))}
                          </ol>
                          <Link
                            href={guide.actionHref}
                            className="mt-5 inline-flex rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-2 text-sm font-medium text-zinc-100"
                          >
                            {guide.actionLabel} &rarr;
                          </Link>
                        </div>
                      </details>
                    ))}
                  </div>
                </div>
              ) : null,
            )}
          </section>
        ) : null}

        {visibleTerms.length > 0 ? (
          <section aria-labelledby="help-words-title">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
              Words on your screen
            </p>
            <h2 id="help-words-title" className="mt-1.5 text-xl font-semibold text-white">
              Plain-language definitions
            </h2>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {visibleTerms.map((item) => (
                <article key={item.term} className="rounded-md border border-[#2b2c31] bg-[#141518] p-4">
                  <h3 className="text-sm font-semibold text-white">{item.term}</h3>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{item.meaning}</p>
                  <p className="mt-3 border-t border-[#2b2c31] pt-3 text-xs leading-5 text-zinc-500">
                    <span className="font-semibold text-zinc-400">Why it helps:</span>{" "}
                    {item.usefulBecause}
                  </p>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {resultCount === 0 ? (
          <section className="rounded-md border border-amber-500/25 bg-amber-500/10 p-5">
            <h2 className="text-base font-semibold text-amber-100">No matching guide yet</h2>
            <p className="mt-2 text-sm leading-6 text-amber-100/80">
              Try fewer words, or email support with the business name, location, page, and the step you were trying to finish.
            </p>
            <button
              type="button"
              onClick={() => setQuery("")}
              className="mt-4 rounded-md border border-amber-500/30 bg-[#141518] px-3 py-2 text-sm font-medium text-amber-100"
            >
              Show all guides
            </button>
          </section>
        ) : null}

        <section className="rounded-lg border border-[#2b2c31] bg-[#141518] p-5 md:p-6">
          <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                Still stuck?
              </p>
              <h2 className="mt-1.5 text-xl font-semibold text-white">Send a useful support request</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                Email support with enough context to find the problem without sharing private login information.
              </p>
              <a
                href="mailto:support@verixlabs.com?subject=InsightOS%20help"
                className="mt-4 inline-flex rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
              >
                Email support@verixlabs.com
              </a>
            </div>
            <div className="rounded-md border border-[#303137] bg-[#0f1012] p-4">
              <p className="text-sm font-semibold text-white">Include these four details</p>
              <ol className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                <li>1. Business and location name</li>
                <li>2. Page where the problem happened</li>
                <li>3. What you were trying to finish</li>
                <li>4. The exact message shown on screen</li>
              </ol>
              <p className="mt-3 border-t border-[#303137] pt-3 text-xs leading-5 text-rose-200">
                Never send a password, sign-in code, payment number, or private access key.
              </p>
            </div>
          </div>
        </section>
      </section>
    </AppShell>
  );
}
