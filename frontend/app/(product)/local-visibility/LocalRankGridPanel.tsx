"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { platformApi } from "../../platform/api";

type TrackedKeyword = { id: string; keyword: string };
type Preview = {
  location_name: string;
  keywords: TrackedKeyword[];
  grid_size: number;
  radius_miles: number;
  points_per_phrase: number;
  total_checks: number;
  estimated_credits: number;
  credits_remaining: number;
  credits_after: number;
  connected_account: boolean;
  completion_message: string;
  source_label: string;
  can_start: boolean;
};
type GridPoint = {
  id: string;
  keyword_id: string;
  keyword: string;
  grid_index: number;
  row_index: number;
  column_index: number;
  latitude: number;
  longitude: number;
  status: "queued" | "pending" | "ranked" | "not_found" | "failed" | "sparse";
  rank?: number | null;
  matched_business_name?: string | null;
  captured_at?: string | null;
};
type GridRun = {
  id: string;
  status: "queued" | "submitting" | "pending" | "partial" | "completed" | "failed";
  grid_size: number;
  radius_miles: number;
  center: { latitude: number; longitude: number };
  keywords: TrackedKeyword[];
  total_checks: number;
  completed_checks: number;
  failed_checks: number;
  not_found_checks: number;
  estimated_credits: number;
  source_label: string;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  points: GridPoint[];
};

function markerStyle(point: GridPoint) {
  if (point.status === "sparse") return "border-dashed border-violet-200 bg-violet-950 text-violet-100";
  if (point.status === "failed") return "border-rose-300 bg-rose-600 text-white";
  if (point.status === "queued" || point.status === "pending") {
    return "border-sky-200 bg-sky-600 text-white";
  }
  if (point.status === "not_found" || !point.rank) {
    return "border-zinc-300 bg-zinc-700 text-white";
  }
  if (point.rank <= 3) return "border-emerald-200 bg-emerald-600 text-white";
  if (point.rank <= 10) return "border-lime-200 bg-lime-600 text-zinc-950";
  if (point.rank <= 20) return "border-amber-200 bg-amber-500 text-zinc-950";
  return "border-orange-200 bg-orange-600 text-white";
}

function markerLabel(point: GridPoint) {
  if (point.status === "sparse") return "?";
  if (point.status === "failed") return "!";
  if (point.status === "queued" || point.status === "pending") return "…";
  if (point.status === "not_found" || !point.rank) return "—";
  return String(point.rank);
}

function statusCopy(run: GridRun) {
  if (run.status === "queued" || run.status === "submitting") {
    return "Your checks are waiting to start.";
  }
  if (run.status === "pending") return "Google Maps is still preparing these results.";
  if (run.status === "partial") return "Some spots are ready. Check again for the rest.";
  if (run.status === "failed") return "These checks could not be completed.";
  return "This area check is complete.";
}

function formatRunDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Saved check"
    : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function LocalRankGridPanel({ campaignId }: { campaignId: string }) {
  const [keywords, setKeywords] = useState<TrackedKeyword[]>([]);
  const [selectedKeywordIds, setSelectedKeywordIds] = useState<string[]>([]);
  const [gridSize, setGridSize] = useState(5);
  const [radiusMiles, setRadiusMiles] = useState(5);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [runs, setRuns] = useState<GridRun[]>([]);
  const [activeRun, setActiveRun] = useState<GridRun | null>(null);
  const [activeKeywordId, setActiveKeywordId] = useState("");
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const loadRun = useCallback(async (runId: string) => {
    const run = (await platformApi(`/local/rank-grid/runs/${encodeURIComponent(runId)}`, {
      method: "GET",
    })) as GridRun;
    setActiveRun(run);
    setActiveKeywordId((current) =>
      run.keywords.some((item) => item.id === current) ? current : run.keywords[0]?.id || "",
    );
    return run;
  }, []);

  const loadSaved = useCallback(async () => {
    if (!campaignId) return;
    const response = (await platformApi(
      `/local/rank-grid/runs?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "GET" },
    )) as { items?: GridRun[] };
    const items = Array.isArray(response?.items) ? response.items : [];
    setRuns(items);
    if (items[0]) await loadRun(items[0].id);
    else setActiveRun(null);
  }, [campaignId, loadRun]);

  useEffect(() => {
    if (!campaignId) return;
    setLoading(true);
    setError("");
    setPreview(null);
    setConfirmed(false);
    void Promise.all([
      platformApi(`/rank/keywords?campaign_id=${encodeURIComponent(campaignId)}`, { method: "GET" }),
      loadSaved(),
    ])
      .then(([keywordResponse]) => {
        const items = Array.isArray(keywordResponse?.items)
          ? (keywordResponse.items as TrackedKeyword[])
          : [];
        setKeywords(items);
        setSelectedKeywordIds(items.slice(0, 2).map((item) => item.id));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load area checks."))
      .finally(() => setLoading(false));
  }, [campaignId, loadSaved]);

  const shownPoints = useMemo(
    () => activeRun?.points.filter((point) => point.keyword_id === activeKeywordId) || [],
    [activeKeywordId, activeRun],
  );
  const mapCells = useMemo(() => {
    if (!activeRun) return [];
    const byIndex = new Map(shownPoints.map((point) => [point.grid_index, point]));
    return Array.from({ length: activeRun.grid_size * activeRun.grid_size }, (_, index) =>
      byIndex.get(index) || {
        id: `sparse-${activeKeywordId}-${index}`,
        keyword_id: activeKeywordId,
        keyword: activeRun.keywords.find((item) => item.id === activeKeywordId)?.keyword || "Search",
        grid_index: index,
        row_index: Math.floor(index / activeRun.grid_size),
        column_index: index % activeRun.grid_size,
        latitude: activeRun.center.latitude,
        longitude: activeRun.center.longitude,
        status: "sparse" as const,
      },
    );
  }, [activeKeywordId, activeRun, shownPoints]);
  const isStale = useMemo(() => {
    if (!activeRun) return false;
    const timestamp = new Date(activeRun.completed_at || activeRun.created_at).getTime();
    return Number.isFinite(timestamp) && Date.now() - timestamp > 7 * 86400000;
  }, [activeRun]);

  const mapUrl = useMemo(() => {
    if (!activeRun) return "";
    const { latitude, longitude } = activeRun.center;
    const latSpan = Math.max(0.025, activeRun.radius_miles / 55);
    const lonSpan = Math.max(0.03, activeRun.radius_miles / 45);
    const bbox = [longitude - lonSpan, latitude - latSpan, longitude + lonSpan, latitude + latSpan].join(",");
    return `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik`;
  }, [activeRun]);

  function toggleKeyword(keywordId: string) {
    setPreview(null);
    setConfirmed(false);
    setSelectedKeywordIds((current) =>
      current.includes(keywordId)
        ? current.filter((item) => item !== keywordId)
        : current.length < 3
          ? [...current, keywordId]
          : current,
    );
  }

  async function reviewCheck() {
    setWorking(true);
    setError("");
    setConfirmed(false);
    try {
      const result = (await platformApi("/local/rank-grid/preview", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: campaignId,
          keyword_ids: selectedKeywordIds,
          grid_size: gridSize,
          radius_miles: radiusMiles,
        }),
      })) as Preview;
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to review this check.");
    } finally {
      setWorking(false);
    }
  }

  async function startCheck() {
    if (!preview || !confirmed) return;
    setWorking(true);
    setError("");
    try {
      const result = (await platformApi("/local/rank-grid/runs", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: campaignId,
          keyword_ids: selectedKeywordIds,
          grid_size: gridSize,
          radius_miles: radiusMiles,
          idempotency_key: crypto.randomUUID(),
        }),
      })) as { run: GridRun };
      setActiveRun(result.run);
      setActiveKeywordId(result.run.keywords[0]?.id || "");
      setRuns((current) => [result.run, ...current.filter((item) => item.id !== result.run.id)]);
      setPreview(null);
      setConfirmed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start this area check.");
    } finally {
      setWorking(false);
    }
  }

  async function checkResults() {
    if (!activeRun) return;
    setWorking(true);
    setError("");
    try {
      const run = (await platformApi(
        `/local/rank-grid/runs/${encodeURIComponent(activeRun.id)}/refresh`,
        { method: "POST" },
      )) as GridRun;
      setActiveRun(run);
      setRuns((current) => current.map((item) => (item.id === run.id ? run : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check the latest results.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Nearby search map</p>
          <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
            See where customers can find you
          </h2>
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-zinc-300">
            Check the same Google Maps search from spots around this location. Each numbered dot is where the business appeared from that spot.
          </p>
        </div>
        {runs.length > 0 ? (
          <label className="text-xs font-medium text-zinc-400">
            Previous checks
            <select
              value={activeRun?.id || ""}
              onChange={(event) => void loadRun(event.target.value)}
              className="mt-1 block min-w-56 rounded-md border border-[#34353b] bg-[#101114] px-3 py-2 text-sm text-zinc-100"
            >
              {runs.map((run) => (
                <option key={run.id} value={run.id}>{formatRunDate(run.created_at)} · {run.grid_size}×{run.grid_size}</option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      {error ? <div className="mt-4 rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</div> : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-4">
          <div className="rounded-md border border-[#26272c] bg-[#101114] p-4">
            <p className="text-sm font-semibold text-white">1. Choose what customers search</p>
            {loading ? <p className="mt-3 text-sm text-zinc-400">Loading tracked searches…</p> : null}
            {!loading && keywords.length === 0 ? (
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                Track at least one customer search on the Search Rankings page first.
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {keywords.slice(0, 12).map((keyword) => (
                  <label key={keyword.id} className="flex items-center gap-2 text-sm text-zinc-200">
                    <input
                      type="checkbox"
                      checked={selectedKeywordIds.includes(keyword.id)}
                      onChange={() => toggleKeyword(keyword.id)}
                      disabled={!selectedKeywordIds.includes(keyword.id) && selectedKeywordIds.length >= 3}
                      className="accent-orange-500"
                    />
                    {keyword.keyword}
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-md border border-[#26272c] bg-[#101114] p-4">
            <p className="text-sm font-semibold text-white">2. Choose the area</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="text-xs text-zinc-400">
                Number of map spots
                <select
                  value={gridSize}
                  onChange={(event) => { setGridSize(Number(event.target.value)); setPreview(null); setConfirmed(false); }}
                  className="mt-1 w-full rounded-md border border-[#34353b] bg-[#141518] px-3 py-2 text-sm text-zinc-100"
                >
                  <option value={3}>3 × 3 · 9 spots</option>
                  <option value={5}>5 × 5 · 25 spots</option>
                  <option value={7}>7 × 7 · 49 spots</option>
                </select>
              </label>
              <label className="text-xs text-zinc-400">
                Distance from business
                <select
                  value={radiusMiles}
                  onChange={(event) => { setRadiusMiles(Number(event.target.value)); setPreview(null); setConfirmed(false); }}
                  className="mt-1 w-full rounded-md border border-[#34353b] bg-[#141518] px-3 py-2 text-sm text-zinc-100"
                >
                  {[2, 3, 5, 10, 15, 20, 25].map((miles) => <option key={miles} value={miles}>{miles} miles</option>)}
                </select>
              </label>
            </div>
            <button
              onClick={() => void reviewCheck()}
              disabled={working || selectedKeywordIds.length === 0}
              className="mt-4 w-full rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {working ? "Please wait…" : "Review this check"}
            </button>
          </div>

          {preview ? (
            <div className="rounded-md border border-amber-500/25 bg-amber-500/5 p-4">
              <p className="text-sm font-semibold text-white">3. Confirm before starting</p>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-4"><dt className="text-zinc-400">Search phrases</dt><dd className="text-zinc-100">{preview.keywords.length}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-zinc-400">Map spots per phrase</dt><dd className="text-zinc-100">{preview.points_per_phrase}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-zinc-400">Total checks</dt><dd className="text-zinc-100">{preview.total_checks}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-zinc-400">Insight Credits</dt><dd className="font-semibold text-amber-100">{preview.estimated_credits}</dd></div>
                {!preview.connected_account ? <div className="flex justify-between gap-4"><dt className="text-zinc-400">Credits available now</dt><dd className="text-zinc-100">{preview.credits_remaining}</dd></div> : null}
                {!preview.connected_account ? <div className="flex justify-between gap-4"><dt className="text-zinc-400">Credits left afterward</dt><dd className="text-zinc-100">{preview.credits_after}</dd></div> : <div className="flex justify-between gap-4"><dt className="text-zinc-400">Usage</dt><dd className="text-zinc-100">Connected account · 0 credits</dd></div>}
              </dl>
              <p className="mt-3 text-xs leading-5 text-zinc-400">{preview.completion_message}</p>
              <label className="mt-3 flex items-start gap-2 text-sm leading-5 text-zinc-200">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-orange-500" />
                I approve {preview.total_checks} Google Maps checks{preview.estimated_credits ? ` using ${preview.estimated_credits} Insight Credits` : " through my connected account"}.
              </label>
              <button
                onClick={() => void startCheck()}
                disabled={!confirmed || !preview.can_start || working}
                className="mt-4 w-full rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                Start area check
              </button>
            </div>
          ) : null}
        </div>

        <div className="min-w-0">
          {!activeRun ? (
            <div className="grid min-h-[520px] place-items-center rounded-md border border-dashed border-[#34353b] bg-[#101114] p-8 text-center">
              <div className="max-w-sm">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-accent-500/30 bg-accent-500/10 text-xl text-orange-200">⌖</div>
                <h3 className="mt-4 text-base font-semibold text-white">No area check yet</h3>
                <p className="mt-2 text-sm leading-6 text-zinc-400">Choose one or two useful customer searches, review the exact number of checks, then start.</p>
              </div>
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border border-[#26272c] bg-[#101114]">
              <div className="flex flex-col gap-3 border-b border-[#26272c] p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-white">{statusCopy(activeRun)}</p>
                  <p className="mt-1 text-xs text-zinc-400">{activeRun.completed_checks} of {activeRun.total_checks} spots finished · {formatRunDate(activeRun.created_at)}{isStale ? " · Saved result is more than 7 days old" : ""}</p>
                </div>
                <button
                  onClick={() => void checkResults()}
                  disabled={working || activeRun.status === "completed" || activeRun.status === "failed"}
                  className="rounded-md border border-[#34353b] bg-[#17181b] px-3 py-2 text-sm text-zinc-200 disabled:opacity-40"
                >
                  {working ? "Checking…" : "Check finished results"}
                </button>
              </div>
              <div className="flex flex-wrap gap-2 border-b border-[#26272c] p-3">
                {activeRun.keywords.map((keyword) => (
                  <button
                    key={keyword.id}
                    onClick={() => setActiveKeywordId(keyword.id)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${activeKeywordId === keyword.id ? "border-orange-500/40 bg-orange-500/15 text-orange-100" : "border-[#34353b] bg-[#141518] text-zinc-400"}`}
                  >
                    {keyword.keyword}
                  </button>
                ))}
              </div>
              <div className="relative h-[430px] overflow-hidden bg-[#0c0d0f]">
                {mapUrl ? <iframe src={mapUrl} title="Reference map under local search results" className="h-full w-full border-0 opacity-70" loading="lazy" /> : null}
                <div
                  className="pointer-events-none absolute inset-[9%] grid place-items-center"
                  style={{ gridTemplateColumns: `repeat(${activeRun.grid_size}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${activeRun.grid_size}, minmax(0, 1fr))` }}
                >
                  {mapCells.map((point) => (
                    <div
                      key={point.id}
                      title={`${point.keyword}: ${point.rank ? `position ${point.rank}` : point.status.replace("_", " ")}`}
                      className={`grid h-9 w-9 place-items-center rounded-full border-2 text-xs font-bold shadow-[0_3px_12px_rgba(0,0,0,0.75)] ${markerStyle(point)}`}
                      style={{ gridRow: point.row_index + 1, gridColumn: point.column_index + 1 }}
                    >
                      {markerLabel(point)}
                    </div>
                  ))}
                </div>
              </div>
              <div className="border-t border-[#26272c] p-4">
                <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-300">
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-emerald-600" />1–3</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-lime-600" />4–10</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />11–20</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-orange-600" />21+</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-zinc-700" />Not found</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-sky-600" />Still checking</span>
                  <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full border border-dashed border-violet-200 bg-violet-950" />No point returned</span>
                  {isStale ? <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-100">Older saved result</span> : null}
                </div>
                <p className="mt-3 text-xs leading-5 text-zinc-500">Search positions come from Google Maps results. The street map underneath is only a geographic reference.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
