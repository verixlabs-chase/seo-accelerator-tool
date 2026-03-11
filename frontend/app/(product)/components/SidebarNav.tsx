import Link from "next/link";

import type { NavItem } from "./types";
import { cn } from "./utils";

type SidebarNavProps = {
  items: NavItem[];
  title?: string;
  subtitle?: string;
};

export function SidebarNav({
  items,
  title = "Local SEO OS",
  subtitle = "Creative operating system",
}: SidebarNavProps) {
  return (
    <aside className="flex h-full w-full flex-col gap-8 px-5 py-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-indigo-200/80">
          {subtitle}
        </p>
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-indigo-400/25 bg-indigo-500/15 text-sm font-semibold text-indigo-100 shadow-[0_0_30px_rgba(99,102,241,0.22)]">
            LS
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-[-0.03em] text-white">
              {title}
            </h1>
            <p className="text-sm text-slate-400">Clarity, action, trust.</p>
          </div>
        </div>
      </div>

      <nav className="space-y-2">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "group flex items-center justify-between rounded-2xl px-4 py-3 text-sm transition",
              item.active
                ? "border border-indigo-400/25 bg-indigo-500/12 text-white shadow-[0_0_0_1px_rgba(99,102,241,0.12)]"
                : "border border-transparent text-slate-300 hover:border-white/10 hover:bg-white/5 hover:text-white",
            )}
          >
            <span className="font-medium">{item.label}</span>
            {item.badge ? (
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-slate-300">
                {item.badge}
              </span>
            ) : null}
          </Link>
        ))}
      </nav>

      <div className="mt-auto rounded-[22px] border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
          Operating principle
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          Every screen should explain what changed, why it matters, and what to do
          next.
        </p>
      </div>
    </aside>
  );
}
