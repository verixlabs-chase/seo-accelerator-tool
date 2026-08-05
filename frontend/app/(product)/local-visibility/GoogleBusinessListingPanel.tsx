"use client";

type AuditItem = {
  field: string;
  label: string;
  status: "complete" | "needs_attention" | "review" | "not_measured";
  message: string;
  action?: string | null;
  primary_metric?: string | null;
  measurement_state: string;
};

export type BusinessListingIntelligence = {
  data_status: "not_connected" | "no_data" | "ready";
  captured_at?: string | null;
  checked_at?: string | null;
  profile?: {
    title?: string;
    websiteUri?: string;
    categories?: { primaryCategory?: { displayName?: string } };
  } | null;
  audit?: {
    score?: number | null;
    needs_attention: number;
    summary: string;
    truth_note: string;
    items: AuditItem[];
  } | null;
  changes?: Array<{ field: string; label: string; message: string }>;
  summary?: {
    total_appearances: number;
    search_appearances: number;
    map_appearances: number;
    website_clicks: number;
    call_clicks: number;
    direction_requests: number;
    bookings: number;
    days_with_data: number;
  } | null;
  points?: Array<{
    date: string;
    total_appearances: number;
    website_clicks?: number | null;
    call_clicks?: number | null;
    direction_requests?: number | null;
  }>;
  search_terms?: Array<{ month: string; keyword: string; impressions: number }>;
};

function formatNumber(value?: number | null) {
  return Number(value || 0).toLocaleString();
}

function formatDate(value?: string | null) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function ActivityChart({ points }: { points: NonNullable<BusinessListingIntelligence["points"]> }) {
  const visible = points.slice(-90);
  if (visible.length < 2 || visible.every((point) => point.total_appearances === 0)) {
    return (
      <div className="grid h-48 place-items-center rounded-md border border-dashed border-[#303137] bg-[#101114] px-6 text-center">
        <p className="max-w-sm text-sm leading-6 text-zinc-400">
          Appearance history will draw here after Google returns enough daily information.
        </p>
      </div>
    );
  }
  const width = 720;
  const height = 180;
  const maxValue = Math.max(...visible.map((point) => point.total_appearances), 1);
  const path = visible
    .map((point, index) => {
      const x = (index / (visible.length - 1)) * width;
      const y = height - (point.total_appearances / maxValue) * (height - 20) - 10;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="rounded-md border border-[#303137] bg-[#101114] p-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full" role="img" aria-label="Daily Google listing appearances">
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line
            key={ratio}
            x1="0"
            x2={width}
            y1={height * ratio}
            y2={height * ratio}
            stroke="#27282d"
            strokeWidth="1"
          />
        ))}
        <path d={path} fill="none" stroke="#ff6a1a" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
        <span>{formatDate(visible[0]?.date)}</span>
        <span className="flex items-center gap-2 text-zinc-300">
          <span className="h-2.5 w-2.5 rounded-full bg-accent-500" /> Daily appearances
        </span>
        <span>{formatDate(visible.at(-1)?.date)}</span>
      </div>
    </div>
  );
}

