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
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#26272c] pb-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Report preview
          </p>
          <h3 className="mt-1.5 text-xl font-semibold tracking-[-0.03em] text-white">
            {title}
          </h3>
          <p className="mt-1.5 text-sm leading-5 text-zinc-300">{summary}</p>
        </div>
        <span className="rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200">
          {audienceLabel}
        </span>
      </div>

      <div className="mt-4 space-y-4">
        {sections.map((section) => (
          <div
            key={section.title}
            className="rounded-md border border-[#26272c] bg-[#111214] p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-base font-semibold text-white">{section.title}</h4>
                <p className="mt-1.5 text-sm leading-5 text-zinc-300">
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
