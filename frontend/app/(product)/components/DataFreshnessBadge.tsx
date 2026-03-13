import { cn } from "./utils";

const toneClasses = {
  info: "border-[#26272c] bg-white/[0.03] text-zinc-100",
  success: "border-emerald-500/20 bg-emerald-500/10 text-emerald-100",
  warning: "border-accent-500/22 bg-accent-500/10 text-zinc-100",
  danger: "border-rose-500/20 bg-rose-500/10 text-rose-100",
} as const;

type DataFreshnessBadgeProps = {
  label: string;
  value: string;
  tone?: keyof typeof toneClasses;
};

export function DataFreshnessBadge({
  label,
  value,
  tone = "info",
}: DataFreshnessBadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium tracking-[0.02em]",
        toneClasses[tone],
      )}
    >
      <span className="h-2 w-2 rounded-full bg-current opacity-80" />
      <span className="text-zinc-400">{label}</span>
      <span>{value}</span>
    </div>
  );
}
