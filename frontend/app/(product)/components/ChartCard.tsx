import type { ReactNode } from "react";

import { DataState, type VisualDataState } from "./DataState";
import { DetailsDisclosure } from "./DetailsDisclosure";
import { ProductIcon, type ProductIconName } from "./ProductIcon";
import { ScopeBar, type ChartScope } from "./ScopeBar";

type ChartLegendItem = {
  label: string;
  color: string;
  description?: string;
};

type ChartCardProps = {
  eyebrow?: string;
  title: string;
  summary: string;
  chart: ReactNode;
  footer?: ReactNode;
  icon?: ProductIconName;
  scope?: ChartScope;
  scopeActions?: ReactNode;
  legend?: ChartLegendItem[];
  state?: VisualDataState;
  stateTitle?: string;
  stateSummary?: string;
  details?: ReactNode;
  detailsSummary?: string;
};

export function ChartCard({
  eyebrow = "Chart",
  title,
  summary,
  chart,
  footer,
  icon = "chart",
  scope,
  scopeActions,
  legend = [],
  state = "ready",
  stateTitle = "Not enough history yet",
  stateSummary = "Run another check later to build a useful trend.",
  details,
  detailsSummary,
}: ChartCardProps) {
  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)] transition hover:shadow-[0_0_36px_rgba(0,0,0,0.48)]">
      <div className="flex items-start gap-3">
        <ProductIcon name={icon} size={18} className="mt-0.5 shrink-0 text-accent-400" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-base font-semibold tracking-[-0.02em] text-white">{title}</h3>
          <p className="mt-1.5 max-w-2xl text-sm leading-5 text-zinc-300">{summary}</p>
        </div>
      </div>
      {scope || scopeActions ? (
        <div className="mt-3 border-y border-[#26272c] py-2.5">
          <ScopeBar {...scope} actions={scopeActions} />
        </div>
      ) : null}
      <div className="mt-4" aria-label={`${title} chart`}>
        {state === "ready" ? (
          chart
        ) : (
          <DataState state={state} title={stateTitle} summary={stateSummary} />
        )}
      </div>
      {legend.length > 0 ? (
        <ul aria-label={`${title} legend`} className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-400">
          {legend.map((item) => (
            <li key={item.label} className="inline-flex items-center gap-1.5" title={item.description}>
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 rounded-sm border border-white/10"
                style={{ backgroundColor: item.color }}
              />
              {item.label}
            </li>
          ))}
        </ul>
      ) : null}
      {footer ? <div className="mt-4 border-t border-[#26272c] pt-3">{footer}</div> : null}
      {details ? (
        <div className="mt-4">
          <DetailsDisclosure summary={detailsSummary}>{details}</DetailsDisclosure>
        </div>
      ) : null}
    </section>
  );
}
