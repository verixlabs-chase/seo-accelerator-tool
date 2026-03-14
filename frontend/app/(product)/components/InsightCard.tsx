import type { Insight } from "./types";

const toneClasses = {
  info: "border-[#26272c] bg-[#141518]",
  success: "border-emerald-500/14 bg-[#101411]",
  warning: "border-amber-500/14 bg-[#15120d]",
  danger: "border-rose-500/14 bg-[#151011]",
} as const;

type InsightCardProps = {
  insight: Insight;
};

export function InsightCard({ insight }: InsightCardProps) {
  const tone = insight.tone ?? "info";

  return (
    <section className={`rounded-md border p-4 ${toneClasses[tone]}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Insight
          </p>
          <h3 className="mt-1.5 text-base font-semibold tracking-[-0.02em] text-white">
            {insight.title}
          </h3>
        </div>
        <span className={`h-2 w-2 shrink-0 rounded-full ${
          tone === "success" ? "bg-emerald-400" :
          tone === "warning" ? "bg-amber-400" :
          tone === "danger" ? "bg-rose-400" :
          "bg-zinc-500"
        }`} aria-hidden="true" />
      </div>
      <p className="mt-2.5 text-sm leading-5 text-zinc-300">{insight.body}</p>
      {insight.action ? (
        <button
          onClick={insight.action.onClick}
          className="mt-3 inline-flex items-center rounded-md border border-accent-500/24 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100"
        >
          {insight.action.label}
        </button>
      ) : null}
    </section>
  );
}
