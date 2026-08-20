import Link from "next/link";

import { ProductIcon } from "./ProductIcon";
import type { NavItem } from "./types";
import { cn } from "./utils";

type SidebarNavProps = {
  items: NavItem[];
  title?: string;
  subtitle?: string;
};

const NAV_SECTIONS = [
  { id: "most-used", label: "Most used" },
  { id: "performance", label: "Measure performance" },
  { id: "improve", label: "Improve visibility" },
  { id: "workspace", label: "Manage workspace" },
  { id: "help", label: "Help" },
] as const;

export function SidebarNav({
  items,
  title = "Local growth workspace",
  subtitle = "InsightOS",
}: SidebarNavProps) {
  const visibleItems = items.filter((item) => !item.hidden);

  function NavLinks({ links }: { links: NavItem[] }) {
    return links.map((item) => (
      item.disabled ? (
        <div
          key={item.href}
          aria-disabled="true"
          className="flex cursor-not-allowed items-center justify-between border border-transparent px-3 py-2 text-sm text-zinc-600"
        >
          <span className="flex items-center gap-2.5 font-medium">
            <ProductIcon name={item.icon} size={18} />
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
            <ProductIcon
              name={item.icon}
              size={18}
              className={cn(
                "shrink-0 transition",
                item.active ? "text-accent-400" : "text-zinc-500 group-hover:text-zinc-300",
              )}
            />
            {item.label}
          </span>
          {item.badge ? (
            <span className="border border-accent-500/25 bg-accent-500/10 px-1.5 py-0.5 text-[10px] text-zinc-100">
              {item.badge}
            </span>
          ) : null}
        </Link>
      )
    ));
  }

  return (
    <aside className="flex h-full min-h-0 w-full flex-col gap-4 px-4 py-4">
      <div className="border-b border-[#26272c] pb-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/92">
          {subtitle}
        </p>
        <p className="mt-2 text-sm font-semibold tracking-[0.01em] text-zinc-400">
          {title}
        </p>
      </div>

      <nav aria-label="Product navigation" className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
        {NAV_SECTIONS.map((section) => {
          const sectionItems = visibleItems.filter((item) => item.section === section.id);
          if (sectionItems.length === 0) return null;
          return (
            <section key={section.id} aria-labelledby={`navigation-${section.id}`}>
              <h2
                id={`navigation-${section.id}`}
                className="px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500"
              >
                {section.label}
              </h2>
              <div className="mt-1 space-y-1">
                <NavLinks links={sectionItems} />
              </div>
            </section>
          );
        })}
      </nav>

      <p className="mt-auto border-t border-[#26272c] px-3 pt-4 text-xs leading-5 text-zinc-500">
        Clear next steps for local service businesses.
      </p>
    </aside>
  );
}
