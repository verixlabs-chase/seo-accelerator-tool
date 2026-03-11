import type { ReactNode } from "react";

import { cn } from "./utils";

type TopBarProps = {
  accountLabel: string;
  dateRangeLabel: string;
  actions?: ReactNode;
};

export function TopBar({
  accountLabel,
  dateRangeLabel,
  actions,
}: TopBarProps) {
  return (
    <header className="flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between md:px-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
          {accountLabel}
        </div>
        <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
          {dateRangeLabel}
        </div>
        <div className="min-w-[240px] rounded-full border border-white/10 bg-slate-950/80 px-4 py-2.5 text-sm text-slate-500">
          Search pages, keywords, or locations
        </div>
      </div>

      <div className={cn("flex items-center gap-2", actions ? "" : "text-slate-300")}>
        {actions ?? (
          <>
            <button className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
              Alerts
            </button>
            <button className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
              Help
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-full border border-indigo-400/20 bg-indigo-500/15 text-sm font-semibold text-indigo-100">
              VA
            </div>
          </>
        )}
      </div>
    </header>
  );
}
