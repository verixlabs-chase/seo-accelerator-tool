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
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-4 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
      <h3 className="text-base font-semibold tracking-[-0.02em] text-white">{title}</h3>
      <div className="mt-4 overflow-hidden rounded-md border border-[#26272c]">
        <table className="w-full border-collapse text-left">
          <thead className="bg-[#111214]">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-[#26272c]">
                {columns.map((column) => (
                  <td key={`${row.id}-${column.key}`} className="px-4 py-3 text-sm text-zinc-200">
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
