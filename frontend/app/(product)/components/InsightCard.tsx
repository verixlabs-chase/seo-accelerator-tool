import type { Insight } from "./types";

const toneClasses = {
  info: "border-sky-400/20 bg-sky-400/8",
  success: "border-emerald-400/20 bg-emerald-400/8",
  warning: "border-amber-400/20 bg-amber-400/8",
  danger: "border-rose-400/20 bg-rose-400/8",
} as const;

type InsightCardProps = {
  insight: Insight;
};

export function InsightCard({ insight }: InsightCardProps) {
  const tone = insight.tone ?? "info";

  return (
    <section className={`rounded-[24px] border p-5 ${toneClasses[tone]}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Insight
          </p>
          <h3 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-white">
            {insight.title}
          </h3>
        </div>
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">
          {tone}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-300">{insight.body}</p>
      {insight.action ? (
        <button className="mt-4 inline-flex items-center rounded-full border border-indigo-400/25 bg-indigo-500/12 px-4 py-2 text-sm font-medium text-indigo-100">
          {insight.action.label}
        </button>
      ) : null}
    </section>
  );
}
