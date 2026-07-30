import type { ReactNode } from "react";

import { cn } from "./utils";
import { TrendIndicator, type TrendTone } from "./TrendIndicator";

type KpiCardProps = {
  label: string;
  value: string;
  changeLabel?: string;
  changeTone?: TrendTone;
  summary: string;
  visual?: ReactNode;
  tone?: "default" | "highlight";
};

export function KpiCard({
  label,
  value,
  changeLabel,
  changeTone = "neutral",
  summary,
  visual,
  tone = "default",
}: KpiCardProps) {
  return (
    <section
      className={cn(
        "border-l-2 px-4 py-3",
        tone === "highlight"
          ? "border-l-accent-500 bg-accent-500/[0.06]"
          : "border-l-[#34353b] bg-white/[0.015]",
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
              <TrendIndicator label={changeLabel} tone={changeTone} />
            ) : null}
          </div>
        </div>
        {visual ? <div className="min-w-[88px]">{visual}</div> : null}
      </div>
      <p className="mt-3 text-sm leading-5 text-zinc-300">{summary}</p>
    </section>
  );
}
