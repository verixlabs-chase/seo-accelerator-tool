import type { ReactNode } from "react";

import { ProductIcon, type ProductIconName } from "./ProductIcon";

type PageSectionProps = {
  title: string;
  summary?: string;
  icon?: ProductIconName;
  action?: ReactNode;
  children: ReactNode;
};

export function PageSection({ title, summary, icon, action, children }: PageSectionProps) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-start gap-2.5">
          {icon ? <ProductIcon name={icon} size={18} className="mt-0.5 text-accent-400" /> : null}
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.025em] text-white">{title}</h2>
            {summary ? <p className="mt-1 text-sm leading-5 text-zinc-400">{summary}</p> : null}
          </div>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
