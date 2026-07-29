"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

type TruthNoticeProps = {
  title: string;
  children: ReactNode;
  tone?: "info" | "warning";
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
  const storageKey = useMemo(
    () =>
      `insightos-guide:${title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")}`,
    [title],
  );
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(window.sessionStorage.getItem(storageKey) !== "dismissed");
  }, [storageKey]);

  function dismiss() {
    window.sessionStorage.setItem(storageKey, "dismissed");
    setIsVisible(false);
  }

  if (!isVisible) {
    return null;
  }

  return (
    <section
      aria-label="Page guidance"
      className={`fixed bottom-4 right-4 z-40 w-[min(24rem,calc(100vw-2rem))] rounded-lg border p-4 shadow-[0_18px_60px_rgba(0,0,0,0.5)] ${toneClassName(tone)}`}
    >
      <div className="flex items-start gap-3">
        <div
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-current/20 bg-black/20 text-sm font-bold"
        >
          i
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-current/75">
            InsightOS guide
          </p>
          <h2 className="mt-1.5 text-base font-semibold text-white">{title}</h2>
          <div className="mt-2 text-sm leading-6 text-current/85">{children}</div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Close page guidance"
          className="-mr-1 -mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md border border-current/15 bg-black/15 text-lg leading-none text-current/80 transition hover:bg-black/30 hover:text-white"
        >
          ×
        </button>
      </div>
    </section>
  );
}
