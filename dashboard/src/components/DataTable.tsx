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

interface DataTableProps<R> {
  columns: Column<R>[];
  rows: R[];
  caption?: string;
  maxHeight?: number;
  initialSort?: { key: string; dir: "asc" | "desc" };
  /** Enable CSV export button */
  exportable?: boolean;
  /** Filename for CSV export (without .csv extension) */
  exportFilename?: string;
}

/**
 * Export rows to CSV file
 */
function exportToCsv<R>(columns: Column<R>[], rows: R[], filename: string) {
  const headers = columns.map((c) => c.label);
  const csvRows = rows.map((r) =>
    columns.map((c) => {
      const v = c.value(r);
      if (v === null || v === undefined) return "";
      // Escape quotes and wrap in quotes
      const str = String(v).replace(/"/g, '""');
      return `"${str}"`;
    }).join(",")
  );
  
  const csv = [headers.join(","), ...csvRows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filename}_${new Date().toISOString().split("T")[0]}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** Sortable, scrollable table with optional CSV export. */
export function DataTable<R>({
  columns,
  rows,
  caption,
  maxHeight = 420,
  initialSort,
  exportable = false,
  exportFilename = "data",
}: DataTableProps<R>) {
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
    <div>
      {exportable && rows.length > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8, paddingRight: 20 }}>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => exportToCsv(columns, sorted, exportFilename)}
            title="Export to CSV"
          >
            <Icon name="download" size={14} />
            Export CSV
          </button>
        </div>
      )}
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
    </div>
  );
}

