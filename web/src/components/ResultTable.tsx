import type { QueryResult } from "../contract";
import { formatCell } from "../format";

export function ResultTable({ result }: { result: QueryResult }) {
  const { columns, rows } = result;
  if (rows.length === 0) {
    return <p className="px-1 py-6 text-center text-sm text-muted">The query ran and returned no rows.</p>;
  }
  return (
    <div className="max-h-[420px] overflow-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 z-10 w-10 border-b border-line bg-surface-2 px-2 py-2 text-right font-mono text-[11px] font-normal text-muted"
            >
              #
            </th>
            {columns.map((c) => (
              <th
                key={c.name}
                scope="col"
                className={`sticky top-0 z-10 whitespace-nowrap border-b border-line bg-surface-2 px-3 py-2 text-[12px] font-semibold text-ink-2 ${
                  c.kind === "number" ? "text-right" : "text-left"
                }`}
              >
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-line/70 last:border-0 even:bg-surface-2/40 hover:bg-accent-soft/50">
              <td className="px-2 py-1.5 text-right font-mono text-[11px] text-muted">{i + 1}</td>
              {columns.map((c, j) => {
                const value = row[j] ?? null;
                return (
                  <td
                    key={c.name}
                    className={`whitespace-nowrap px-3 py-1.5 ${c.kind === "number" ? "text-right font-mono text-[12.5px]" : "text-left"} ${
                      value === null ? "text-muted" : "text-ink"
                    }`}
                  >
                    {value === null ? <span className="text-[11px] italic">null</span> : formatCell(value, c.kind, c.name)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
