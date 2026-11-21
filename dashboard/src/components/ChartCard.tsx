import { useState, type ReactNode } from "react";
import type { ApiState } from "../api/useApi";
import { Card, EmptyState, ErrorState, Skeleton } from "./ui";

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value}
          className={`segmented__opt ${value === o.value ? "segmented__opt--on" : ""}`} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Card for one chart: handles loading / error / empty from the API state, offers a Chart <-> Table
 * toggle (the accessible table view every chart must have) and a footnote naming the source.
 */
export function ChartCard<T>({ title, subtitle, state, chart, table, controls, footnote, height = 320, isEmpty }: {
  title: string; subtitle?: ReactNode; state: ApiState<T> & { retry?: () => void };
  chart: (data: T) => ReactNode; table: (data: T) => ReactNode; controls?: ReactNode; footnote?: (data: T) => ReactNode;
  height?: number; isEmpty?: (data: T) => boolean;
}) {
  const [mode, setMode] = useState<"chart" | "table">("chart");
  return (
    <Card
      title={title} subtitle={subtitle} className="chartcard"
      actions={
        <div className="chartcard__controls">
          {controls}
          <Segmented label={`${title} view`} value={mode} onChange={setMode}
            options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
        </div>
      }
    >
      <div className="chartcard__body" style={{ minHeight: height }}>
        {state.status === "loading" && <Skeleton height={height} />}
        {state.status === "error" && <ErrorState error={state.error} onRetry={state.retry} />}
        {state.status === "success" && (isEmpty?.(state.data)
          ? <EmptyState title="No data for these filters" message="Widen the global filters to see results." icon="filter" />
          : mode === "chart" ? chart(state.data) : table(state.data))}
      </div>
      {state.status === "success" && footnote && <p className="chartcard__foot">{footnote(state.data)}</p>}
    </Card>
  );
}
