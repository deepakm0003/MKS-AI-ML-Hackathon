import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoadingState } from "./components/ui";
import { FilterProvider } from "./filters/FilterContext";
import { AppShell } from "./layout/AppShell";
import { NotFound, ViewPlaceholder } from "./pages/ViewPlaceholder";
import { VIEWS } from "./routes";

// chart pages load on demand, so the shell paints before the chart library arrives
const SystemPage = lazy(() => import("./pages/SystemPage").then((m) => ({ default: m.SystemPage })));
const ExecutiveOverview = lazy(() => import("./pages/ExecutiveOverview").then((m) => ({ default: m.ExecutiveOverview })));
const DemandExplorer = lazy(() => import("./pages/DemandExplorer").then((m) => ({ default: m.DemandExplorer })));
const RiskExceptions = lazy(() => import("./pages/RiskExceptions").then((m) => ({ default: m.RiskExceptions })));
const PlanningProcurement = lazy(() => import("./pages/PlanningProcurement").then((m) => ({ default: m.PlanningProcurement })));
const ScenarioLab = lazy(() => import("./pages/ScenarioLab").then((m) => ({ default: m.ScenarioLab })));
const ModelTrust = lazy(() => import("./pages/ModelTrust").then((m) => ({ default: m.ModelTrust })));
const DataHealth = lazy(() => import("./pages/DataHealth").then((m) => ({ default: m.DataHealth })));
const AnomalyMonitor = lazy(() => import("./pages/AnomalyMonitor").then((m) => ({ default: m.AnomalyMonitor })));
const ExceptionList = lazy(() => import("./pages/ExceptionList").then((m) => ({ default: m.ExceptionList })));
const CalendarForecast = lazy(() => import("./pages/CalendarForecast").then((m) => ({ default: m.CalendarForecast })));
const MacroDrivers     = lazy(() => import("./pages/MacroDrivers").then((m) => ({ default: m.MacroDrivers })));
const LandingPage      = lazy(() => import("./pages/LandingPage").then((m) => ({ default: m.LandingPage })));

/** Views that are built; the rest keep their live-readiness placeholder until their phase. */
const BUILT: Record<string, () => JSX.Element> = {
  "/overview": () => <ExecutiveOverview />,
  "/explorer": () => <DemandExplorer />,
  "/risk": () => <RiskExceptions />,
  "/planning": () => <PlanningProcurement />,
  "/scenarios": () => <ScenarioLab />,
  "/trust": () => <ModelTrust />,
  "/data-health": () => <DataHealth />,
  "/anomalies": () => <AnomalyMonitor />,
  "/exceptions": () => <ExceptionList />,
  "/calendar": () => <CalendarForecast />,
  "/macro": () => <MacroDrivers />,
};

const lazyPage = (el: JSX.Element) => <Suspense fallback={<LoadingState label="Loading view" />}>{el}</Suspense>;

export function AppRoutes() {
  return (
    <FilterProvider>
      <Routes>
        {/* Landing page — fullscreen, no sidebar */}
        <Route path="/home" element={lazyPage(<LandingPage />)} />

        <Route element={<AppShell />}>
          {/* Root "/" → Executive Overview (keeps existing tests passing) */}
          <Route index element={<Navigate to="/overview" replace />} />
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
