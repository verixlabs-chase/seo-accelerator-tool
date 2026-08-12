"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  DetailsDisclosure,
  EmptyState,
  KpiCard,
  LoadingCard,
  OwnerDecisionPanel,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = { id: string; name?: string; domain?: string };

type Competitor = {
  id: string;
  campaign_id: string;
  domain: string;
  label?: string | null;
  discovery_source: "manual" | "search_overlap" | string;
  review_status: "suggested" | "confirmed" | string;
  overlap_count?: number | null;
  average_position?: number | null;
  estimated_traffic?: number | null;
  last_observed_at?: string | null;
  created_at: string;
};

type GapItem = {
  id: string;
  suggestion_id: string;
  competitor_id: string;
  competitor_domain: string;
  competitor_label?: string | null;
  keyword: string;
  gap_type: "not_showing" | "competitor_ahead";
  competitor_position: number;
  previous_competitor_position?: number | null;
  competitor_position_change?: number | null;
  movement_direction?: "up" | "down" | "steady" | "unavailable";
  movement_label?: string | null;
  movement_alert?: boolean;
  previous_source_updated_at?: string | null;
  competitor_url?: string | null;
  owner_position?: number | null;
  owner_url?: string | null;
  page_status: "existing" | "needs_page" | "review" | string;
  page_reason?: string | null;
  search_volume?: number | null;
  matched_service_name?: string | null;
  matched_service_area_name?: string | null;
  opportunity_score: number;
  next_step: string;
  source_updated_at?: string | null;
};

type ResearchResult = {
  run: {
    id: string;
    status: string;
    location_name: string;
    completed_at?: string | null;
    previous_run_id?: string | null;
    previous_completed_at?: string | null;
  } | null;
  summary: {
    confirmed_competitors: number;
    suggested_competitors: number;
    competitors_with_gaps: number;
    exact_gaps: number;
    not_showing: number;
    competitor_ahead: number;
    movement_alerts: number;
  };
  items: GapItem[];
};

type CreditSummary = {
  credits: { remaining: number; blocked: boolean };
  action_prices: Array<{
    code: string;
    credits: number;
    price_type: "up_to" | "per_item" | "fixed_ceiling";
  }>;
};

const EMPTY_RESEARCH: ResearchResult = {
  run: null,
  summary: {
    confirmed_competitors: 0,
    suggested_competitors: 0,
    competitors_with_gaps: 0,
    exact_gaps: 0,
    not_showing: 0,
    competitor_ahead: 0,
    movement_alerts: 0,
  },
  items: [],
};

function formatPosition(value?: number | null) {
  return value == null ? "Not showing" : `#${Math.round(value)}`;
}

