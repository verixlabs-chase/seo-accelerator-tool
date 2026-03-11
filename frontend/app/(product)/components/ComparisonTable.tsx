type ComparisonColumn = {
  key: string;
  label: string;
};

type ComparisonRow = {
  id: string;
  values: Record<string, string>;
};

type ComparisonTableProps = {
  title: string;
  columns: ComparisonColumn[];
  rows: ComparisonRow[];
};

export function ComparisonTable({
  title,
  columns,
  rows,
}: ComparisonTableProps) {
  return (
    <section className="rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] p-5 shadow-[0_18px_55px_rgba(15,23,42,0.36)] md:p-6">
      <h3 className="text-lg font-semibold tracking-[-0.02em] text-white">{title}</h3>
      <div className="mt-5 overflow-hidden rounded-2xl border border-white/10">
        <table className="w-full border-collapse text-left">
          <thead className="bg-white/5">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-white/10">
                {columns.map((column) => (
                  <td key={`${row.id}-${column.key}`} className="px-4 py-3 text-sm text-slate-200">
                    {row.values[column.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
