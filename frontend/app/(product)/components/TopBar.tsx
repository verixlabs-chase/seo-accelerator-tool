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
    <header className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="rounded-md border border-[#26272c] bg-[#131417] px-3 py-1.5 text-sm text-zinc-200">
          {accountLabel}
        </div>
        <div className="rounded-md border border-[#26272c] bg-[#131417] px-3 py-1.5 text-sm text-zinc-400">
          {dateRangeLabel}
        </div>
        <div className="min-w-[260px] rounded-md border border-[#26272c] bg-[#0d0e10] px-3 py-2 text-sm text-zinc-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
          Search pages, keywords, or locations
        </div>
      </div>

      <div className={cn("flex items-center gap-2", actions ? "" : "text-zinc-300")}>
        {actions ?? (
          <>
            <button className="rounded-md border border-[#26272c] bg-white/[0.03] px-3 py-1.5 text-sm text-zinc-200">
              Alerts
            </button>
            <button className="rounded-md border border-[#26272c] bg-white/[0.03] px-3 py-1.5 text-sm text-zinc-200">
              Help
            </button>
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-accent-500/25 bg-accent-500/10 text-sm font-semibold text-zinc-100 shadow-[0_0_16px_rgba(255,106,26,0.08)]">
              VA
            </div>
          </>
        )}
      </div>
    </header>
  );
}
