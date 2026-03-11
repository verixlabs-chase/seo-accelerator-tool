import { cn } from "./utils";

const toneClasses = {
  info: "border-sky-400/20 bg-sky-400/10 text-sky-100",
  success: "border-emerald-400/20 bg-emerald-400/10 text-emerald-100",
  warning: "border-amber-400/20 bg-amber-400/10 text-amber-100",
  danger: "border-rose-400/20 bg-rose-400/10 text-rose-100",
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
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium tracking-[0.02em]",
        toneClasses[tone],
      )}
    >
      <span className="h-2 w-2 rounded-full bg-current opacity-80" />
      <span className="text-slate-300">{label}</span>
      <span>{value}</span>
    </div>
  );
}
