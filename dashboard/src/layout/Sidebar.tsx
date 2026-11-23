import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { VIEWS, type ViewDef } from "../routes";

const GROUPS: { key: ViewDef["group"]; label: string }[] = [
  { key: "workspace", label: "Workspace" },
  { key: "data", label: "Data & diagnostics" },
];

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onNavigate }: {
  collapsed: boolean; onToggleCollapse: () => void; mobileOpen: boolean; onNavigate: () => void;
}) {
  const { search } = useLocation();
  const navigate   = useNavigate();

  return (
    <aside
      className={`sidebar ${collapsed ? "sidebar--collapsed" : ""} ${mobileOpen ? "sidebar--open" : ""}`}
      aria-label="Main navigation"
    >
      <button
        type="button"
        className="sidebar__brand"
        onClick={() => navigate("/home")}
        title="Back to home"
        style={{ background: "transparent", border: "none", cursor: "pointer", width: "100%", textAlign: "left" }}
      >
        <span className="brand-mark" aria-hidden>
          <svg viewBox="0 0 32 32" width="28" height="28">
            <rect width="32" height="32" rx="6" fill="#141414" />
            <path d="M7 22l5-7 4 5 4-6 5-5" stroke="#c7ff32" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="sidebar__brandtext">
          <span className="brand-name">CELERIS</span>
          <span className="brand-sub">Demand Control Tower</span>
        </span>
      </button>

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
