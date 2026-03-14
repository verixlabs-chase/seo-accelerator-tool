import type { ReactNode } from "react";

type MapCardProps = {
  title: string;
  summary: string;
  map: ReactNode;
  legend?: ReactNode;
};

export function MapCard({ title, summary, map, legend }: MapCardProps) {
  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Local visibility
          </p>
          <h3 className="mt-1.5 text-base font-semibold tracking-[-0.02em] text-white">
            {title}
          </h3>
          <p className="mt-1.5 text-sm leading-5 text-zinc-300">{summary}</p>
        </div>
        {legend}
      </div>
      <div className="mt-4 overflow-hidden rounded-md border border-[#26272c] bg-[#0b0b0c]">
        {map}
      </div>
    </section>
  );
}
