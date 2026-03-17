export type TimelineEntry = {
  key: string;
  label: string;
  detail: string;
  timestamp: string | null;
  tone: "neutral" | "success" | "warning" | "error";
};

function formatRelativeTime(value?: string | null) {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const hours = Math.round(diffMs / 3600000);

  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(diffMs / 86400000);
  return formatter.format(days, "day");
}

function getDotClass(tone: TimelineEntry["tone"]) {
  if (tone === "success") return "bg-emerald-500";
  if (tone === "warning") return "bg-amber-500";
  if (tone === "error") return "bg-rose-500";
  return "bg-zinc-500";
}

type ExecutionTimelineProps = {
  entries: TimelineEntry[];
};

export function ExecutionTimeline({ entries }: ExecutionTimelineProps) {
  return (
    <div className="rounded-md border border-[#26272c] bg-[#141518] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        History
      </p>
      <h3 className="mt-1.5 text-base font-semibold tracking-[-0.03em] text-white">
        Execution timeline
      </h3>
      <div className="mt-4">
        {entries.map((entry, index) => {
          const relTime = formatRelativeTime(entry.timestamp);
          const isLast = index === entries.length - 1;
          return (
            <div key={entry.key} className="flex gap-3">
              <div className="flex flex-col items-center pt-1">
                <div
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${getDotClass(entry.tone)}`}
                />
                {!isLast ? (
                  <div className="mt-1.5 min-h-5 w-px flex-1 bg-[#26272c]" />
                ) : null}
              </div>
              <div className={`min-w-0 flex-1 ${!isLast ? "pb-4" : ""}`}>
                <div className="flex flex-wrap items-baseline gap-3">
                  <p className="text-sm font-medium text-zinc-100">
                    {entry.label}
                  </p>
                  {relTime ? (
                    <span className="text-xs text-zinc-500">{relTime}</span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-sm leading-5 text-zinc-400">
                  {entry.detail}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
