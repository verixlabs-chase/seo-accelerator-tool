import { cn } from "./utils";

export type TrendTone = "positive" | "negative" | "neutral";

type TrendIndicatorProps = {
  label: string;
  tone?: TrendTone;
};

export function TrendIndicator({
  label,
  tone = "neutral",
}: TrendIndicatorProps) {
  const icon = tone === "positive" ? "↑" : tone === "negative" ? "↓" : "•";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-semibold",
        tone === "positive"
          ? "text-emerald-400"
          : tone === "negative"
            ? "text-rose-400"
            : "text-zinc-400",
      )}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}
