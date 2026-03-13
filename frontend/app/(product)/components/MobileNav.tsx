"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { SidebarNav } from "./SidebarNav";
import type { NavItem } from "./types";

type MobileNavProps = {
  navItems: NavItem[];
  isOpen: boolean;
  onClose: () => void;
};

export function MobileNav({ navItems, isOpen, onClose }: MobileNavProps) {
  const pathname = usePathname();

  // Close drawer on route change
  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 xl:hidden">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Drawer */}
      <aside className="relative h-full w-[260px] border-r border-[#26272c] bg-[#0b0b0c] shadow-[4px_0_24px_rgba(0,0,0,0.5)]">
        <SidebarNav items={navItems} />
      </aside>
    </div>
  );
}
