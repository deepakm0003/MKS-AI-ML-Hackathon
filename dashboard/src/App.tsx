import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoadingState } from "./components/ui";
import { FilterProvider } from "./filters/FilterContext";
import { AppShell } from "./layout/AppShell";
import { NotFound, ViewPlaceholder } from "./pages/ViewPlaceholder";
import { DEFAULT_PATH, VIEWS } from "./routes";

// chart pages load on demand, so the shell paints before the chart library arrives
const SystemPage = lazy(() => import("./pages/SystemPage").then((m) => ({ default: m.SystemPage })));

export function AppRoutes() {
  return (
    <FilterProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={DEFAULT_PATH} replace />} />
          {VIEWS.map((v) => (
            <Route key={v.path} path={v.path} element={<ViewPlaceholder view={v} />} />
          ))}
          <Route path="/system" element={<Suspense fallback={<LoadingState label="Loading charts" />}><SystemPage /></Suspense>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </FilterProvider>
  );
}
