import type { ReportSection } from "./types";

type ReportPreviewProps = {
  title: string;
  audienceLabel: string;
  summary: string;
  sections: ReportSection[];
};

export function ReportPreview({
  title,
  audienceLabel,
  summary,
  sections,
}: ReportPreviewProps) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(15,23,42,0.82))] p-6 shadow-[0_18px_55px_rgba(15,23,42,0.36)] md:p-7">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Report preview
          </p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            {title}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">{summary}</p>
        </div>
        <span className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
          {audienceLabel}
        </span>
      </div>

      <div className="mt-6 space-y-5">
        {sections.map((section) => (
          <div
            key={section.title}
            className="rounded-[22px] border border-white/10 bg-white/5 p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-base font-semibold text-white">{section.title}</h4>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {section.summary}
                </p>
              </div>
              {section.metric ? (
                <span className="text-xl font-semibold tracking-[-0.03em] text-white">
                  {section.metric}
                </span>
              ) : null}
            </div>
            {section.visual ? <div className="mt-4">{section.visual}</div> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
