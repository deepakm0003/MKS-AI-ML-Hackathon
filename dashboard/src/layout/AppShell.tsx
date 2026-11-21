import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { FilterBar } from "../filters/FilterBar";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const COLLAPSE_KEY = "celeris.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Sidebar + header + global filter bar + scrollable analytical workspace. */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch {
      /* storage unavailable - a per-viewer convenience only */
    }
  }, [collapsed]);

  return (
    <div className={`shell ${collapsed ? "shell--collapsed" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <Sidebar
        collapsed={collapsed} onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen} onNavigate={() => setMobileOpen(false)}
      />
      {mobileOpen && <div className="scrim" onClick={() => setMobileOpen(false)} aria-hidden />}
      <div className="shell__main">
        <Header onMenu={() => setMobileOpen(true)} />
        <FilterBar />
        <main id="main" className="workspace" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
