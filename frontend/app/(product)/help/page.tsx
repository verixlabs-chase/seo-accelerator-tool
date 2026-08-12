"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  AppShell,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";
import { getTenantId } from "../../lib/authStorage";
import { PRODUCT_TOUR_EVENT, requestProductTour } from "../truth/productTour.mjs";
import {
  GLOSSARY_TERMS,
  HELP_AUDIENCES,
  HELP_GUIDES,
  matchesHelpSearch,
  type HelpAudience,
} from "./helpContent";

type SupportRequest = {
  id: string;
  reference_code: string;
  category: string;
  customer_summary: string;
  priority: string;
  status: string;
  status_label: string;
  response_expectation: string;
  response_target_at: string;
  diagnostic_attached: boolean;
  operator_access_consent: boolean;
  operator_access_expires_at?: string | null;
  escalated_at?: string | null;
  created_at: string;
};

const SUPPORT_CATEGORIES = [
  { value: "setup", label: "Finishing setup" },
  { value: "connection", label: "Connecting Google" },
  { value: "data_not_updating", label: "Information is not updating" },
  { value: "results_question", label: "Understanding results" },
  { value: "recommended_action", label: "A recommended action" },
  { value: "report", label: "A report" },
  { value: "billing", label: "Billing or plan" },
  { value: "other", label: "Something else" },
];

const SUPPORT_PAGES = new Set([
  "/dashboard",
  "/settings",
  "/rankings",
  "/local-visibility",
  "/site-health",
  "/opportunities",
  "/reports",
  "/reviews",
  "/keyword-research",
  "/locations",
  "/help",
]);

