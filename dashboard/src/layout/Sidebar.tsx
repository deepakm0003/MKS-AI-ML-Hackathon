import { NavLink, useLocation } from "react-router-dom";
import { Icon } from "../components/Icon";
import { VIEWS, type ViewDef } from "../routes";

const GROUPS: { key: ViewDef["group"]; label: string }[] = [
  { key: "workspace", label: "Workspace" },
  { key: "data", label: "Data & diagnostics" },
];

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onNavigate }: {
  collapsed: boolean; onToggleCollapse: () => void; mobileOpen: boolean; onNavigate: () => void;
}) {
  const { search } = useLocation();          // keep the global filters when switching views
  return (
    <aside
      className={`sidebar ${collapsed ? "sidebar--collapsed" : ""} ${mobileOpen ? "sidebar--open" : ""}`}
      aria-label="Main navigation"
    >
      <div className="sidebar__brand">
        <span className="brand-mark" aria-hidden>
          <svg viewBox="0 0 32 32" width="32" height="32">
            <rect width="32" height="32" rx="8" fill="var(--surface-3)" />
            <path d="M8 21l5-6 4 4 7-9" stroke="var(--accent)" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="sidebar__brandtext">
          <span className="brand-name">CELERIS</span>
          <span className="brand-sub">Demand Control Tower</span>
        </span>
      </div>

      <nav className="sidebar__nav">
        {GROUPS.map((g) => (
          <div key={g.key} className="navgroup">
            <p className="navgroup__label">{g.label}</p>
            <ul>
              {VIEWS.filter((v) => v.group === g.key).map((v) => (
                <li key={v.path}>
                  <NavLink
                    to={{ pathname: v.path, search }}
                    className={({ isActive }) => `navlink ${isActive ? "navlink--active" : ""}`}
                    title={collapsed ? v.label : undefined}
                    onClick={onNavigate}
                  >
                    <Icon name={v.icon} size={18} className="navlink__icon" />
                    <span className="navlink__text">
                      {v.number && <span className="navlink__num">{v.number}</span>}
                      {v.label}
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <button type="button" className="sidebar__collapse" onClick={onToggleCollapse}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
        <Icon name="chevronLeft" size={16} className={collapsed ? "rot180" : ""} />
        <span className="navlink__text">Collapse</span>
      </button>
    </aside>
  );
}
