"use client";

import { useEffect, useState } from "react";

import { platformApi } from "../../platform/api";

type CustomerStatusIncident = {
  id: string;
  state: "investigating" | "identified" | "monitoring" | "maintenance";
  impact: "none" | "minor" | "major" | "critical";
  title: string;
  message: string;
  affected_surfaces: Array<{ code: string; label: string }>;
  starts_at: string;
  ends_at: string | null;
  updated_at: string;
};

type CustomerStatusSummary = {
  state: "operational" | "notice" | "degraded";
  incidents: CustomerStatusIncident[];
  checked_at: string;
};

const STATE_LABELS: Record<CustomerStatusIncident["state"], string> = {
  investigating: "We are investigating",
  identified: "The issue is identified",
  monitoring: "A fix is in place",
  maintenance: "Planned maintenance",
};

function localTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function CustomerStatusBanner() {
  const [summary, setSummary] = useState<CustomerStatusSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    void platformApi("/status/summary", { method: "GET" })
      .then((response) => {
        if (!cancelled) setSummary(response as CustomerStatusSummary);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!summary?.incidents?.length) return null;

  return (
    <section
      aria-label="InsightOS service updates"
      aria-live="polite"
      className={`border-b px-4 py-3 md:px-5 xl:px-6 ${
        summary.state === "degraded"
          ? "border-rose-500/30 bg-rose-500/10"
          : "border-amber-500/25 bg-amber-500/10"
      }`}
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-2">
        {summary.incidents.slice(0, 3).map((incident) => (
          <div key={incident.id} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-4">
            <p className="shrink-0 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-200">
              {STATE_LABELS[incident.state]}
            </p>
            <div className="min-w-0 text-sm text-zinc-200">
              <strong className="font-semibold text-white">{incident.title}</strong>
              <span className="ml-2">{incident.message}</span>
              <p className="mt-1 text-xs text-zinc-400">
                Affects {incident.affected_surfaces.map((surface) => surface.label).join(", ")}
                {incident.state === "maintenance" &&
                new Date(incident.starts_at).getTime() > new Date(summary.checked_at).getTime()
                  ? ` · Starts ${localTime(incident.starts_at)}`
                  : ""}
                {incident.ends_at ? ` · Expected through ${localTime(incident.ends_at)}` : ""}
                {` · Updated ${localTime(incident.updated_at)}`}
              </p>
            </div>
          </div>
        ))}
        {summary.incidents.length > 3 ? (
          <p className="text-xs text-zinc-400">
            {summary.incidents.length - 3} more service update
            {summary.incidents.length - 3 === 1 ? "" : "s"} are active.
          </p>
        ) : null}
      </div>
    </section>
  );
}
