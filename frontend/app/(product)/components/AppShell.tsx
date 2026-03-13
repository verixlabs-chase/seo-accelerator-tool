"use client";

import { useState, type ReactNode } from "react";

import { MobileNav } from "./MobileNav";
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="lsos-theme-dark min-h-screen bg-[radial-gradient(circle_at_22%_0%,rgba(255,106,26,0.12),transparent_16%),radial-gradient(circle_at_70%_12%,rgba(255,255,255,0.035),transparent_22%),linear-gradient(180deg,#09090a_0%,#0b0b0c_48%,#101114_100%)] font-sans text-zinc-50">
      <div className="flex min-h-screen flex-col">
        <div className="flex min-h-screen overflow-hidden rounded-md border border-[#26272c] bg-[#0f1012] shadow-[0_0_30px_rgba(0,0,0,0.4)]">
          <div className="hidden w-[232px] shrink-0 border-r border-[#26272c] bg-[#0b0b0c] xl:block">
            <SidebarNav items={navItems} />
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="border-b border-[#26272c] bg-[#101114]">
              <TopBar
                accountLabel={accountLabel}
                dateRangeLabel={dateRangeLabel}
                actions={topBarActions}
                onMenuOpen={() => setMobileNavOpen(true)}
              />
            </div>
            <div className="border-b border-[#26272c] bg-[#111214]">
              <TrustStatusBar signals={trustSignals} />
            </div>
            <main className="lsos-scrollbar flex-1 overflow-y-auto px-4 py-4 md:px-5 xl:px-6">
              {children}
            </main>
          </div>
        </div>
      </div>

      <MobileNav
        navItems={navItems}
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />
    </div>
  );
}
