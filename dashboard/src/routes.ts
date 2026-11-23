import type { IconName } from "./components/Icon";

/**
 * Every planned view. `covers` maps each view to the problem statement's required views
 * and optional views; `sources` lists the contract datasets / endpoints that will feed it.
 */
export interface ViewDef {
  path: string;
  number?: string;
  label: string;
  icon: IconName;
  group: "workspace" | "data";
  purpose: string;
  questions: string[];
  covers: { required: string[]; optional: string[] };
  sources: string[];
  phase: number;
}

export const VIEWS: ViewDef[] = [
  {
    path: "/overview", number: "01", label: "Executive Overview", icon: "overview", group: "workspace", phase: 3,
    purpose: "Revenue, demand, forecast, business signals and critical alerts on one screen.",
    questions: ["How much demand do we expect?", "How much revenue will it generate?", "Is demand increasing or decreasing?",
      "What could go wrong?", "What should I do now?"],
    covers: { required: ["Executive overview", "Revenue forecast"], optional: [] },
    sources: ["intelligence_report", "timeline", "mix", "forecast_hierarchy", "recommendations", "scenario_presets"],
  },
  {
    path: "/explorer", number: "02", label: "Demand Explorer", icon: "explorer", group: "workspace", phase: 5,
    purpose: "History and forecast on one continuous timeline, drill-down family → SKU → region → customer.",
    questions: ["How does the forecast continue the history?", "What is the seasonality and how many zero months?",
      "Where is each SKU in its lifecycle?"],
    covers: { required: ["Demand explorer", "History vs forecast", "Revenue forecast"], optional: ["Lifecycle intelligence"] },
    sources: ["history", "forecast_detail", "demand_signals", "series_risk", "price_book"],
  },
  {
    path: "/risk", number: "03", label: "Risk & Exceptions", icon: "risk", group: "workspace", phase: 6,
    purpose: "Ranked exceptions, capacity risks, fragile supply and forecast anomalies.",
    questions: ["Which items need a decision now?", "Where will demand exceed demonstrated throughput?",
      "Which supply bases are fragile?"],
    covers: { required: [], optional: ["Ranked exception list", "Capacity planning", "Stockouts & lost sales"] },
    sources: ["exceptions_ranked", "recommendations", "capacity_check", "supply_risk", "series_risk"],
  },
  {
    path: "/planning", number: "04", label: "Planning & Procurement", icon: "planning", group: "workspace", phase: 7,
    purpose: "P90 procurement plan, calibrated lead-time buffers, ABC-XYZ policy and recommended actions.",
    questions: ["What should we order this cycle?", "How much buffer does each segment need?", "Who owns which action?"],
    covers: { required: [], optional: ["Procurement planning using P90", "ABC-XYZ segmentation"] },
    sources: ["procurement_plan", "procurement_next_cycle", "segmentation", "recommendations"],
  },
  {
    path: "/scenarios", number: "05", label: "Scenario Lab", icon: "scenario", group: "workspace", phase: 8,
    purpose: "Change macro assumptions and see demand, revenue and planning risks respond instantly.",
    questions: ["What if PMI falls 3 points?", "Which families and regions are most exposed?", "What should we do about it?"],
    covers: { required: [], optional: ["What-if scenarios"] },
    sources: ["POST /scenario", "/scenario/config", "scenario_presets", "emulator_validation"],
  },
  {
    path: "/trust", number: "06", label: "Model Trust", icon: "trust", group: "workspace", phase: 9,
    purpose: "Accuracy, backtests, uncertainty calibration, experiment registry and methodology.",
    questions: ["How accurate is the forecast, by family, region and horizon?", "Are the P10–P90 bands calibrated?",
      "Why this model?"],
    covers: { required: ["Forecast & accuracy"], optional: [] },
    sources: ["backtest_metrics", "experiment_registry", "band_coverage", "interval_reliability", "horizon_reliability", "manifest"],
  },
  {
    path: "/data-health", label: "Data Health", icon: "health", group: "data", phase: 9,
    purpose: "Issues by type and file, rows affected, before vs after cleaning.",
    questions: ["What was wrong with the raw ERP extract?", "What did cleaning change, and why?"],
    covers: { required: ["Data health"], optional: [] },
    sources: ["dq_issue_log", "dq_report", "run_report"],
  },
  {
    path: "/anomalies", label: "Anomaly Monitor", icon: "anomaly", group: "data", phase: 9,
    purpose: "Flagged points on the time series with type, reason and the action taken.",
    questions: ["Which months were errors and which were real events?", "How was unconstrained demand recovered?"],
    covers: { required: ["Anomaly monitor"], optional: ["Stockouts & lost sales"] },
    sources: ["anomaly_register", "structural_register", "event_impact", "history"],
  },
  {
    path: "/exceptions", label: "Exception List", icon: "risk", group: "workspace", phase: 9,
    purpose: "All actionable exceptions with filters by priority and owner, sortable and exportable to CSV.",
    questions: ["What needs my immediate attention?", "Which exceptions are assigned to procurement?", "How much revenue is at risk?"],
    covers: { required: [], optional: ["Exception list for planners", "Data download"] },
    sources: ["recommendations", "exceptions_ranked"],
  },
  {
    path: "/calendar", label: "Calendar Forecast", icon: "calendar", group: "workspace", phase: 9,
    purpose: "Select any date range within the 19-month horizon and explore demand, revenue, insights and procurement requirements for that period.",
    questions: ["What is the forecast for Q1 2027?", "How does demand build month by month?", "Which families drive the next 6 months?"],
    covers: { required: [], optional: ["What-if scenarios", "Data download"] },
    sources: ["forecast_detail", "timeline", "breakdown", "recommendations", "series_signals"],
  },
  {
    path: "/macro", label: "Macro Drivers", icon: "explorer", group: "workspace", phase: 9,
    purpose: "Lead/lag heatmap: which macro indicator leads which product family, by how many months, and whether the lag is stable.",
    questions: ["Which indicator leads Electrical Assemblies?", "Is the auto-production lag stable over time?", "How fast is EV share growing?"],
    covers: { required: [], optional: ["macro lead/lag heatmap"] },
    sources: ["lead_lag", "best_lags", "lag_stability", "ev_shift"],
  },
];

export const DEFAULT_PATH = "/overview";
