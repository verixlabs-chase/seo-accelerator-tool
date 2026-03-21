import type { ReactNode } from "react";

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
  return (
    <section className={`rounded-md border p-4 shadow-[0_0_30px_rgba(0,0,0,0.25)] ${toneClassName(tone)}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-current/75">
        Product truth
      </p>
      <h2 className="mt-1.5 text-base font-semibold text-white">{title}</h2>
      <div className="mt-2 text-sm leading-6 text-current/85">{children}</div>
    </section>
  );
}
