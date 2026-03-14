type LoadingCardProps = {
  title?: string;
  summary: string;
};

export function LoadingCard({
  title = "Loading",
  summary,
}: LoadingCardProps) {
  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 text-sm text-zinc-300 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {title}
      </p>
      <p className="mt-2 leading-6">{summary}</p>
    </section>
  );
}
