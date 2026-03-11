import type { ReactNode } from "react";

import { SidebarNav } from "./SidebarNav";
import { TopBar } from "./TopBar";
import { TrustStatusBar } from "./TrustStatusBar";
import type { NavItem, TrustSignal } from "./types";

type AppShellProps = {
  navItems: NavItem[];
  trustSignals: TrustSignal[];
  accountLabel: string;
  dateRangeLabel: string;
  children: ReactNode;
  topBarActions?: ReactNode;
};

export function AppShell({
  navItems,
  trustSignals,
  accountLabel,
  dateRangeLabel,
  children,
  topBarActions,
}: AppShellProps) {
  return (
    <div className="lsos-theme-dark min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(99,102,241,0.18),transparent_26%),radial-gradient(circle_at_top_right,rgba(139,92,246,0.14),transparent_24%),linear-gradient(180deg,#050816_0%,#070b16_36%,#090d18_100%)] text-slate-50">
      <div className="mx-auto flex min-h-screen max-w-[1680px] flex-col px-4 py-4 md:px-6 xl:px-8">
        <div className="flex min-h-[calc(100vh-2rem)] overflow-hidden rounded-[30px] border border-white/10 bg-slate-950/50 shadow-[0_24px_80px_rgba(15,23,42,0.42)] backdrop-blur-xl">
          <div className="hidden w-[280px] shrink-0 border-r border-white/10 bg-slate-950/50 xl:block">
            <SidebarNav items={navItems} />
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="border-b border-white/10 bg-slate-950/45">
              <TopBar
                accountLabel={accountLabel}
                dateRangeLabel={dateRangeLabel}
                actions={topBarActions}
              />
            </div>
            <div className="border-b border-indigo-400/12 bg-indigo-500/6">
              <TrustStatusBar signals={trustSignals} />
            </div>
            <main className="lsos-scrollbar flex-1 overflow-y-auto px-5 py-6 md:px-6 xl:px-8">
              {children}
            </main>
          </div>
        </div>
      </div>
    </div>
  );
}
