import type { ReactNode } from "react";

type ChartCardProps = {
  eyebrow?: string;
  title: string;
  summary: string;
  chart: ReactNode;
  footer?: ReactNode;
};

export function ChartCard({
  eyebrow = "Chart",
  title,
  summary,
  chart,
  footer,
}: ChartCardProps) {
  return (
    <section className="rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] p-5 shadow-[0_18px_55px_rgba(15,23,42,0.36)] md:p-6">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
        {eyebrow}
      </p>
      <div className="mt-2 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold tracking-[-0.02em] text-white">
            {title}
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{summary}</p>
        </div>
      </div>
      <div className="mt-6">{chart}</div>
      {footer ? <div className="mt-5 border-t border-white/10 pt-4">{footer}</div> : null}
    </section>
  );
}
