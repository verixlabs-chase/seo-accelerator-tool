import type { ReactNode } from "react";

import { cn } from "./utils";

type TopBarProps = {
  accountLabel: string;
  dateRangeLabel: string;
  actions?: ReactNode;
  onMenuOpen?: () => void;
};

export function TopBar({
  accountLabel,
  dateRangeLabel,
  actions,
  onMenuOpen,
}: TopBarProps) {
  return (
    <header className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-5">
      <div className="flex flex-wrap items-center gap-2.5">
        {onMenuOpen ? (
          <button
            onClick={onMenuOpen}
            className="rounded-md border border-[#26272c] bg-[#131417] px-2.5 py-1.5 text-sm text-zinc-200 xl:hidden"
            aria-label="Open navigation menu"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <path d="M2 4.5h14M2 9h14M2 13.5h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        ) : null}
        <div className="rounded-md border border-[#26272c] bg-[#131417] px-3 py-1.5 text-sm text-zinc-200">
          {accountLabel}
        </div>
        <div className="rounded-md border border-[#26272c] bg-[#131417] px-3 py-1.5 text-sm text-zinc-400">
          {dateRangeLabel}
        </div>
        <div className="rounded-md border border-[#26272c] bg-[#0d0e10] px-3 py-1.5 text-sm text-zinc-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
          Guided workspace
        </div>
      </div>

      <div className={cn("flex items-center gap-2", actions ? "" : "text-zinc-300")}>
        {actions ?? (
          <>
            <div className="rounded-md border border-[#26272c] bg-white/[0.03] px-3 py-1.5 text-sm text-zinc-400">
              Customer-facing workflows only
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-accent-500/25 bg-accent-500/10 text-sm font-semibold text-zinc-100 shadow-[0_0_16px_rgba(255,106,26,0.08)]">
              VA
            </div>
          </>
        )}
      </div>
    </header>
  );
}
