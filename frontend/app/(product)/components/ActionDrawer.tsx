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
    <aside className="rounded-[28px] border border-indigo-400/18 bg-[linear-gradient(180deg,rgba(27,37,72,0.96),rgba(17,24,39,0.88))] p-6 shadow-[0_0_0_1px_rgba(99,102,241,0.14),0_18px_50px_rgba(99,102,241,0.12)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200/80">
        Action drawer
      </p>
      <h3 className="mt-3 text-xl font-semibold tracking-[-0.03em] text-white">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-6 text-slate-300">{summary}</p>

      <div className="mt-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
          Why this matters
        </p>
        <ul className="mt-3 space-y-3">
          {evidence.map((item) => (
            <li
              key={item}
              className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300"
            >
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        {actions ?? (
          <>
            <button className="rounded-full border border-indigo-400/25 bg-indigo-500/12 px-4 py-2 text-sm font-medium text-indigo-100">
              Approve
            </button>
            <button className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200">
              Schedule
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
