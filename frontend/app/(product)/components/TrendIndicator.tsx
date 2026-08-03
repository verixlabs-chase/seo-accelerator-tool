import { cn } from "./utils";
import { ProductIcon } from "./ProductIcon";

export type TrendTone = "positive" | "negative" | "neutral";

type TrendIndicatorProps = {
  label: string;
  tone?: TrendTone;
};

export function TrendIndicator({
  label,
  tone = "neutral",
}: TrendIndicatorProps) {
  const icon = tone === "positive" ? "arrow-up" : tone === "negative" ? "arrow-down" : "no-change";
  const direction = tone === "positive" ? "Improving" : tone === "negative" ? "Slipping" : "No clear change";
  return (
    <span
      aria-label={`${direction}: ${label}`}
      className={cn(
        "inline-flex items-center gap-1 text-xs font-semibold",
        tone === "positive"
          ? "text-emerald-400"
          : tone === "negative"
            ? "text-rose-400"
            : "text-zinc-400",
      )}
    >
      <ProductIcon name={icon} size={13} />
      {label}
    </span>
  );
}
