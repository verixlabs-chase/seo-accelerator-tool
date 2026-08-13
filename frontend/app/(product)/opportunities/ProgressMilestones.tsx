"use client";

import { useEffect, useMemo, useState } from "react";

import { platformApi } from "../../platform/api";
import { ProductIcon } from "../components";


type AchievementEvidence = {
  evidence_type?: string;
  metric_id?: string;
  metric_value?: number | string | null;
  metric_unit?: string | null;
  successful_at?: string | null;
  captured_at?: string | null;
  completed_at?: string | null;
  cadence?: "daily" | "weekly" | "monthly" | "later";
  period_key?: string;
  required_steps_completed?: number;
  active_location_count?: number;
  freshness_window_days?: number;
};

type Achievement = {
  id: string;
  rule_key: string;
  category: "foundation" | "habit" | "verified_result" | "multi_location";
  title: string;
  description: string;
  scope: { type: "location" | "organization"; id: string; label: string };
  evidence: AchievementEvidence[];
  earned_at: string;
  corrected_at?: string | null;
};

type NextMilestone = {
  rule_key: string;
  category: "foundation" | "habit" | "multi_location";
  title: string;
  description: string;
  position: number;
  total: number;
};

type AchievementPreferences = {
  celebrations_enabled: boolean;
  notifications_enabled: boolean;
};

type AchievementSummary = {
  earned_count: number;
  foundation_earned_count: number;
  foundation_total: number;
  habit_earned_count: number;
  habit_total: number;
  multi_location_earned_count: number;
  multi_location_total: number;
  progress_earned_count: number;
  progress_total: number;
  newly_earned: Achievement[];
  achievements: Achievement[];
  next_milestone: NextMilestone | null;
  preferences: AchievementPreferences;
  safety: { verified_result_rewards_enabled: boolean; message: string };
};

type ProgressMilestonesProps = {
  campaignId: string;
};

