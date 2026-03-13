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
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)] transition hover:shadow-[0_0_36px_rgba(0,0,0,0.48)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {eyebrow}
      </p>
      <div className="mt-2 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-[-0.02em] text-white">
            {title}
          </h3>
          <p className="mt-1.5 max-w-2xl text-sm leading-5 text-zinc-300">{summary}</p>
        </div>
      </div>
      <div className="mt-4">{chart}</div>
      {footer ? <div className="mt-4 border-t border-[#26272c] pt-3">{footer}</div> : null}
    </section>
  );
}
