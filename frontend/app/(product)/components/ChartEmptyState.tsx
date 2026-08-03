import { ProductIcon } from "./ProductIcon";

type ChartEmptyStateProps = {
  title: string;
  summary: string;
};

export function ChartEmptyState({ title, summary }: ChartEmptyStateProps) {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-md border border-dashed border-[#303137] bg-[#101114] p-6 text-center">
      <div className="max-w-sm">
        <ProductIcon name="empty" size={30} className="mx-auto text-zinc-500" />
        <p className="mt-3 text-sm font-semibold text-zinc-100">{title}</p>
        <p className="mt-1.5 text-sm leading-5 text-zinc-400">{summary}</p>
      </div>
    </div>
  );
}
