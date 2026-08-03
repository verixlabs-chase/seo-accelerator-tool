import type { ReactNode } from "react";

import { ProductIcon } from "./ProductIcon";

type DetailsDisclosureProps = {
  label?: string;
  summary?: string;
  children: ReactNode;
};

export function DetailsDisclosure({
  label = "How this was measured",
  summary,
  children,
}: DetailsDisclosureProps) {
  return (
    <details className="group border-t border-[#26272c] pt-3 text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-zinc-300 hover:text-white">
        <ProductIcon name="info" size={16} className="text-zinc-500" />
        <span>{label}</span>
        <span aria-hidden="true" className="ml-auto text-zinc-500 transition group-open:rotate-45">
          +
        </span>
      </summary>
      {summary ? <p className="mt-2 text-sm leading-5 text-zinc-400">{summary}</p> : null}
      <div className="mt-3 text-sm leading-5 text-zinc-400">{children}</div>
    </details>
  );
}
