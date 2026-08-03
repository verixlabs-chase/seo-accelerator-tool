"use client";

import { ProductIcon, type ProductIconName } from "./ProductIcon";

type DecisionTone = "positive" | "warning" | "urgent" | "neutral";

type ProgressSummary = {
  label: string;
  value: number;
  total: number;
  valueLabel?: string;
  summary?: string;
};

type OwnerDecisionPanelProps = {
  eyebrow?: string;
  title: string;
  summary: string;
  nextStep: string;
  actionLabel?: string;
  onAction?: () => void;
  tone?: DecisionTone;
  progress?: ProgressSummary;
};

const toneStyles: Record<
  DecisionTone,
  { icon: ProductIconName; iconClass: string; borderClass: string }
> = {
  positive: {
    icon: "check",
    iconClass: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/20",
    borderClass: "border-emerald-500/50",
  },
  warning: {
    icon: "warning",
    iconClass: "bg-amber-500/10 text-amber-200 ring-amber-500/20",
    borderClass: "border-amber-400/60",
  },
  urgent: {
    icon: "warning",
    iconClass: "bg-rose-500/10 text-rose-200 ring-rose-500/20",
    borderClass: "border-rose-400/60",
  },
  neutral: {
    icon: "info",
    iconClass: "bg-sky-500/10 text-sky-200 ring-sky-500/20",
    borderClass: "border-sky-400/50",
  },
};

function clampPercent(value: number, total: number) {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (value / total) * 100));
}

export function OwnerDecisionPanel({
  eyebrow = "Current result",
  title,
  summary,
  nextStep,
  actionLabel,
  onAction,
  tone = "neutral",
  progress,
}: OwnerDecisionPanelProps) {
  const styles = toneStyles[tone];
  const progressPercent = progress
    ? clampPercent(progress.value, progress.total)
    : 0;

  return (
    <section
      aria-label="Current result and next action"
      className={`border-y border-[#2b2c31] border-l-2 ${styles.borderClass} bg-white/[0.015] px-4 py-4 md:px-5`}
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)] lg:items-center">
        <div className="flex min-w-0 items-start gap-3.5">
          <div
            className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-lg ring-1 ring-inset ${styles.iconClass}`}
          >
            <ProductIcon name={styles.icon} size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.17em] text-zinc-500">
              {eyebrow}
            </p>
            <h2 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
              {title}
            </h2>
            <p className="mt-1.5 max-w-3xl text-sm leading-6 text-zinc-300">
              {summary}
            </p>

            {progress ? (
              <div className="mt-4 max-w-2xl">
                <div className="flex items-center justify-between gap-3 text-xs text-zinc-400">
                  <span>{progress.label}</span>
                  <span className="font-medium text-zinc-200">
                    {progress.valueLabel || `${progress.value} of ${progress.total}`}
                  </span>
                </div>
                <div
                  className="mt-2 h-2 overflow-hidden rounded-full bg-[#27282d]"
                  role="progressbar"
                  aria-label={progress.label}
                  aria-valuemin={0}
                  aria-valuemax={Math.max(0, progress.total)}
                  aria-valuenow={Math.max(0, progress.value)}
                >
                  <div
                    className={`h-full rounded-full ${
                      tone === "urgent"
                        ? "bg-rose-400"
                        : tone === "warning"
                          ? "bg-amber-400"
                          : tone === "positive"
                            ? "bg-emerald-400"
                            : "bg-sky-400"
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                {progress.summary ? (
                  <p className="mt-1.5 text-xs leading-5 text-zinc-500">
                    {progress.summary}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="border-t border-[#2b2c31] pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.17em] text-accent-400">
            Do this next
          </p>
          <p className="mt-1.5 text-sm leading-6 text-zinc-200">{nextStep}</p>
          {actionLabel && onAction ? (
            <button
              type="button"
              onClick={onAction}
              className="mt-3 inline-flex items-center gap-2 rounded-md bg-accent-500 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-accent-400"
            >
              {actionLabel}
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
