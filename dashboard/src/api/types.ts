/**
 * Response types of the read-only API (api/app.py), written against the live responses
 * recorded in docs/api_contracts.md (python scripts/document_api.py). Only fields the
 * dashboard reads are typed; anything else stays out until a view needs it.
 */

export interface Health {
  status: string;
  validation: "PASS" | "FAIL" | string;
  selected_model: string;
  frozen_at: string;
}

export interface Kpis {
  selected_model: string;
  selection_reason: string;
  backtest_WAPE: number;
  backtest_bias: number;
  family_month_WAPE: number;
  total_month_WAPE: number;
  forecast_total_19m: number;
  forecast_P10_19m: number;
  forecast_P90_19m: number;
  next12_vs_last12: number;
  validation: string;
  exceptions?: number;
  risk_level_counts?: Record<"LOW" | "MEDIUM" | "HIGH", number>;
  market_headline?: { signal: string; yoy_last3m: number; yoy_last12m: number; forecast_next12_vs_last12: number };
}

export interface DatasetInfo {
  path: string;
  view: string;
  description: string;
  available: boolean;
}
export type DatasetIndex = Record<string, DatasetInfo>;

export interface Paged<T> {
  total: number;
  offset: number;
  rows: T[];
}

/** GET /meta/filters - index-encoded valid combinations for the global filter bar. */
export interface FilterOptions {
  families: string[];
  regions: string[];
  channels: string[];
  customers: string[];
  skus: { id: string; description: string; family: number }[];
  /** [skuIndex, regionIndex, channelIndex, customerIndex] */
  combos: [number, number, number, number][];
  combo_fields: string[];
}

export type Priority = "CRITICAL" | "HIGH" | "MEDIUM";

export interface IntelligenceKpis {
  forecast_model: string;
  history_end: string;
  units_next12: number;
  units_next12_vs_last12: number;
  revenue_next12: number;
  revenue_next12_vs_last12: number;
  units_19m: number;
  units_19m_p10: number;
  units_19m_p90: number;
  revenue_19m: number;
  series: number;
  exceptions: number;
  exceptions_by_priority: Partial<Record<Priority, number>>;
  capacity_flags: Record<string, number>;
  high_supply_risk_family_regions: number;
}

export interface BriefingItem {
  topic: string;
  text: string;
  sources: string[];
}

export interface Briefing {
  kpis: IntelligenceKpis;
  briefing: BriefingItem[];
}

export interface RecommendationCard {
  id: string;
  priority: Priority;
  priority_score: number;
  rule_id: string;
  title: string;
  level: string;
  scope: string;
  owner: string;
  finding: string;
  action: string;
  trade_off: string;
  window: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  impact_usd: number;
  evidence: Record<string, string | number | boolean | null>;
}

export interface Recommendations {
  total: number;
  cards: RecommendationCard[];
}

export interface ScenarioSlider {
  column: string;
  kind: "add" | "mul";
  min: number;
  max: number;
  unit: string;
}

export interface ScenarioConfig {
  sliders: Record<string, ScenarioSlider>;
  presets: Record<string, Record<string, number>>;
  regions: string[];
}

export interface ScenarioBreakdownRow {
  Base: number;
  Scenario: number;
  Base_revenue?: number;
  Scenario_revenue?: number;
  Change_pct: number;
  Change_units: number;
}

export interface ScenarioResult {
  shocks: Record<string, number>;
  region_overlay: Record<string, number>;
  method: string;
  total: {
    base_units: number;
    scenario_units: number;
    change_units: number;
    change_pct: number;
    base_revenue?: number;
    scenario_revenue?: number;
    change_revenue?: number;
  };
  by_family: (ScenarioBreakdownRow & { Product_Family: string })[];
  by_region: (ScenarioBreakdownRow & { Region: string })[];
  by_month: (ScenarioBreakdownRow & { Date: string })[];
  capacity?: { Product_Family: string; Region: string; Utilisation_pct: number }[];
  planning_risks: { type: string; scope: string; [k: string]: string | number }[];
  responses: string[];
}

/* ---------------------------------------------------------------- filter-aware views (api/views.py) */
export interface TimelineHistoryPoint {
  Date: string;
  Units_shipped: number;
  Units_unconstrained: number;
  Revenue_shipped: number;
  Revenue_unconstrained: number;
}

export interface TimelineForecastPoint {
  Date: string;
  Units_forecast: number;
  Revenue_forecast: number;
  Units_P10: number | null;
  Units_P90: number | null;
  Revenue_P10: number | null;
  Revenue_P90: number | null;
}

export interface TimelineSummary {
  series: number;
  forecast_series: number;
  history_end: string | null;
  units_last12: number;
  units_next12: number;
  revenue_last12: number;
  revenue_next12: number;
  units_19m: number;
  units_19m_p10: number;
  units_19m_p90: number;
  revenue_19m: number;
  units_next12_vs_last12: number | null;
  revenue_next12_vs_last12: number | null;
}

export interface TimelineView {
  filters: Record<string, string[]>;
  band_method: string;
  summary: TimelineSummary;
  history: TimelineHistoryPoint[];
  forecast: TimelineForecastPoint[];
}

export interface BreakdownRow {
  Member: string;
  Units_last12: number;
  Revenue_last12: number;
  Units_next12: number;
  Revenue_next12: number;
  Units_change_pct: number | null;
  Revenue_change_pct: number | null;
  Revenue_share_next12: number | null;
}

export interface BreakdownView {
  dim: "family" | "region" | "channel" | "customer" | "sku";
  filters: Record<string, string[]>;
  members: number;
  rows: BreakdownRow[];
}