function formatDate(value?: string | null) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not checked yet";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export default function CompetitorsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [research, setResearch] = useState<ResearchResult>(EMPTY_RESEARCH);
  const [creditSummary, setCreditSummary] = useState<CreditSummary | null>(null);
  const [newDomain, setNewDomain] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadCampaigns = useCallback(async () => {
    const response = await platformApi("/campaigns", { method: "GET" });
    const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
    setCampaigns(items);
    setSelectedCampaignId((current) =>
      current && items.some((item) => item.id === current) ? current : items[0]?.id || "",
    );
    return items;
  }, [setSelectedCampaignId]);

  const loadLocation = useCallback(async (campaignId: string) => {
    if (!campaignId) return;
    const [competitorResponse, researchResponse] = await Promise.all([
      platformApi(`/competitors?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      platformApi(`/competitors/research?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
    ]);
    setCompetitors(
      Array.isArray(competitorResponse?.items) ? (competitorResponse.items as Competitor[]) : [],
    );
    setResearch((researchResponse as ResearchResult) || EMPTY_RESEARCH);
  }, []);

  const loadCredits = useCallback(async () => {
    try {
      const response = (await platformApi("/usage/credits", { method: "GET" })) as CreditSummary;
      setCreditSummary(response);
    } catch {
      setCreditSummary(null);
    }
  }, []);

  async function runAction(name: string, action: () => Promise<void>) {
    setBusyAction(name);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusyAction("");
    }
  }

  async function findCompetitors() {
    if (!selectedCampaignId) return;
    await runAction("discover", async () => {
      const response = await platformApi("/competitors/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, limit: 12 }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(
        response?.suggestions_found
          ? `Found ${response.suggestions_found} possible competitors. Confirm only the businesses customers truly compare with you.`
          : "No new competitors were found from the available search overlap.",
      );
    });
  }

  async function confirmCompetitor(item: Competitor) {
    if (!selectedCampaignId) return;
    await runAction(`confirm:${item.id}`, async () => {
      await platformApi("/competitors", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          domain: item.domain,
          label: item.label || null,
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(`${item.label || item.domain} is now included in competitor research.`);
    });
  }

  async function dismissCompetitor(item: Competitor) {
    if (!selectedCampaignId) return;
    await runAction(`dismiss:${item.id}`, async () => {
      await platformApi("/competitors/review", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          competitor_id: item.id,
          decision: "dismissed",
        }),
      });
      await loadLocation(selectedCampaignId);
      setNotice(`${item.label || item.domain} was removed from this location’s suggestions.`);
    });
  }

  async function addCompetitor() {
    if (!selectedCampaignId || !newDomain.trim()) return;
    await runAction("add", async () => {
      await platformApi("/competitors", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          domain: newDomain.trim(),
          label: newLabel.trim() || null,
        }),
      });
      setNewDomain("");
      setNewLabel("");
      await loadLocation(selectedCampaignId);
      setNotice("Competitor added. Refresh the search comparison to find exact gaps.");
    });
  }

  async function trackGap(item: GapItem) {
    if (!selectedCampaignId) return;
    await runAction(`track:${item.id}`, async () => {
      const response = await platformApi("/keyword-research/track", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [item.suggestion_id],
        }),
      });
      setNotice(
        response?.created_count
          ? `“${item.keyword}” is now in Search Rankings.`
          : `“${item.keyword}” was already in Search Rankings.`,
      );
    });
  }

  async function addGapToNextSteps(item: GapItem) {
    if (!selectedCampaignId) return;
    await runAction(`action:${item.id}`, async () => {
      const response = await platformApi("/keyword-research/create-action", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          suggestion_ids: [item.suggestion_id],
        }),
      });
      setNotice(response?.message || `“${item.keyword}” is ready to review in Next Steps.`);
    });
  }

  async function refreshComparison() {
    if (!selectedCampaignId) return;
    await runAction("refresh", async () => {
      await platformApi("/keyword-research/discover", {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId, max_suggestions: 75 }),
      });
      await loadLocation(selectedCampaignId);
      setNotice("The comparison now uses the latest searches available for this location.");
    });
  }

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        const [items] = await Promise.all([loadCampaigns(), loadCredits()]);
        if (items[0]?.id) await loadLocation(items[0].id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load competitor research.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [loadCampaigns, loadCredits, loadLocation]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setError("");
    setNotice("");
    void loadLocation(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Unable to change locations.");
    });
  }, [selectedCampaignId, loading, loadLocation]);

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId);
  const confirmed = competitors.filter((item) => item.review_status === "confirmed");
  const suggested = competitors.filter((item) => item.review_status === "suggested");
  const topGap = research.items[0];
  const discoveryCreditPrice = creditSummary?.action_prices.find(
    (item) => item.code === "competitor_discovery",
  );
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals: TrustSignal[] = [
    {
      label: "Location",
      value: selectedCampaign?.name || "Choose a location",
      tone: selectedCampaign ? "success" : "warning",
    },
    {
      label: "Competitors confirmed",
      value: String(confirmed.length),
      tone: confirmed.length ? "success" : "warning",
    },
    {
      label: "Search comparison",
      value: research.run ? formatDate(research.run.completed_at) : "Not run",
      tone: research.run ? "success" : "warning",
    },
  ];

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed business"} / ${selectedCampaign.domain || "No website"}`
          : "No business selected"
      }
      dateRangeLabel="Latest saved comparison"
      topBarActions={
        <button
          onClick={() => router.push("/keyword-research")}
          className="rounded-md border border-[#2f3035] px-3 py-1.5 text-sm text-zinc-200"
        >
          Find searches
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Competitors"
          title="See who is winning the searches you want"
          summary="Find the businesses customers see beside yours, then compare the exact searches and pages where they are ahead."
        />

        {discoveryCreditPrice ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[#26272c] py-3 text-sm">
            <p className="text-zinc-300">
              Finding competitors uses {discoveryCreditPrice.credits} Insight Credits for this location.
            </p>
            <p className="font-semibold text-white">
              {creditSummary?.credits.remaining.toLocaleString()} available
            </p>
          </div>
        ) : null}

        <TruthNotice title="Choose competitors customers would actually hire.">
          Search overlap is only a starting clue. Confirm local businesses that sell the same work
          in the same area before using their pages to plan improvements.
        </TruthNotice>

        {loading ? (
          <LoadingCard title="Loading competitor research" summary="Checking this location’s saved comparisons." />
        ) : null}
        {error ? (
          <div className="rounded-md border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-100">{error}</div>
        ) : null}
        {notice ? (
          <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 p-4 text-sm text-emerald-100">{notice}</div>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a business first"
            summary="Competitor research needs a website and location before it can compare search results."
            actionLabel="Go to setup"
            onAction={() => router.push("/dashboard")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            <OwnerDecisionPanel
              title={
                topGap
                  ? `${topGap.competitor_label || topGap.competitor_domain} is ahead for “${topGap.keyword}”`
                  : suggested.length
                    ? `Review ${suggested.length} possible competitor${suggested.length === 1 ? "" : "s"}`
                    : confirmed.length
                      ? "Refresh the searches to build a current comparison"
                      : "Find the businesses customers see beside yours"
              }
              summary={
                topGap
                  ? `They appear around ${formatPosition(topGap.competitor_position)}. Your website is ${topGap.owner_position == null ? "not showing in the saved results" : `around ${formatPosition(topGap.owner_position)}`}.`
                  : suggested.length
                    ? "Search overlap can include directories and national websites. Confirm only businesses that truly compete for the same customers."
                    : "InsightOS will suggest likely competitors from real search overlap. You decide which ones belong in the comparison."
              }
              nextStep={
                topGap
                  ? topGap.next_step
                  : suggested.length
                    ? "Confirm the closest local competitors below."
                    : confirmed.length
                      ? "Run a fresh search comparison."
                      : "Run the first competitor search."
              }
              actionLabel={
                suggested.length ? "Review suggestions" : confirmed.length ? "Refresh comparison" : "Find competitors"
              }
              onAction={() => {
                if (suggested.length) {
                  document.getElementById("competitor-suggestions")?.scrollIntoView({ behavior: "smooth" });
                } else if (confirmed.length) {
                  void refreshComparison();
                } else {
                  void findCompetitors();
                }
              }}
              tone={topGap ? "warning" : "neutral"}
            />

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="Real competitors confirmed"
                value={String(research.summary.confirmed_competitors)}
                summary="Businesses included in this location’s comparison."
              />
              <KpiCard
                label="Searches where they lead"
                value={String(research.summary.exact_gaps)}
                summary="Exact, relevant searches backed by a saved result."
                tone={research.summary.exact_gaps ? "highlight" : undefined}
              />
              <KpiCard
                label="Searches where you are absent"
                value={String(research.summary.not_showing)}
                summary="Confirmed competitor searches where your website was not found."
              />
              <KpiCard
                label="Competitor movement alerts"
                value={String(research.summary.movement_alerts)}
                summary="Competitors that moved by at least three places since the earlier matching check."
                tone={research.summary.movement_alerts ? "highlight" : undefined}
              />
            </div>

            <section id="competitor-suggestions" className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Who customers compare</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Choose your real competitors</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Shared searches are a clue, not a final decision. Confirm local businesses that sell the same work in the same area.
                  </p>
                </div>
                <button
                  onClick={() => void findCompetitors()}
                  disabled={busyAction !== "" || creditSummary?.credits.blocked}
                  className="rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {busyAction === "discover" ? "Finding competitors…" : "Find competitors"}
                </button>
              </div>

              {suggested.length ? (
                <div className="mt-5 grid gap-3 lg:grid-cols-2">
                  {suggested.map((item) => (
                    <article key={item.id} className="rounded-md border border-[#2b2c31] bg-[#121315] p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="font-semibold text-white">{item.label || item.domain}</h3>
                          <p className="mt-1 text-sm text-zinc-400">{item.domain}</p>
                        </div>
                        <span className="rounded-full bg-sky-500/10 px-2.5 py-1 text-xs text-sky-200">
                          {item.overlap_count || 0} shared searches
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-zinc-300">
                        This website repeatedly appears for searches also tied to your website. Confirm it only if it serves the same customers.
                      </p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          onClick={() => void confirmCompetitor(item)}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-100 disabled:opacity-50"
                        >
                          {busyAction === `confirm:${item.id}` ? "Confirming…" : "Yes, this is a competitor"}
                        </button>
                        <button
                          onClick={() => void dismissCompetitor(item)}
                          disabled={busyAction !== ""}
                          className="rounded-md border border-[#303137] px-3 py-2 text-sm text-zinc-300 disabled:opacity-50"
                        >
                          {busyAction === `dismiss:${item.id}` ? "Removing…" : "Not a competitor"}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="mt-5 text-sm text-zinc-400">
                  No unreviewed suggestions. Run the check when you want to look for more.
                </p>
              )}

              {confirmed.length ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  {confirmed.map((item) => (
                    <span key={item.id} className="rounded-full border border-[#303137] px-3 py-1.5 text-sm text-zinc-200">
                      {item.label || item.domain}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="border-t border-[#26272c] pt-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Where to catch up</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-white">Exact searches and competing pages</h2>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
                    Every item names the search, both saved positions, and the competing page when one was available. No made-up gap score is used.
                  </p>
                </div>
                <button
                  onClick={() => void refreshComparison()}
                  disabled={busyAction !== "" || confirmed.length === 0}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "refresh" ? "Refreshing…" : "Refresh comparison"}
                </button>
              </div>

              {research.items.length ? (
                <div className="mt-5 divide-y divide-[#26272c] border-y border-[#26272c]">
                  {research.items.map((item, index) => (
                    <article key={item.id} className="grid gap-4 py-5 lg:grid-cols-[2rem_1.1fr_.8fr_1.2fr]">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-500/15 text-sm font-semibold text-orange-200">
                        {index + 1}
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">{item.keyword}</h3>
                        <p className="mt-1 text-sm text-zinc-400">
                          {[item.matched_service_name, item.matched_service_area_name].filter(Boolean).join(" · ") || "Confirmed relevant search"}
                        </p>
                        {item.search_volume != null ? (
                          <p className="mt-1 text-xs text-zinc-500">About {item.search_volume.toLocaleString()} searches in the saved market data</p>
                        ) : null}
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Your site</p>
                          <p className="mt-1 font-semibold text-white">{formatPosition(item.owner_position)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Competitor</p>
                          <p className="mt-1 font-semibold text-orange-200">{formatPosition(item.competitor_position)}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{item.competitor_label || item.competitor_domain}</p>
                        {item.previous_competitor_position != null && item.movement_label ? (
                          <p
                            className={`mt-1 text-sm font-medium ${
                              item.movement_direction === "up"
                                ? "text-orange-200"
                                : item.movement_direction === "down"
                                  ? "text-emerald-300"
                                  : "text-zinc-400"
                            }`}
                          >
                            {item.movement_label} Earlier: {formatPosition(item.previous_competitor_position)}.
                          </p>
                        ) : null}
                        <p className="mt-1 text-sm leading-6 text-zinc-300">{item.next_step}</p>
                        <p className="mt-1 text-xs leading-5 text-zinc-500">
                          {item.page_status === "existing"
                            ? "A likely page on your website was found."
                            : item.page_status === "needs_page"
                              ? "No saved page clearly covers this customer need yet."
                              : item.page_reason || "The best website page still needs review."}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-3 text-xs">
                          {item.competitor_url ? (
                            <a href={item.competitor_url} target="_blank" rel="noreferrer" className="text-sky-300 hover:text-sky-200">
                              Open their page ↗
                            </a>
                          ) : null}
                          {item.owner_url ? (
                            <a href={item.owner_url} target="_blank" rel="noreferrer" className="text-zinc-300 hover:text-white">
                              Open your page ↗
                            </a>
                          ) : null}
                          <span className="text-zinc-500">Checked {formatDate(item.source_updated_at)}</span>
                          {item.previous_source_updated_at && item.previous_competitor_position != null ? (
                            <span className="text-zinc-500">Earlier check {formatDate(item.previous_source_updated_at)}</span>
                          ) : null}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => void trackGap(item)}
                            disabled={busyAction !== ""}
                            className="rounded-md border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-100 disabled:opacity-50"
                          >
                            {busyAction === `track:${item.id}` ? "Adding…" : "Track this search"}
                          </button>
                          <button
                            onClick={() => void addGapToNextSteps(item)}
                            disabled={busyAction !== ""}
                            className="rounded-md border border-[#34353a] px-3 py-1.5 text-xs font-medium text-zinc-200 disabled:opacity-50"
                          >
                            {busyAction === `action:${item.id}` ? "Adding…" : "Add to Next Steps"}
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="mt-5">
                  <EmptyState
                    title={confirmed.length ? "No exact gaps are ready yet" : "Confirm a competitor first"}
                    summary={
                      confirmed.length
                        ? "Refresh the comparison. InsightOS will only show relevant searches with enough evidence to compare."
                        : "Find or add a real competitor, confirm it, then refresh the comparison."
                    }
                    actionLabel={confirmed.length ? "Refresh comparison" : "Find competitors"}
                    onAction={() => void (confirmed.length ? refreshComparison() : findCompetitors())}
                  />
                </div>
              )}
            </section>

            <DetailsDisclosure label="Add a competitor yourself" summary="Use this when you already know a business customers compare with you.">
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <input
                  value={newDomain}
                  onChange={(event) => setNewDomain(event.target.value)}
                  placeholder="competitor.com"
                  aria-label="Competitor website"
                  className="rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                />
                <input
                  value={newLabel}
                  onChange={(event) => setNewLabel(event.target.value)}
                  placeholder="Business name (optional)"
                  aria-label="Competitor business name"
                  className="rounded-md border border-[#303137] bg-[#0d0e10] px-3 py-2 text-sm text-white outline-none"
                />
                <button
                  onClick={() => void addCompetitor()}
                  disabled={busyAction !== "" || !newDomain.trim()}
                  className="rounded-md border border-[#303137] px-4 py-2 text-sm font-medium text-zinc-100 disabled:opacity-50"
                >
                  {busyAction === "add" ? "Adding…" : "Add competitor"}
                </button>
              </div>
            </DetailsDisclosure>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
