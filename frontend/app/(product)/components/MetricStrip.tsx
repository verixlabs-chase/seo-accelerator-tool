import { ProductIcon, type ProductIconName } from "./ProductIcon";
import { TrendIndicator, type TrendTone } from "./TrendIndicator";

export type MetricStripItem = {
  id: string;
  icon: ProductIconName;
  label: string;
  value: string;
  summary?: string;
  changeLabel?: string;
  changeTone?: TrendTone;
};

type MetricStripProps = {
  items: MetricStripItem[];
  label?: string;
};

export function MetricStrip({ items, label = "Key results" }: MetricStripProps) {
  return (
    <section aria-label={label} className="divide-y divide-[#26272c] border-y border-[#26272c] md:grid md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-4">
      {items.map((item) => (
        <div key={item.id} className="flex min-w-0 gap-3 px-1 py-4 md:px-4 first:md:pl-1">
          <ProductIcon name={item.icon} size={19} className="mt-0.5 shrink-0 text-accent-400" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-zinc-400">{item.label}</p>
            <div className="mt-1 flex flex-wrap items-baseline gap-2">
              <p className="text-2xl font-semibold tracking-[-0.04em] text-white">{item.value}</p>
              {item.changeLabel ? (
                <TrendIndicator label={item.changeLabel} tone={item.changeTone} />
              ) : null}
            </div>
            {item.summary ? <p className="mt-1 text-xs leading-5 text-zinc-500">{item.summary}</p> : null}
          </div>
        </div>
      ))}
    </section>
  );
}
