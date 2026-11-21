import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import type { Option } from "./model";

const MAX_RENDER = 250;

export interface MultiSelectProps {
  label: string;
  options: Option[];
  selected: string[];
  onToggle: (value: string) => void;
  onSet: (values: string[]) => void;
  onClear: () => void;
  disabled?: boolean;
}

/** Filter dropdown: searchable checkbox list with live counts (matching series). */
export function MultiSelect({ label, options, selected, onToggle, onSet, onClear, disabled }: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    search.current?.focus();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? options.filter((o) => o.label.toLowerCase().includes(s)) : options;
  }, [options, q]);

  const summary = selected.length === 0 ? "All" : selected.length === 1 ? selected[0] : `${selected.length} selected`;

  return (
    <div className={`ms ${open ? "ms--open" : ""}`} ref={root}>
      <button
        type="button" className={`ms__trigger ${selected.length ? "ms__trigger--active" : ""}`} disabled={disabled}
        aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((o) => !o)}
      >
        <span className="ms__label">{label}</span>
        <span className="ms__value" title={selected.join(", ") || "All"}>{summary}</span>
        <Icon name="chevronDown" size={14} className="ms__chev" />
      </button>
      {open && (
        <div className="ms__panel" role="dialog" aria-label={`${label} filter`}>
          <div className="ms__search">
            <Icon name="search" size={14} />
            <input
              ref={search} value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${label.toLowerCase()}`}
              aria-label={`Search ${label}`}
            />
          </div>
          <ul className="ms__list" id={listId} role="listbox" aria-multiselectable="true" aria-label={label}>
            {filtered.slice(0, MAX_RENDER).map((o) => {
              const on = selected.includes(o.value);
              return (
                <li key={o.value} role="option" aria-selected={on}>
                  <label className={`ms__opt ${o.count === 0 ? "ms__opt--zero" : ""}`}>
                    <input type="checkbox" checked={on} onChange={() => onToggle(o.value)} />
                    <span className="ms__check" aria-hidden>{on && <Icon name="check" size={12} />}</span>
                    <span className="ms__optlabel">{o.label}</span>
                    <span className="ms__count">{o.count.toLocaleString()}</span>
                  </label>
                </li>
              );
            })}
            {filtered.length === 0 && <li className="ms__none">No matches</li>}
            {filtered.length > MAX_RENDER && (
              <li className="ms__none">Showing {MAX_RENDER} of {filtered.length.toLocaleString()} - refine the search</li>
            )}
          </ul>
          <div className="ms__foot">
            <button type="button" className="btn btn--text" onClick={() => onSet(filtered.filter((o) => o.count > 0).map((o) => o.value))}
              disabled={filtered.length === 0 || filtered.length > MAX_RENDER}>
              Select shown
            </button>
            <button type="button" className="btn btn--text" onClick={onClear} disabled={selected.length === 0}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
