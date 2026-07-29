type ChartEmptyStateProps = {
  title: string;
  summary: string;
};

export function ChartEmptyState({ title, summary }: ChartEmptyStateProps) {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-md border border-dashed border-[#303137] bg-[#101114] p-6 text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-10 w-10 items-end justify-center gap-1 rounded-md border border-[#303137] bg-[#141518] p-2">
          <span className="h-2 w-1.5 rounded-sm bg-zinc-600" />
          <span className="h-4 w-1.5 rounded-sm bg-zinc-500" />
          <span className="h-6 w-1.5 rounded-sm bg-accent-500/70" />
        </div>
        <p className="mt-3 text-sm font-semibold text-zinc-100">{title}</p>
        <p className="mt-1.5 text-sm leading-5 text-zinc-400">{summary}</p>
      </div>
    </div>
  );
}
