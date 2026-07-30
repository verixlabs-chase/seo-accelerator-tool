"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { platformApi } from "../../platform/api";
import { useLocationContext } from "./LocationContext";

type TruthNoticeProps = {
  title: string;
  children: ReactNode;
  tone?: "info" | "warning";
};

type DailyGuide = {
  summary: string;
  generatedByAi: boolean;
};

type BriefResponse = {
  item?: {
    status?: string;
    output?: {
      summary?: string;
    };
  } | null;
};

function toneClassName(tone: TruthNoticeProps["tone"]) {
  if (tone === "info") {
    return "border-sky-500/20 bg-sky-500/10 text-sky-50";
  }

  return "border-amber-500/20 bg-amber-500/10 text-amber-50";
}

export function TruthNotice({
  title,
  children,
  tone = "warning",
}: TruthNoticeProps) {
  const { selectedCampaignId } = useLocationContext();
  const today = new Date().toISOString().slice(0, 10);
  const storageKey = useMemo(
    () => `insightos-guide-dismissed:${selectedCampaignId || "setup"}:${today}`,
    [selectedCampaignId, today],
  );
  const cacheKey = useMemo(
    () => `insightos-daily-guide:${selectedCampaignId}:${today}`,
    [selectedCampaignId, today],
  );
  const [isVisible, setIsVisible] = useState(false);
  const [dailyGuide, setDailyGuide] = useState<DailyGuide | null>(null);

  useEffect(() => {
    setIsVisible(window.sessionStorage.getItem(storageKey) !== "dismissed");
  }, [storageKey]);

  useEffect(() => {
    if (!selectedCampaignId) {
      setDailyGuide(null);
      return;
    }

    const cached = window.localStorage.getItem(cacheKey);
    if (cached) {
      try {
        setDailyGuide(JSON.parse(cached) as DailyGuide);
        return;
      } catch {
        window.localStorage.removeItem(cacheKey);
      }
    }

    let cancelled = false;
    void platformApi(
      `/intelligence/brief?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
      {
        method: "POST",
        body: JSON.stringify({ retry_failed: false }),
      },
    )
      .then((response) => {
        if (cancelled) {
          return;
        }
        const normalized = response as BriefResponse;
        const output = normalized?.item?.output;
        if (
          normalized?.item?.status === "validated" &&
          typeof output?.summary === "string" &&
          output.summary.trim()
        ) {
          const guide = {
            summary: shorten(output.summary, 260),
            generatedByAi: true,
          };
          window.localStorage.setItem(cacheKey, JSON.stringify(guide));
          setDailyGuide(guide);
          return;
        }

        const fallback = { summary: "", generatedByAi: false };
        window.localStorage.setItem(cacheKey, JSON.stringify(fallback));
        setDailyGuide(fallback);
      })
      .catch(() => {
        if (!cancelled) {
          setDailyGuide({ summary: "", generatedByAi: false });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, selectedCampaignId]);

  function dismiss() {
    window.sessionStorage.setItem(storageKey, "dismissed");
    setIsVisible(false);
  }

  if (!isVisible) {
    return null;
  }

  return (
    <section
      aria-label="Daily guidance"
      className={`fixed bottom-4 right-4 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-lg border p-3.5 shadow-[0_18px_60px_rgba(0,0,0,0.5)] ${toneClassName(tone)}`}
    >
      <div className="flex items-start gap-3">
        <div
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-current/20 bg-black/20 text-sm font-bold"
        >
          1
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-current/75">
            Today&apos;s focus
          </p>
          <h2 className="mt-1 text-sm font-semibold text-white">
            {dailyGuide?.generatedByAi ? "Your current priority" : title}
          </h2>
          <div className="mt-1.5 text-sm leading-5 text-current/85">
            {dailyGuide?.generatedByAi ? dailyGuide.summary : children}
          </div>
          {dailyGuide?.generatedByAi ? (
            <Link
              href="/opportunities"
              className="mt-2.5 inline-flex text-xs font-semibold text-white underline decoration-current/40 underline-offset-4 hover:decoration-current"
            >
              See the recommended next step
            </Link>
          ) : null}
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Close daily guidance"
          className="-mr-1 -mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md border border-current/15 bg-black/15 text-lg leading-none text-current/80 transition hover:bg-black/30 hover:text-white"
        >
          ×
        </button>
      </div>
    </section>
  );
}

function shorten(value: string, maxLength: number) {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
}
