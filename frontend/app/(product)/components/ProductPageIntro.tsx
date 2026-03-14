type ProductPageIntroProps = {
  eyebrow: string;
  title: string;
  summary: string;
};

export function ProductPageIntro({
  eyebrow,
  title,
  summary,
}: ProductPageIntroProps) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {eyebrow}
      </p>
      <h1 className="mt-2 text-4xl font-bold tracking-[-0.05em] text-white md:text-[3.25rem]">
        {title}
      </h1>
      <p className="mt-2.5 max-w-3xl text-sm leading-6 text-zinc-300 md:text-base">
        {summary}
      </p>
    </div>
  );
}
