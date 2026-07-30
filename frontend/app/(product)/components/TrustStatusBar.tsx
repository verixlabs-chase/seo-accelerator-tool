import type { TrustSignal } from "./types";
import { DataFreshnessBadge } from "./DataFreshnessBadge";

type TrustStatusBarProps = {
  signals: TrustSignal[];
};

export function TrustStatusBar({ signals }: TrustStatusBarProps) {
  const actionableSignals = signals.filter(
    (signal) => signal.tone === "warning" || signal.tone === "danger",
  );
  if (actionableSignals.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 px-5 py-3 md:px-6">
      {actionableSignals.map((signal) => (
        <DataFreshnessBadge
          key={`${signal.label}-${signal.value}`}
          label={signal.label}
          value={signal.value}
          tone={signal.tone ?? "info"}
        />
      ))}
    </div>
  );
}
