"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ActionDrawer,
  AppShell,
  ChartCard,
  InsightCard,
  KpiCard,
  type NavItem,
  type TrustSignal,
} from "../components";

const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", active: true },
  { href: "/locations", label: "Locations" },
  { href: "/rankings", label: "Rankings" },
  { href: "/local-visibility", label: "Local Visibility" },
  { href: "/site-health", label: "Site Health", badge: "3" },
  { href: "/competitors", label: "Competitors" },
  { href: "/opportunities", label: "Opportunities", badge: "5" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

const trustSignals: TrustSignal[] = [
  { label: "Freshness", value: "Updated 12 min ago", tone: "info" },
  { label: "Providers", value: "4 connected", tone: "success" },
  { label: "Crawl sync", value: "Healthy", tone: "success" },
  { label: "Rank sync", value: "Refresh running", tone: "warning" },
];

const visibilityTrend = [
  { label: "Mon", visibility: 58, baseline: 54 },
  { label: "Tue", visibility: 60, baseline: 55 },
  { label: "Wed", visibility: 63, baseline: 56 },
  { label: "Thu", visibility: 65, baseline: 57 },
  { label: "Fri", visibility: 67, baseline: 58 },
  { label: "Sat", visibility: 69, baseline: 59 },
  { label: "Sun", visibility: 72, baseline: 60 },
];

const rankingTrend = [
  { label: "Mon", momentum: 41, benchmark: 46 },
  { label: "Tue", momentum: 44, benchmark: 45 },
  { label: "Wed", momentum: 49, benchmark: 45 },
  { label: "Thu", momentum: 53, benchmark: 44 },
  { label: "Fri", momentum: 56, benchmark: 44 },
  { label: "Sat", momentum: 59, benchmark: 43 },
  { label: "Sun", momentum: 62, benchmark: 43 },
];

const recentActivity = [
  {
    title: "Crawl completed",
    time: "12 minutes ago",
    detail: "118 pages processed and 3 high-priority title issues flagged.",
  },
  {
    title: "Rankings refreshed",
    time: "38 minutes ago",
    detail: "Two high-intent service keywords moved into the top 3.",
  },
  {
    title: "Report generated",
    time: "Yesterday",
    detail: "Monthly executive summary sent to the owner and marketing lead.",
  },
  {
    title: "Optimization executed",
    time: "2 days ago",
    detail: "Internal links were updated on 4 service pages with supporting anchors.",
  },
];

function SectionHeading({
  eyebrow,
  title,
  summary,
}: {
  eyebrow: string;
  title: string;
  summary: string;
}) {
  return (
    <div className="mb-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200/80">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
        {title}
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{summary}</p>
    </div>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ color?: string; value?: number; name?: string }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/95 px-4 py-3 shadow-[0_18px_45px_rgba(15,23,42,0.42)]">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </p>
      <div className="mt-2 space-y-1.5">
        {payload.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2 text-sm text-slate-200">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span>{entry.name}</span>
            <span className="ml-auto font-medium text-white">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function VisibilityTrendChart() {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={visibilityTrend}>
          <defs>
            <linearGradient id="visibilityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#818cf8" stopOpacity={0.34} />
              <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#94a3b8", fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            width={36}
          />
          <Tooltip content={<TrendTooltip />} />
          <Area
            type="monotone"
            dataKey="visibility"
            stroke="#818cf8"
            strokeWidth={3}
            fill="url(#visibilityFill)"
            name="Visibility"
          />
          <Line
            type="monotone"
            dataKey="baseline"
            stroke="#38bdf8"
            strokeWidth={2}
            strokeDasharray="4 5"
            dot={false}
            name="Baseline"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function RankingTrendChart() {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rankingTrend}>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#94a3b8", fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            width={36}
          />
          <Tooltip content={<TrendTooltip />} />
          <Line
            type="monotone"
            dataKey="momentum"
            stroke="#a78bfa"
            strokeWidth={3}
            dot={{ r: 0 }}
            activeDot={{ r: 5, fill: "#a78bfa", stroke: "#070b16", strokeWidth: 2 }}
            name="Momentum"
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#22c55e"
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 6"
            name="Benchmark"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function MiniSpark({
  bars,
  color,
}: {
  bars: number[];
  color: string;
}) {
  return (
    <div className="flex h-16 items-end gap-1">
      {bars.map((bar, index) => (
        <span
          key={`${color}-${index}`}
          className="w-2 rounded-full"
          style={{
            height: `${bar}%`,
            background: color,
            opacity: 0.92,
            boxShadow: `0 0 18px ${color}33`,
          }}
        />
      ))}
    </div>
  );
}

function TimelineCard() {
  return (
    <section className="rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] p-5 shadow-[0_18px_55px_rgba(15,23,42,0.36)] md:p-6">
      <SectionHeading
        eyebrow="Recent activity"
        title="Execution timeline"
        summary="This feed keeps operators and owners aligned on what the system changed, checked, and completed."
      />
      <div className="space-y-4">
        {recentActivity.map((item, index) => (
          <div key={item.title} className="flex gap-4">
            <div className="flex flex-col items-center">
              <div className="mt-1 h-3.5 w-3.5 rounded-full border border-indigo-300/30 bg-indigo-400 shadow-[0_0_18px_rgba(129,140,248,0.55)]" />
              {index < recentActivity.length - 1 ? (
                <div className="mt-2 h-full min-h-10 w-px bg-white/10" />
              ) : null}
            </div>
            <div className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-sm font-semibold text-white">{item.title}</h3>
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">
                  {item.time}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-300">{item.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DashboardPage() {
  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel="Austin Roofing Co. / Downtown"
      dateRangeLabel="Last 30 days"
    >
      <section className="space-y-6">
        <div className="max-w-4xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200/80">
            Campaign command center
          </p>
          <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-white md:text-5xl">
            Local SEO performance, interpreted.
          </h1>
          <p className="mt-3 text-base leading-7 text-slate-300">
            Visibility is improving, rankings are recovering on priority service
            pages, and the clearest next gain is still technical link equity.
          </p>
        </div>

        <div className="grid gap-5 xl:grid-cols-4">
          <KpiCard
            label="SEO Health Score"
            value="81"
            changeLabel="+6"
            summary="Technical health improved after last week&apos;s page title and internal link updates."
            visual={<MiniSpark bars={[30, 46, 42, 58, 61, 73, 82]} color="#22c55e" />}
            tone="highlight"
          />
          <KpiCard
            label="Local Visibility Score"
            value="72"
            changeLabel="+8%"
            summary="Visibility expanded after review velocity improved across your highest-converting grid cells."
            visual={<MiniSpark bars={[32, 38, 41, 49, 55, 62, 74]} color="#818cf8" />}
          />
          <KpiCard
            label="Ranking Momentum"
            value="+11"
            changeLabel="Upward"
            summary="Two service pages recovered rankings after internal link consolidation and refreshed metadata."
            visual={<MiniSpark bars={[18, 30, 39, 44, 57, 66, 79]} color="#a78bfa" />}
          />
          <KpiCard
            label="Competitor Pressure"
            value="Moderate"
            changeLabel="-2 rivals"
            summary="One core competitor lost downtown map-pack coverage, but service-area gaps remain on the west side."
            visual={<MiniSpark bars={[74, 68, 63, 58, 49, 42, 36]} color="#38bdf8" />}
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <ChartCard
            eyebrow="Trend"
            title="Local visibility trend"
            summary="The strongest gains came after review velocity improved and business-profile engagement stabilized in high-value cells."
            chart={<VisibilityTrendChart />}
            footer={
              <p className="text-sm leading-6 text-slate-300">
                What changed: visibility climbed steadily across the week. Why it
                matters: stronger map-pack presence lifts inbound demand before site
                visits even begin.
              </p>
            }
          />
          <ChartCard
            eyebrow="Trend"
            title="Ranking momentum"
            summary="Priority commercial terms are recovering faster than the market benchmark, which suggests the recent content and link work is holding."
            chart={<RankingTrendChart />}
            footer={
              <p className="text-sm leading-6 text-slate-300">
                What to do next: reinforce the recovering service pages instead of
                spreading effort across low-intent terms.
              </p>
            }
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-3">
          <InsightCard
            insight={{
              title: "Visibility increased near downtown.",
              body: "Review velocity growth and improved business-profile completeness are lifting local pack coverage where conversion intent is strongest.",
              tone: "success",
              action: { label: "Open local visibility" },
            }}
          />
          <InsightCard
            insight={{
              title: "Two service pages recovered rankings.",
              body: "Internal link updates improved crawl depth and relevance signals on high-intent roofing service pages.",
              tone: "info",
              action: { label: "Inspect rankings" },
            }}
          />
          <InsightCard
            insight={{
              title: "Three service pages still need title fixes.",
              body: "Metadata remains incomplete on money pages, which is limiting click-through rate and weakening page clarity.",
              tone: "danger",
              action: { label: "Review site health" },
            }}
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <section className="rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] p-5 shadow-[0_18px_55px_rgba(15,23,42,0.36)] md:p-6">
            <SectionHeading
              eyebrow="Top risks"
              title="Watch these constraints"
              summary="The campaign is recovering, but a few weak points can still slow local growth if they are left unresolved."
            />
            <div className="grid gap-4 md:grid-cols-2">
              <InsightCard
                insight={{
                  title: "Review velocity slowed in the last two weeks.",
                  body: "Recent gains are strong, but the pace of new reviews is flattening in the locations that influence your best-performing zones.",
                  tone: "warning",
                  action: { label: "Open review plan" },
                }}
              />
              <InsightCard
                insight={{
                  title: "Competitor coverage remains stronger west of downtown.",
                  body: "A nearby rival still outranks you for high-intent repair terms in a service area where you have weak landing-page support.",
                  tone: "warning",
                  action: { label: "Compare competitors" },
                }}
              />
            </div>
          </section>

          <ActionDrawer
            title="Strengthen internal links to service pages"
            summary="Internal linking remains the clearest technical lever for ranking improvement and reinforces the pages already starting to recover."
            evidence={[
              "Dropped pages have weaker internal link depth than the current winners.",
              "High-intent keywords recently recovered after content and metadata updates.",
              "Competitor wins still cluster around stronger page-to-page relevance signals.",
            ]}
          />
        </div>

        <TimelineCard />
      </section>
    </AppShell>
  );
}