export function GoogleBusinessListingPanel({
  intelligence,
  onOpenSettings,
}: {
  intelligence: BusinessListingIntelligence | null;
  onOpenSettings: () => void;
}) {
  if (!intelligence || intelligence.data_status === "not_connected") {
    return (
      <section className="rounded-md border border-amber-500/20 bg-[#141518] p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200">
          Google business listing
        </p>
        <h2 className="mt-2 text-xl font-semibold text-white">Connect the listing customers see</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
          Once connected, this page will show whether the listing is complete, what changed,
          how often it appeared, and how many people called, visited the website, or asked for directions.
        </p>
        <button
          onClick={onOpenSettings}
          className="mt-4 rounded-md border border-accent-500/40 bg-accent-500/15 px-4 py-2 text-sm font-semibold text-white"
        >
          Connect Google business listing
        </button>
      </section>
    );
  }

  if (intelligence.data_status === "no_data") {
    return (
      <section className="rounded-md border border-[#303137] bg-[#141518] p-5">
        <h2 className="text-xl font-semibold text-white">The listing is matched and waiting for its first check</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-400">
          Run the first check from Data connections. The saved results will appear here without mixing this location with another one.
        </p>
        <button onClick={onOpenSettings} className="mt-4 rounded-md border border-[#303137] bg-[#17181b] px-4 py-2 text-sm text-white">
          Open data connections
        </button>
      </section>
    );
  }

  const summary = intelligence.summary;
  const audit = intelligence.audit;
  const priorityItems = (audit?.items || []).filter((item) => item.status === "needs_attention");
  const topTerms = [...(intelligence.search_terms || [])]
    .sort((a, b) => b.impressions - a.impressions)
    .slice(0, 8);
  const maxTermValue = Math.max(...topTerms.map((term) => term.impressions), 1);

  return (
    <section className="space-y-4 rounded-md border border-[#303137] bg-[#141518] p-5 shadow-[0_0_30px_rgba(0,0,0,0.35)]">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">
            Google business listing
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            What customers saw and did
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
            These numbers come from the listing matched to this location. The latest check finished {formatDate(intelligence.checked_at || intelligence.captured_at)}.
          </p>
        </div>
        <div className="rounded-md border border-[#303137] bg-[#101114] px-4 py-3 text-right">
          <p className="text-xs text-zinc-500">Listing details filled in</p>
          <p className="mt-1 text-2xl font-semibold text-white">{audit?.score ?? "—"}%</p>
          <p className="mt-1 text-xs text-zinc-400">{audit?.summary}</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Google appearances", summary?.total_appearances, "Search and Maps combined"],
          ["Website visits", summary?.website_clicks, "Clicks from the listing"],
          ["Call clicks", summary?.call_clicks, "Taps on the call button"],
          ["Direction requests", summary?.direction_requests, "People asking for directions"],
          ["Bookings", summary?.bookings, "When booking is supported"],
        ].map(([label, value, note]) => (
          <div key={String(label)} className="border-l-2 border-[#38393f] py-1 pl-4">
            <p className="text-xs text-zinc-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-white">{formatNumber(value as number)}</p>
            <p className="mt-1 text-xs leading-5 text-zinc-500">{note}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <div>
          <div className="mb-3">
            <h3 className="text-base font-semibold text-white">Daily appearances</h3>
            <p className="mt-1 text-sm text-zinc-400">How often this listing appeared in Google Search and Maps.</p>
          </div>
          <ActivityChart points={intelligence.points || []} />
        </div>
        <div className="rounded-md border border-[#303137] bg-[#101114] p-4">
          <h3 className="text-base font-semibold text-white">Fix these listing details first</h3>
          {priorityItems.length === 0 ? (
            <p className="mt-3 text-sm leading-6 text-emerald-100">The main listing details are filled in. Keep them accurate when the business changes.</p>
          ) : (
            <ol className="mt-3 space-y-3">
              {priorityItems.slice(0, 4).map((item, index) => (
                <li key={item.field} className="flex gap-3 border-t border-[#27282d] pt-3 first:border-t-0 first:pt-0">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-accent-500/30 bg-accent-500/10 text-xs font-semibold text-accent-200">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">{item.action}</p>
                    <p className="mt-1 text-xs leading-5 text-zinc-500">Watch: {item.primary_metric}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-4 border-t border-[#27282d] pt-3 text-xs leading-5 text-zinc-500">{audit?.truth_note}</p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-md border border-[#303137] bg-[#101114] p-4">
          <h3 className="text-base font-semibold text-white">Searches that led to this listing</h3>
          <p className="mt-1 text-sm text-zinc-400">The strongest customer searches Google returned for recent months.</p>
          {topTerms.length === 0 ? (
            <p className="mt-4 text-sm text-zinc-500">No customer search terms were returned yet.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {topTerms.map((term) => (
                <div key={`${term.month}-${term.keyword}`}>
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-zinc-200">{term.keyword}</span>
                    <span className="shrink-0 text-zinc-500">{formatNumber(term.impressions)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#26272c]">
                    <div className="h-full rounded-full bg-accent-500" style={{ width: `${Math.max(4, (term.impressions / maxTermValue) * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="rounded-md border border-[#303137] bg-[#101114] p-4">
          <h3 className="text-base font-semibold text-white">What changed on the listing</h3>
          <p className="mt-1 text-sm text-zinc-400">Changes are saved so you can connect later results to the work that actually happened.</p>
          {(intelligence.changes || []).length === 0 ? (
            <p className="mt-4 text-sm leading-6 text-zinc-500">No listing changes have been recorded between saved checks yet.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {(intelligence.changes || []).map((change) => (
                <li key={change.field} className="border-l-2 border-sky-400/40 pl-3 text-sm leading-6 text-zinc-300">
                  {change.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