function formatDate(value?: string | null): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function evidenceLabel(item: AchievementEvidence): string {
  if (item.evidence_type === "location_setup") {
    return "Business details and service area saved";
  }
  if (item.evidence_type === "successful_data_sync") {
    return `Successful update received ${formatDate(item.successful_at)}`;
  }
  if (item.evidence_type === "governed_baseline") {
    const readableMetric = String(item.metric_id || "starting measurement")
      .replace(/[._]/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
    const value = item.metric_value ?? "saved";
    return `${readableMetric}: ${value}${item.metric_unit ? ` ${item.metric_unit}` : ""}`;
  }
  if (item.evidence_type === "checklist_completion") {
    const cadence = item.cadence === "monthly" ? "Monthly" : "Weekly";
    const steps = item.required_steps_completed || 0;
    return `${cadence} checklist finished with ${steps} required ${steps === 1 ? "step" : "steps"}`;
  }
  if (item.evidence_type === "portfolio_location_setup") {
    const count = item.active_location_count || 0;
    return `${count} active ${count === 1 ? "location is" : "locations are"} ready to measure`;
  }
  if (item.evidence_type === "portfolio_data_current") {
    const count = item.active_location_count || 0;
    return `${count} active ${count === 1 ? "location has" : "locations have"} a recent successful update`;
  }
  return "Saved business evidence";
}

function categoryLabel(category: Achievement["category"]): string {
  if (category === "verified_result") return "Result verified";
  if (category === "multi_location") return "Team milestone";
  if (category === "habit") return "Healthy habit";
  return "Foundation";
}

export function ProgressMilestones({ campaignId }: ProgressMilestonesProps) {
  const [summary, setSummary] = useState<AchievementSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dismissedCelebration, setDismissedCelebration] = useState(false);
  const [savingPreferences, setSavingPreferences] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setDismissedCelebration(false);
    platformApi(
      `/engagement/achievements/evaluate?campaign_id=${encodeURIComponent(campaignId)}`,
      { method: "POST" },
    )
      .then((payload) => {
        if (active) setSummary(payload as AchievementSummary);
      })
      .catch(() => {
        if (active) setError("Progress could not be checked right now.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [campaignId]);

  const activeAchievements = useMemo(
    () => (summary?.achievements || []).filter((item) => !item.corrected_at),
    [summary?.achievements],
  );
  const celebration = summary?.newly_earned?.[0] || null;
  const showCelebration = Boolean(
    celebration && summary?.preferences.celebrations_enabled && !dismissedCelebration,
  );

  async function savePreferences(next: AchievementPreferences) {
    if (!summary || savingPreferences) return;
    const previous = summary.preferences;
    setSummary({ ...summary, preferences: next });
    setSavingPreferences(true);
    try {
      const response = await platformApi("/engagement/achievement-preferences", {
        method: "PATCH",
        body: JSON.stringify(next),
      });
      setSummary((current) =>
        current
          ? {
              ...current,
              preferences: (response?.preferences || next) as AchievementPreferences,
            }
          : current,
      );
    } catch {
      setSummary((current) => (current ? { ...current, preferences: previous } : current));
      setError("That preference could not be saved. Try again.");
    } finally {
      setSavingPreferences(false);
    }
  }

  if (loading) {
    return (
      <section aria-label="Progress milestones" className="rounded-md border border-[#26272c] bg-[#141518] p-4">
        <p className="text-sm text-zinc-400">Checking your progress...</p>
      </section>
    );
  }

  if (!summary) {
    return error ? (
      <p role="status" className="rounded-md border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100">
        {error}
      </p>
    ) : null;
  }

  const percent = Math.min(
    100,
    Math.round((summary.progress_earned_count / Math.max(summary.progress_total, 1)) * 100),
  );

  return (
    <section aria-labelledby="progress-milestones-title" className="space-y-3">
      {showCelebration && celebration ? (
        <div
          role="status"
          className="flex items-start justify-between gap-4 rounded-md border border-emerald-500/25 bg-emerald-500/10 p-4"
        >
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-500 text-[#07130d]">
              <ProductIcon name="check" size={18} />
            </span>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-emerald-200/80">
                Milestone earned
              </p>
              <p className="mt-1 font-semibold text-white">{celebration.title}</p>
              <p className="mt-1 text-sm leading-5 text-emerald-50/80">{celebration.description}</p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Dismiss milestone message"
            onClick={() => setDismissedCelebration(true)}
            className="rounded px-2 py-1 text-lg leading-none text-emerald-100/70 hover:bg-emerald-500/15 hover:text-white"
          >
            ×
          </button>
        </div>
      ) : null}

      <details className="rounded-md border border-[#26272c] bg-[#141518] shadow-[0_0_24px_rgba(0,0,0,0.25)]">
        <summary className="cursor-pointer list-none p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-accent-500/20 bg-accent-500/10 text-accent-300">
                <ProductIcon name="spark" size={18} />
              </span>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                  Progress you earned
                </p>
                <h2 id="progress-milestones-title" className="mt-1 text-base font-semibold text-white">
                  {summary.progress_earned_count} of {summary.progress_total} milestones earned
                </h2>
                <p className="mt-1 text-xs text-zinc-500">
                  Setup {summary.foundation_earned_count}/{summary.foundation_total}
                  <span aria-hidden="true"> · </span>
                  Healthy habits {summary.habit_earned_count}/{summary.habit_total}
                  {summary.multi_location_total > 0 ? (
                    <>
                      <span aria-hidden="true"> · </span>
                      All-location progress {summary.multi_location_earned_count}/{summary.multi_location_total}
                    </>
                  ) : null}
                </p>
              </div>
            </div>
            <div className="min-w-52 flex-1 sm:max-w-sm">
              <div className="h-2 overflow-hidden rounded-full bg-[#292a30]">
                <div
                  className="h-full rounded-full bg-emerald-500"
                  style={{ width: `${percent}%` }}
                  aria-hidden="true"
                />
              </div>
              <p className="mt-2 text-right text-xs text-zinc-400">
                {summary.next_milestone ? `Next: ${summary.next_milestone.title}` : "Current milestones complete"}
              </p>
            </div>
          </div>
        </summary>

        <div className="border-t border-[#303137] p-4">
          {summary.next_milestone ? (
            <div className="rounded-md border border-accent-500/20 bg-accent-500/5 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-accent-300">
                {summary.next_milestone.category === "multi_location"
                  ? "Next all-location milestone"
                  : summary.next_milestone.category === "habit"
                    ? "Next healthy habit"
                    : "Your next milestone"}
              </p>
              <h3 className="mt-2 font-semibold text-white">{summary.next_milestone.title}</h3>
              <p className="mt-1 text-sm leading-6 text-zinc-300">{summary.next_milestone.description}</p>
            </div>
          ) : (
            <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm leading-6 text-emerald-50/85">
              Your current milestones are complete. Improvement milestones will appear only after a fresh measurement proves the result.
            </div>
          )}

          {activeAchievements.length > 0 ? (
            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              {activeAchievements.map((achievement) => (
                <article key={achievement.id} className="rounded-md border border-[#303137] bg-[#111214] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-emerald-300">
                      <ProductIcon name="check" size={14} />
                    </span>
                    <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                      {categoryLabel(achievement.category)}
                    </span>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-white">{achievement.title}</h3>
                  <p className="mt-1 text-xs leading-5 text-zinc-400">{achievement.description}</p>
                  <p className="mt-3 text-xs text-zinc-500">
                    {achievement.scope.label} · {formatDate(achievement.earned_at)}
                  </p>
                  <p className="mt-2 border-t border-[#292a30] pt-2 text-xs leading-5 text-zinc-300">
                    Proof: {evidenceLabel(achievement.evidence[0] || {})}
                  </p>
                </article>
              ))}
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#303137] pt-4">
            <p className="max-w-xl text-xs leading-5 text-zinc-500">
              Progress is tied to saved business evidence. Completing a checklist alone never claims that results improved.
            </p>
            <div className="flex flex-wrap gap-4 text-xs text-zinc-300">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={summary.preferences.celebrations_enabled}
                  disabled={savingPreferences}
                  onChange={(event) =>
                    void savePreferences({
                      ...summary.preferences,
                      celebrations_enabled: event.target.checked,
                    })
                  }
                  className="accent-orange-500"
                />
                Show milestone messages
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={summary.preferences.notifications_enabled}
                  disabled={savingPreferences}
                  onChange={(event) =>
                    void savePreferences({
                      ...summary.preferences,
                      notifications_enabled: event.target.checked,
                    })
                  }
                  className="accent-orange-500"
                />
                Allow progress reminders
              </label>
            </div>
          </div>
          {error ? <p role="status" className="mt-3 text-xs text-amber-200">{error}</p> : null}
        </div>
      </details>
    </section>
  );
}
