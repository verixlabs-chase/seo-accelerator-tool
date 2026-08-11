"use client";

import { usePathname } from "next/navigation";

import { ProductIcon, type ProductIconName } from "./ProductIcon";

type ProductPageIntroProps = {
  eyebrow: string;
  title: string;
  summary: string;
  compact?: boolean;
};

const START_HERE_BY_PATH: Record<string, string> = {
  "/dashboard": "Read what changed, take the one next action, then compare the Google results below.",
  "/rankings": "Check the biggest drop first. Use the location menu above to switch businesses.",
  "/keyword-research":
    "Review the best opportunities first. Track only the searches that match work you want.",
  "/local-visibility":
    "Start with map position and recent reviews, then follow the suggested next step.",
  "/site-health": "Start with the first red or amber item. The technical details can wait.",
  "/opportunities":
    "Choose Today, This week, or This month, then finish the next unchecked step.",
  "/reports": "Check the headline and next action before creating or sharing a report.",
  "/settings":
    "Connect the source marked as needing attention; leave healthy connections alone.",
  "/locations":
    "Confirm every location is assigned, then add or edit only what is missing.",
  "/organic-value":
    "Start with current value and upside. Treat every dollar amount as an estimate.",
  "/competitors":
    "Start with the largest gap, then decide whether a fresh comparison is needed.",
  "/citations":
    "Fix failed or missing listings first; confirmed live listings need no action.",
  "/reviews":
    "Start with reviews that need a reply, especially any review with 3 stars or less.",
  "/profile-campaigns":
    "Choose a saved location group, write one update, and review every location before approval.",
};

const PAGE_ICON_BY_PATH: Record<string, ProductIconName> = {
  "/dashboard": "overview",
  "/rankings": "rankings",
  "/keyword-research": "keyword-research",
  "/local-visibility": "local-search",
  "/site-health": "website-health",
  "/opportunities": "next-steps",
  "/reports": "reports",
  "/settings": "connections",
  "/locations": "locations",
  "/organic-value": "search-value",
  "/competitors": "competitors",
  "/citations": "listings",
  "/reviews": "reviews",
  "/profile-campaigns": "profile-campaigns",
};

export function ProductPageIntro({
  eyebrow,
  title,
  summary,
  compact = false,
}: ProductPageIntroProps) {
  const pathname = usePathname();
  const startHere =
    START_HERE_BY_PATH[pathname] ??
    "Review the first result below, then take the single recommended next step.";
  const icon = PAGE_ICON_BY_PATH[pathname] ?? "spark";

  return (
    <header className={`border-b border-[#26272c] ${compact ? "pb-3" : "pb-4"}`}>
      <div className="flex items-start gap-3.5">
        <div className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent-500/10 text-accent-400 ring-1 ring-inset ring-accent-500/20">
          <ProductIcon name={icon} size={21} />
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
            {eyebrow}
          </p>
          <h1 className={`mt-1 font-bold tracking-[-0.045em] text-white ${compact ? "text-3xl" : "text-3xl md:text-4xl"}`}>
            {title}
          </h1>
          {compact ? null : (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">{summary}</p>
          )}
        </div>
      </div>
      <p className={`${compact ? "mt-2" : "mt-3"} flex max-w-4xl items-start gap-2 text-sm leading-5 text-zinc-400 md:ml-[3.375rem]`}>
        <ProductIcon name="spark" size={16} className="mt-0.5 shrink-0 text-accent-400" />
        <span><strong className="font-semibold text-zinc-200">Start here:</strong> {startHere}</span>
      </p>
      {compact ? <p className="sr-only">{summary}</p> : null}
    </header>
  );
}
