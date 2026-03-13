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
  title = "InsightOS",
  subtitle = "InsightOS",
}: SidebarNavProps) {
  function NavGlyph({ active = false }: { active?: boolean }) {
    return (
      <span
        className={cn(
          "inline-block h-3 w-3 rounded-[2px] border",
          active
            ? "border-accent-500/55 bg-accent-500/30 shadow-[0_0_12px_rgba(255,106,26,0.25)]"
            : "border-[#26272c] bg-[#141518]",
        )}
      />
    );
  }

  return (
    <aside className="flex h-full w-full flex-col gap-6 px-4 py-4">
      <div className="border-b border-[#26272c] pb-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/92">
          {subtitle}
        </p>
        <h1 className="mt-2 text-sm font-semibold tracking-[0.01em] text-zinc-400">
          {title}
        </h1>
      </div>

      <nav className="space-y-1.5">
        {items.map((item) => (
          item.disabled ? (
            <div
              key={item.href}
              aria-disabled="true"
              className="flex cursor-not-allowed items-center justify-between border border-transparent px-3 py-2 text-sm text-zinc-600"
            >
              <span className="flex items-center gap-2.5 font-medium">
                <NavGlyph />
                {item.label}
              </span>
              <span className="border border-[#26272c] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                Coming soon
              </span>
            </div>
          ) : (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center justify-between rounded-md border px-3 py-2 text-sm transition",
                item.active
                  ? "border-[#3a2a20] bg-[linear-gradient(90deg,rgba(255,106,26,0.14),rgba(255,106,26,0.02))] text-white shadow-[inset_2px_0_0_0_rgba(255,106,26,1)]"
                  : "border-transparent text-zinc-300 hover:border-[#26272c] hover:bg-white/[0.02] hover:text-white",
              )}
            >
              <span className="flex items-center gap-2.5 font-medium">
                <NavGlyph active={item.active} />
                {item.label}
              </span>
              {item.badge ? (
                <span className="border border-accent-500/25 bg-accent-500/10 px-1.5 py-0.5 text-[10px] text-zinc-100">
                  {item.badge}
                </span>
              ) : null}
            </Link>
          )
        ))}
      </nav>

      <div className="mt-auto rounded-md border border-[#26272c] bg-[#111214] p-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
          Operating principle
        </p>
        <p className="mt-2 text-sm leading-5 text-zinc-400">
          Every screen should explain what changed, why it matters, and what to do
          next.
        </p>
      </div>
    </aside>
  );
}
