import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { ErrorState } from "../components/ui";
import { useFilters } from "./FilterContext";
import { MultiSelect } from "./MultiSelect";
import { DIMS, DIM_LABEL, optionsFor, type Dim, type Option } from "./model";

/** Global filter bar - one row above every view, shared by the history and forecast parts. */
export function FilterBar() {
  const { filters, dispatch, index, status, error, retry, active, matching, total } = useFilters();
  const [copied, setCopied] = useState(false);

  const options = useMemo(() => {
    const out = {} as Record<Dim, Option[]>;
    for (const d of DIMS) out[d] = index ? optionsFor(d, index, filters) : [];
    return out;
  }, [index, filters]);

  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable (insecure context) - the address bar still holds the link */
    }
  };

  if (status === "error" && error) {
    return (
      <div className="filterbar filterbar--error" role="region" aria-label="Global filters">
        <ErrorState error={error} onRetry={retry} compact />
      </div>
    );
  }

  return (
    <div className="filterbar" role="region" aria-label="Global filters">
      <span className="filterbar__icon" aria-hidden><Icon name="filter" size={16} /></span>
      <div className="filterbar__controls">
        {DIMS.map((d) => (
          <MultiSelect
            key={d} label={DIM_LABEL[d]} options={options[d]} selected={filters[d]} disabled={!index}
            onToggle={(value) => dispatch({ type: "toggle", dim: d, value })}
            onSet={(values) => dispatch({ type: "set", dim: d, values })}
            onClear={() => dispatch({ type: "clear", dim: d })}
          />
        ))}
      </div>
      <div className="filterbar__meta">
        <span className="filterbar__count" aria-live="polite">
          {matching === null ? "Loading filters…" : (
            <><strong>{matching.toLocaleString()}</strong> of {total?.toLocaleString()} series</>
          )}
        </span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => dispatch({ type: "clearAll" })} disabled={!active}>
          Clear all{active ? ` (${active})` : ""}
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={share} title="Copy a link to this filtered view">
          <Icon name={copied ? "check" : "link"} size={14} /> {copied ? "Copied" : "Share"}
        </button>
      </div>
    </div>
  );
}