function formatSupportTime(value?: string | null) {
  if (!value) return "Not set";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not set";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function HelpPage() {
  const pathname = usePathname();
  const { selectedCampaignId, selectedCampaign } = useLocationContext();
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState<HelpAudience>("solo");
  const [supportCategory, setSupportCategory] = useState("setup");
  const [supportPage, setSupportPage] = useState("/help");
  const [supportSummary, setSupportSummary] = useState("");
  const [diagnosticConsent, setDiagnosticConsent] = useState(false);
  const [operatorAccessConsent, setOperatorAccessConsent] = useState(false);
  const [supportBusy, setSupportBusy] = useState(false);
  const [supportError, setSupportError] = useState("");
  const [supportNotice, setSupportNotice] = useState("");
  const [supportRequests, setSupportRequests] = useState<SupportRequest[]>([]);
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);

  const loadSupportRequests = useCallback(async () => {
    const response = (await platformApi("/support/requests")) as {
      items?: SupportRequest[];
    };
    setSupportRequests(response.items || []);
  }, []);

  useEffect(() => {
    const source = new URLSearchParams(window.location.search).get("from") || "";
    if (SUPPORT_PAGES.has(source)) setSupportPage(source);
    void loadSupportRequests().catch(() => undefined);
  }, [loadSupportRequests]);

  async function createSupportRequest() {
    if (supportSummary.trim().length < 10) {
      setSupportError("Tell us what you were trying to finish and what stopped you.");
      return;
    }
    setSupportBusy(true);
    setSupportError("");
    setSupportNotice("");
    try {
      const response = (await platformApi("/support/requests", {
        method: "POST",
        body: JSON.stringify({
          category: supportCategory,
          page_path: SUPPORT_PAGES.has(supportPage) ? supportPage : "/other",
          customer_summary: supportSummary.trim(),
          campaign_id: selectedCampaignId || null,
          diagnostic_consent: diagnosticConsent,
          operator_access_consent: operatorAccessConsent,
        }),
      })) as { request: SupportRequest };
      setSupportRequests((current) => [response.request, ...current]);
      setSupportSummary("");
      setSupportNotice(
        `Support request ${response.request.reference_code} was received. ${response.request.response_expectation}.`,
      );
    } catch (error) {
      setSupportError(
        error instanceof Error ? error.message : "We could not save your support request.",
      );
    } finally {
      setSupportBusy(false);
    }
  }

  async function escalateSupportRequest(requestId: string) {
    setSupportBusy(true);
    setSupportError("");
    try {
      const response = (await platformApi(`/support/requests/${requestId}/escalate`, {
        method: "POST",
        body: JSON.stringify({ reason: "business_impact" }),
      })) as { request: SupportRequest };
      setSupportRequests((current) =>
        current.map((item) => (item.id === requestId ? response.request : item)),
      );
      setSupportNotice(`${response.request.reference_code} was moved to priority review.`);
    } catch (error) {
      setSupportError(
        error instanceof Error ? error.message : "We could not escalate this request.",
      );
    } finally {
      setSupportBusy(false);
    }
  }

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

  function startQuickTour() {
    requestProductTour(window.localStorage, getTenantId() || "current", audience);
    window.dispatchEvent(
      new CustomEvent(PRODUCT_TOUR_EVENT, { detail: { persona: audience } }),
    );
  }

  return (
    <AppShell
      navItems={navItems}
      trustSignals={[]}
      accountLabel="Help for your workspace"
      dateRangeLabel="Practical guides"
      topBarActions={
        <button
          type="button"
          onClick={() => document.getElementById("support-request")?.scrollIntoView({ behavior: "smooth" })}
          className="rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
        >
          Get support
        </button>
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
              What these terms mean
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

        <section id="support-request" className="rounded-lg border border-[#2b2c31] bg-[#141518] p-5 md:p-6">
          <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                Still stuck?
              </p>
              <h2 className="mt-1.5 text-xl font-semibold text-white">Ask the support team for help</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                Send a tracked request and see when the team starts investigating. You decide whether to attach a safe system summary.
              </p>

              {supportError ? (
                <div className="mt-4 rounded-md border border-rose-500/25 bg-rose-500/10 p-3 text-sm text-rose-100">
                  {supportError}
                </div>
              ) : null}
              {supportNotice ? (
                <div className="mt-4 rounded-md border border-emerald-500/25 bg-emerald-500/10 p-3 text-sm text-emerald-100">
                  {supportNotice}
                </div>
              ) : null}

              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="support-category" className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    What do you need help with?
                  </label>
                  <select
                    id="support-category"
                    value={supportCategory}
                    onChange={(event) => setSupportCategory(event.target.value)}
                    className="mt-2 w-full rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100"
                  >
                    {SUPPORT_CATEGORIES.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="support-page" className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    Where did it happen?
                  </label>
                  <select
                    id="support-page"
                    value={supportPage}
                    onChange={(event) => setSupportPage(event.target.value)}
                    className="mt-2 w-full rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100"
                  >
                    {Array.from(SUPPORT_PAGES).map((item) => (
                      <option key={item} value={item}>{item === "/help" ? "Help Center" : item.slice(1).replaceAll("-", " ")}</option>
                    ))}
                    <option value="/other">Somewhere else</option>
                  </select>
                </div>
              </div>

              <label htmlFor="support-summary" className="mt-4 block text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                What were you trying to finish, and what stopped you?
              </label>
              <textarea
                id="support-summary"
                rows={5}
                maxLength={800}
                value={supportSummary}
                onChange={(event) => setSupportSummary(event.target.value)}
                placeholder="Example: I reconnected Google, but this location still says the information is out of date."
                className="mt-2 w-full rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2.5 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-accent-500/60"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Location: {selectedCampaign?.name || selectedCampaign?.domain || "No location selected"} · {supportSummary.length}/800
              </p>

              <div className="mt-4 space-y-3">
                <label className="flex items-start gap-3 rounded-md border border-[#303137] bg-[#0f1012] p-3">
                  <input
                    type="checkbox"
                    checked={diagnosticConsent}
                    onChange={(event) => setDiagnosticConsent(event.target.checked)}
                    className="mt-1"
                  />
                  <span className="text-sm leading-6 text-zinc-300">
                    <span className="font-semibold text-white">Attach a safe system summary.</span>{" "}
                    This includes setup state, connection status, timestamps, error codes, and the latest scan/report status.
                  </span>
                </label>
                <label className="flex items-start gap-3 rounded-md border border-[#303137] bg-[#0f1012] p-3">
                  <input
                    type="checkbox"
                    checked={operatorAccessConsent}
                    onChange={(event) => setOperatorAccessConsent(event.target.checked)}
                    className="mt-1"
                  />
                  <span className="text-sm leading-6 text-zinc-300">
                    <span className="font-semibold text-white">Allow support to inspect this location for 72 hours.</span>{" "}
                    This permission is recorded and expires automatically. It does not allow website or listing changes.
                  </span>
                </label>
              </div>

              <div className="mt-4 rounded-md border border-rose-500/15 bg-rose-500/5 p-3 text-xs leading-5 text-rose-100">
                Never send a password, sign-in code, payment number, or private access key. Do not paste an API key here either. The diagnostic summary never includes these items or website page content.
              </div>

              <button
                type="button"
                disabled={supportBusy}
                onClick={() => void createSupportRequest()}
                className="mt-4 rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2.5 text-sm font-semibold text-zinc-100 disabled:opacity-50"
              >
                {supportBusy ? "Sending request..." : "Send support request"}
              </button>
              <p className="mt-3 text-xs leading-5 text-zinc-500">
                If this form is unavailable, email{" "}
                <a className="text-accent-300 underline underline-offset-4" href="mailto:support@verixlabs.com?subject=InsightOS%20help">
                  support@verixlabs.com
                </a>
                . Include the reference number if one was already created.
              </p>
            </div>

            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                Your requests
              </p>
              <h3 className="mt-1.5 text-lg font-semibold text-white">See what happens next</h3>
              {supportRequests.length === 0 ? (
                <div className="mt-4 rounded-md border border-[#303137] bg-[#0f1012] p-4 text-sm leading-6 text-zinc-400">
                  No support requests yet. New requests receive a reference number and visible response target.
                </div>
              ) : (
                <div className="mt-4 space-y-3">
                  {supportRequests.slice(0, 8).map((item) => (
                    <article key={item.id} className="rounded-md border border-[#303137] bg-[#0f1012] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">{item.reference_code}</p>
                          <p className="mt-1 font-semibold text-white">{item.status_label}</p>
                        </div>
                        <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                          item.status === "resolved"
                            ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                            : item.status === "escalated"
                              ? "border-amber-500/25 bg-amber-500/10 text-amber-100"
                              : "border-sky-500/25 bg-sky-500/10 text-sky-100"
                        }`}>
                          {item.priority === "standard" ? "Standard support" : "Priority support"}
                        </span>
                      </div>
                      <p className="mt-3 line-clamp-3 text-sm leading-6 text-zinc-300">{item.customer_summary}</p>
                      <div className="mt-3 space-y-1 border-t border-[#303137] pt-3 text-xs text-zinc-500">
                        <p>{item.response_expectation} · Target: {formatSupportTime(item.response_target_at)}</p>
                        <p>{item.diagnostic_attached ? "Safe system summary attached" : "No diagnostic summary attached"}</p>
                        {item.operator_access_consent ? <p>Temporary inspection permission ends {formatSupportTime(item.operator_access_expires_at)}</p> : null}
                      </div>
                      {!item.escalated_at && !["resolved", "escalated"].includes(item.status) ? (
                        <button
                          type="button"
                          disabled={supportBusy}
                          onClick={() => void escalateSupportRequest(item.id)}
                          className="mt-3 text-sm font-semibold text-amber-200 underline decoration-amber-500/50 underline-offset-4 disabled:opacity-50"
                        >
                          This is blocking my business — request priority review
                        </button>
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#2b2c31] bg-[#141518] p-4">
            <div>
              <p className="text-sm font-semibold text-white">Want a quick look around?</p>
              <p className="mt-1 text-sm text-zinc-400">Take a four-step tour for the workspace type selected above. It remembers your place and can be closed at any time.</p>
            </div>
            <button
              type="button"
              onClick={startQuickTour}
              className="rounded-md border border-accent-500/35 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-white"
            >
              Start quick tour
            </button>
          </div>
        </section>
      </section>
    </AppShell>
  );
}
