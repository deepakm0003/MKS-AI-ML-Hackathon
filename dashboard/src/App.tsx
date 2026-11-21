import { Navigate, Route, Routes } from "react-router-dom";
import { FilterProvider } from "./filters/FilterContext";
import { AppShell } from "./layout/AppShell";
import { NotFound, ViewPlaceholder } from "./pages/ViewPlaceholder";
import { DEFAULT_PATH, VIEWS } from "./routes";

export function AppRoutes() {
  return (
    <FilterProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={DEFAULT_PATH} replace />} />
          {VIEWS.map((v) => (
            <Route key={v.path} path={v.path} element={<ViewPlaceholder view={v} />} />
          ))}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </FilterProvider>
  );
}
