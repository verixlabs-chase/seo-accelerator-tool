"use client";

import { usePathname } from "next/navigation";

type ProductPageIntroProps = {
  eyebrow: string;
  title: string;
  summary: string;
};

const START_HERE_BY_PATH: Record<string, string> = {
  "/dashboard": "Review what changed, then choose the one next action shown below.",
  "/rankings": "Check the biggest drop first. Use the location menu above to switch businesses.",
  "/local-visibility":
    "Start with map position and recent reviews, then follow the suggested next step.",
  "/site-health": "Start with the first red or amber item. The technical details can wait.",
  "/opportunities":
    "Begin with the first recommendation. Open more detail only when you need it.",
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
};

export function ProductPageIntro({
  eyebrow,
  title,
  summary,
}: ProductPageIntroProps) {
  const pathname = usePathname();
  const startHere =
    START_HERE_BY_PATH[pathname] ??
    "Review the first result below, then take the single recommended next step.";

  return (
    <header className="grid gap-4 border-b border-[#26272c] pb-4 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.42fr)] lg:items-end">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
          {eyebrow}
        </p>
        <h1 className="mt-1.5 text-3xl font-bold tracking-[-0.045em] text-white md:text-4xl">
          {title}
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">{summary}</p>
      </div>
      <div className="border-l-2 border-accent-500 bg-accent-500/[0.06] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-300">
          Start here
        </p>
        <p className="mt-1 text-sm leading-5 text-zinc-200">{startHere}</p>
      </div>
    </header>
  );
}
