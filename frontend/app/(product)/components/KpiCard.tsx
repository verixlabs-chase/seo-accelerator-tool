import type { ReactNode } from "react";

import { cn } from "./utils";

type KpiCardProps = {
  label: string;
  value: string;
  changeLabel?: string;
  summary: string;
  visual?: ReactNode;
  tone?: "default" | "highlight";
};

export function KpiCard({
  label,
  value,
  changeLabel,
  summary,
  visual,
  tone = "default",
}: KpiCardProps) {
  return (
    <section
      className={cn(
        "rounded-md border p-3.5 shadow-[0_0_30px_rgba(0,0,0,0.4)] transition hover:shadow-[0_0_36px_rgba(0,0,0,0.48)]",
        tone === "highlight"
          ? "border-[#3a2a20] bg-[#171417]"
          : "border-[#26272c] bg-[#141518]",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            {label}
          </p>
          <div className="mt-2.5 flex items-end gap-2.5">
            <p className="text-[2rem] font-semibold tracking-[-0.04em] text-white">
              {value}
            </p>
            {changeLabel ? (
              <span className="rounded-md border border-accent-500/24 bg-accent-500/10 px-2 py-0.5 text-[11px] font-medium text-zinc-100">
                {changeLabel}
              </span>
            ) : null}
          </div>
        </div>
        {visual ? <div className="min-w-[88px]">{visual}</div> : null}
      </div>
      <p className="mt-3 text-sm leading-5 text-zinc-300">{summary}</p>
    </section>
  );
}
