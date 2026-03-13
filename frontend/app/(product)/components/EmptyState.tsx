type EmptyStateProps = {
  title: string;
  summary: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function EmptyState({
  title,
  summary,
  actionLabel = "Start here",
  onAction,
}: EmptyStateProps) {
  return (
    <section className="rounded-md border border-dashed border-[#26272c] bg-[#141518] p-6 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-md border border-accent-500/20 bg-accent-500/10 text-base font-semibold text-zinc-100 shadow-[0_0_18px_rgba(255,106,26,0.08)]">
        LS
      </div>
      <h3 className="mt-4 text-lg font-semibold tracking-[-0.03em] text-white">
        {title}
      </h3>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-5 text-zinc-300">
        {summary}
      </p>
      <button
        onClick={onAction}
        className="mt-5 rounded-md border border-accent-500/25 bg-accent-500/10 px-4 py-1.5 text-sm font-medium text-zinc-100"
      >
        {actionLabel}
      </button>
    </section>
  );
}
