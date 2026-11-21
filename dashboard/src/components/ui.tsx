import type { ReactNode } from "react";
import type { ApiError } from "../api/client";
import { Icon, type IconName } from "./Icon";

/* ---------------------------------------------------------------- Card */
export function Card({ title, subtitle, actions, children, className = "", padded = true }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; padded?: boolean;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card__head">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="card__actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? "card__body" : ""}>{children}</div>
    </section>
  );
}

/* ---------------------------------------------------------------- Badge (status = colour + icon + label) */
export type Tone = "neutral" | "accent" | "good" | "warning" | "serious" | "critical";
const TONE_ICON: Partial<Record<Tone, IconName>> = { good: "check", warning: "alert", serious: "alert", critical: "alert" };

export function Badge({ tone = "neutral", children, icon }: { tone?: Tone; children: ReactNode; icon?: IconName | null }) {
  const ic = icon === null ? undefined : icon ?? TONE_ICON[tone];
  return (
    <span className={`badge badge--${tone}`}>
      {ic && <Icon name={ic} size={12} />}
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- loading / empty / error */
export function Skeleton({ lines = 3, height }: { lines?: number; height?: number }) {
  if (height) return <div className="skeleton" style={{ height }} aria-hidden />;
  return (
    <div className="skeleton-stack" aria-hidden>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span className="state__text">{label}…</span>
    </div>
  );
}

export function EmptyState({ title, message, icon = "database" }: { title: string; message?: ReactNode; icon?: IconName }) {
  return (
    <div className="state state--empty">
      <span className="state__icon"><Icon name={icon} size={22} /></span>
      <p className="state__title">{title}</p>
      {message && <p className="state__text">{message}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry, compact = false }: { error: ApiError; onRetry?: () => void; compact?: boolean }) {
  const title = error.status === null ? "API unreachable"
    : error.notGenerated ? "Data not generated yet"
      : `Request failed (${error.status})`;
  return (
    <div className={`state state--error ${compact ? "state--compact" : ""}`} role="alert">
      <span className="state__icon"><Icon name="alert" size={22} /></span>
      <p className="state__title">{title}</p>
      <p className="state__text">{error.message}</p>
      {error.path && <p className="state__meta mono">{error.path}</p>}
      {onRetry && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          <Icon name="refresh" size={14} /> Retry
        </button>
      )}
    </div>
  );
}
