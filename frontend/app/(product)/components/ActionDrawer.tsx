import type { ReactNode } from "react";

type ActionDrawerProps = {
  title: string;
  summary: string;
  evidence: string[];
  actions?: ReactNode;
};

export function ActionDrawer({
  title,
  summary,
  evidence,
  actions,
}: ActionDrawerProps) {
  return (
    <aside className="rounded-md border border-accent-500/22 bg-[#161417] p-4 shadow-[0_0_0_1px_rgba(255,106,26,0.12),0_0_24px_rgba(255,106,26,0.06)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-600/90">
        Recommended action
      </p>
      <h3 className="mt-2.5 text-lg font-semibold tracking-[-0.03em] text-white">
        {title}
      </h3>
      <p className="mt-2 text-sm leading-5 text-zinc-300">{summary}</p>

      <div className="mt-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
          Why this matters
        </p>
        <ul className="mt-3 space-y-2">
          {evidence.map((item) => (
            <li
              key={item}
              className="rounded-md border border-[#26272c] bg-black/20 px-3 py-2.5 text-sm text-zinc-300"
            >
              {item}
            </li>
          ))}
        </ul>
      </div>

      {actions ? (
        <div className="mt-5 flex flex-wrap gap-2.5">
          {actions}
        </div>
      ) : null}
    </aside>
  );
}
