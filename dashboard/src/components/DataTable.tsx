import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "./Icon";

export interface Column<R> {
  key: string;
  label: string;
  value: (r: R) => string | number | null | undefined;
  /** Display formatter; defaults to the raw value. */
  render?: (r: R) => ReactNode;
  align?: "left" | "right";
  sortable?: boolean;
}

/** Sortable, scrollable table - also the accessible "table view" of every chart. */
export function DataTable<R>({ columns, rows, caption, maxHeight = 420, initialSort }: {
  columns: Column<R>[]; rows: R[]; caption?: string; maxHeight?: number; initialSort?: { key: string; dir: "asc" | "desc" };
}) {
  const [sort, setSort] = useState(initialSort);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const s = [...rows].sort((a, b) => {
      const x = col.value(a), y = col.value(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return x < y ? -1 : 1;
    });
    return sort.dir === "desc" ? s.reverse() : s;
  }, [rows, columns, sort]);

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));

  return (
    <div className="dtable" style={{ maxHeight }}>
      <table className="table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.align === "right" ? "ta-r" : ""} aria-sort={sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                {c.sortable === false ? c.label : (
                  <button type="button" className="th-sort" onClick={() => toggle(c.key)}>
                    {c.label}
                    {sort?.key === c.key && <Icon name={sort.dir === "asc" ? "arrowUp" : "arrowDown"} size={12} />}
                  </button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === "right" ? "ta-r num" : ""}>{c.render ? c.render(r) : (c.value(r) ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
