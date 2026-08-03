import type { ReactNode } from "react";

import { ProductIcon, type ProductIconName } from "./ProductIcon";

export type VisualDataState =
  | "ready"
  | "loading"
  | "empty"
  | "single-point"
  | "partial"
  | "stale"
  | "unsupported"
  | "error";

type DataStateProps = {
  state: Exclude<VisualDataState, "ready">;
  title: string;
  summary: string;
  action?: ReactNode;
};

const stateIcon: Record<Exclude<VisualDataState, "ready">, ProductIconName> = {
  loading: "chart",
  empty: "empty",
  "single-point": "chart",
  partial: "info",
  stale: "calendar",
  unsupported: "info",
  error: "warning",
};

export function DataState({ state, title, summary, action }: DataStateProps) {
  const isWarning = state === "stale" || state === "partial";
  const isError = state === "error";

  return (
    <div
      role={isError ? "alert" : "status"}
      className="flex min-h-48 items-center justify-center border-y border-dashed border-[#303137] bg-[#101114]/70 px-5 py-8 text-center"
    >
      <div className="max-w-md">
        <ProductIcon
          name={stateIcon[state]}
          size={28}
          className={`mx-auto ${
            isError ? "text-rose-400" : isWarning ? "text-amber-400" : "text-zinc-500"
          }`}
        />
        <p className="mt-3 text-sm font-semibold text-zinc-100">{title}</p>
        <p className="mt-1.5 text-sm leading-5 text-zinc-400">{summary}</p>
        {action ? <div className="mt-4">{action}</div> : null}
      </div>
    </div>
  );
}
