import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoadingState } from "./components/ui";
import { FilterProvider } from "./filters/FilterContext";
import { AppShell } from "./layout/AppShell";
import { NotFound, ViewPlaceholder } from "./pages/ViewPlaceholder";
import { DEFAULT_PATH, VIEWS } from "./routes";

// chart pages load on demand, so the shell paints before the chart library arrives
const SystemPage = lazy(() => import("./pages/SystemPage").then((m) => ({ default: m.SystemPage })));
const ExecutiveOverview = lazy(() => import("./pages/ExecutiveOverview").then((m) => ({ default: m.ExecutiveOverview })));
const DemandExplorer = lazy(() => import("./pages/DemandExplorer").then((m) => ({ default: m.DemandExplorer })));

/** Views that are built; the rest keep their live-readiness placeholder until their phase. */
const BUILT: Record<string, () => JSX.Element> = {
  "/overview": () => <ExecutiveOverview />,
  "/explorer": () => <DemandExplorer />,
};

const lazyPage = (el: JSX.Element) => <Suspense fallback={<LoadingState label="Loading view" />}>{el}</Suspense>;

export function AppRoutes() {
  return (
    <FilterProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={DEFAULT_PATH} replace />} />
          {VIEWS.map((v) => (
            <Route key={v.path} path={v.path} element={BUILT[v.path] ? lazyPage(BUILT[v.path]()) : <ViewPlaceholder view={v} />} />
          ))}
          <Route path="/system" element={lazyPage(<SystemPage />)} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </FilterProvider>
  );
}
