import type { ReactNode } from "react";

import { ProductIcon } from "./ProductIcon";

export type ChartScope = {
  locationLabel?: string;
  dateRangeLabel?: string;
  comparisonLabel?: string;
};

type ScopeBarProps = ChartScope & {
  actions?: ReactNode;
};

export function ScopeBar({
  locationLabel,
  dateRangeLabel,
  comparisonLabel,
  actions,
}: ScopeBarProps) {
  const labels = [
    locationLabel ? { icon: "locations" as const, text: locationLabel } : null,
    dateRangeLabel ? { icon: "calendar" as const, text: dateRangeLabel } : null,
    comparisonLabel ? { icon: "no-change" as const, text: comparisonLabel } : null,
  ].filter(Boolean) as Array<{
    icon: "locations" | "calendar" | "no-change";
    text: string;
  }>;

  if (labels.length === 0 && !actions) {
    return null;
  }

  return (
    <div aria-label="Chart scope" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-zinc-400">
      {labels.map((item) => (
        <span key={`${item.icon}-${item.text}`} className="inline-flex items-center gap-1.5">
          <ProductIcon name={item.icon} size={14} className="text-zinc-500" />
          {item.text}
        </span>
      ))}
      {actions ? <div className="ml-auto">{actions}</div> : null}
    </div>
  );
}
