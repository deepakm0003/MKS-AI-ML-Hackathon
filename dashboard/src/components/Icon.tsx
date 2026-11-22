/** Inline stroke icons (24px grid, 1.75 stroke) - no icon dependency. */
const PATHS = {
  overview: "M3 13h8V3H3zM13 21h8v-8h-8zM13 3v6h8V3zM3 21h8v-4H3z",
  explorer: "M3 3v18h18M7 15l4-4 3 3 6-7",
  risk: "M12 3l9 16H3zM12 10v4M12 17.5v.5",
  planning: "M4 7h16M4 12h10M4 17h7M17 15l2 2 3-4",
  scenario: "M4 21v-6M4 11V3M12 21v-9M12 8V3M20 21v-4M20 13V3M1 15h6M9 8h6M17 17h6",
  trust: "M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6zM8.5 12l2.5 2.5L16 9.5",
  health: "M3 12h4l2-5 4 10 2-5h6",
  anomaly: "M3 17l5-5 4 3 8-9M18 6h2v2M8 12a1.5 1.5 0 1 0 0 .01",
  filter: "M3 5h18l-7 8v6l-4 2v-8z",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.3-4.3",
  close: "M6 6l12 12M18 6L6 18",
  chevronDown: "M6 9l6 6 6-6",
  chevronLeft: "M15 6l-6 6 6 6",
  menu: "M4 6h16M4 12h16M4 18h16",
  check: "M5 12.5l4.5 4.5L19 7",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  alert: "M12 8v5M12 16.5v.5M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  info: "M12 11v6M12 7.5v.5M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  dot: "M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0",
  arrowUp: "M12 19V5M6 11l6-6 6 6",
  arrowDown: "M12 5v14M6 13l6 6 6-6",
  minus: "M5 12h14",
  palette: "M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.5 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1 0-.8.7-1.5 1.5-1.5H16a5 5 0 0 0 5-5c0-4.4-4-7.8-9-7.8zM7.5 12.5h.01M9.5 8.5h.01M14.5 8.5h.01",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className, title, style }: { name: IconName; size?: number; className?: string; title?: string; style?: Record<string, string | number> }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" className={className} style={style}
      aria-hidden={title ? undefined : true} role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      <path d={PATHS[name]} />
    </svg>
  );
}
