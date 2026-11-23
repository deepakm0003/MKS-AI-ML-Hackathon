import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./App";
import { FUTURE } from "./router";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/shell.css";
import "./styles/components.css";

// Send first-time visitors straight to the landing page.
// Tests use MemoryRouter with an explicit initialEntry so they are unaffected.
if (window.location.pathname === "/") {
  window.history.replaceState(null, "", "/home");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter future={FUTURE}>
      <AppRoutes />
    </BrowserRouter>
  </StrictMode>,
);
