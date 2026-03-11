import type { ReactNode } from "react";

type MapCardProps = {
  title: string;
  summary: string;
  map: ReactNode;
  legend?: ReactNode;
};

export function MapCard({ title, summary, map, legend }: MapCardProps) {
  return (
    <section className="rounded-[28px] border border-indigo-400/18 bg-[linear-gradient(180deg,rgba(27,37,72,0.96),rgba(17,24,39,0.88))] p-5 shadow-[0_0_0_1px_rgba(99,102,241,0.14),0_18px_50px_rgba(99,102,241,0.12)] md:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200/80">
            Local visibility
          </p>
          <h3 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-white">
            {title}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">{summary}</p>
        </div>
        {legend}
      </div>
      <div className="mt-6 overflow-hidden rounded-[22px] border border-white/10 bg-slate-950/60">
        {map}
      </div>
    </section>
  );
}
