type EmptyStateProps = {
  title: string;
  summary: string;
  actionLabel?: string;
};

export function EmptyState({
  title,
  summary,
  actionLabel = "Start here",
}: EmptyStateProps) {
  return (
    <section className="rounded-[28px] border border-dashed border-white/12 bg-white/[0.03] p-8 text-center">
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-indigo-400/20 bg-indigo-500/12 text-base font-semibold text-indigo-100 shadow-[0_0_30px_rgba(99,102,241,0.2)]">
        LS
      </div>
      <h3 className="mt-5 text-xl font-semibold tracking-[-0.03em] text-white">
        {title}
      </h3>
      <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">
        {summary}
      </p>
      <button className="mt-6 rounded-full border border-indigo-400/25 bg-indigo-500/12 px-5 py-2.5 text-sm font-medium text-indigo-100">
        {actionLabel}
      </button>
    </section>
  );
}
