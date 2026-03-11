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
        "rounded-[24px] border p-5 md:p-6",
        tone === "highlight"
          ? "border-indigo-400/22 bg-[linear-gradient(180deg,rgba(27,37,72,0.96),rgba(17,24,39,0.88))] shadow-[0_0_0_1px_rgba(99,102,241,0.14),0_18px_50px_rgba(99,102,241,0.12)]"
          : "border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] shadow-[0_18px_55px_rgba(15,23,42,0.36)]",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            {label}
          </p>
          <div className="mt-3 flex items-end gap-3">
            <p className="text-3xl font-semibold tracking-[-0.04em] text-white md:text-4xl">
              {value}
            </p>
            {changeLabel ? (
              <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-xs font-medium text-emerald-100">
                {changeLabel}
              </span>
            ) : null}
          </div>
        </div>
        {visual ? <div className="min-w-[88px]">{visual}</div> : null}
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-300">{summary}</p>
    </section>
  );
}
