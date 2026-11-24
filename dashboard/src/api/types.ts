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
  /** Only with global filters: "direct" = scope inside the selection, "context" = broader card. */
  match?: "direct" | "context";
}

export interface Recommendations {
  total: number;
  direct: number;
  by_priority: Partial<Record<Priority, number>>;
  cards: RecommendationCard[];
}

export interface PresetResult {
  method: string;
  shocks: Record<string, number>;
  total: ScenarioResult["total"];
  by_family: ScenarioResult["by_family"];
  by_region: ScenarioResult["by_region"];
  planning_risks: ScenarioResult["planning_risks"];
  responses: string[];
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

/* ---------------------------------------------------------------- Demand Explorer (api/explorer.py) */
export interface SeasonalityView {
  filters: Record<string, string[]>;
  by_month: { month: number; label: string; hist_avg_units: number | null; hist_index: number | null;
    forecast_units: number | null; forecast_index: number | null }[];
  years: { year: string; kind: "history" | "forecast"; values: (number | null)[] }[];
  stats: {
    peak_months: string[];
    trough_month: string | null;
    amplitude: number | null;
    zero_month_share_24m: number | null;
    series_with_30pct_zero_months: number;
    series_observed_24m: number;
    demand_classes: Record<string, number>;
    median_order_cycle_months: number | null;
  };
}

export type DrillLevel = "family" | "sku" | "region" | "customer";

export interface DrillRow {
  Member: string;
  Series: number | null;
  Units_last12: number | null;
  Units_next12: number | null;
  Revenue_next12: number | null;
  Units_change_pct: number | null;
  Zero_share_24m: number | null;
  spark_history: (number | null)[];
  spark_forecast: (number | null)[];
  Label?: string | null;
  Lifecycle_Status?: string | null;
  Powertrain?: string | null;
  Launch_Date?: string | null;
  EOL_Date?: string | null;
  Successor_SKU?: string | null;
  Demand_Class?: string;
  Order_cycle_months?: number | null;
  First_Month?: string;
}

export interface DrilldownView {
  level: DrillLevel;
  next_level: DrillLevel | null;
  filters: Record<string, string[]>;
  members: number;
  spark_months: { history: string[]; forecast: string[] };
  rows: DrillRow[];
}

export interface LifecycleEvent {
  type: "LAUNCH" | "EOL";
  sku: string;
  date: string;
  description: string | null;
  related_sku: string | null;
  powertrain: string | null;
  regions: number;
  forecast_units: number | null;
}

export interface LifecycleView {
  filters: Record<string, string[]>;
  skus: number;
  status_counts: Record<string, number>;
  powertrain_counts: Record<string, number>;
  series_age: Record<string, number>;
  events: LifecycleEvent[];
}

export interface SeriesDetail {
  forecast: { Date: string; h: number; Forecast: number; P10: number; P50: number; P90: number; Units_Sold_Forecast: number; method: string }[];
  history?: { Date: string; Units_Sold: number | null; Demand: number | null; Demand_Source: string; Anomaly_Type: string | null }[];
  signals?: Record<string, string | number | boolean | null> | null;
  anomalies: Record<string, string | number | null>[];
  profile?: { Demand_Class: string; Cycle_Last12: number | null; First_Month: string; Months: number; Nonzero_Share_24: number | null;
    ADI: number | null; CV2: number | null; Months_Since_Order: number | null } | null;
  lifecycle?: { Lifecycle_Status: string; Launch_Date: string; EOL_Date: string | null; Replaces_SKU: string | null;
    Successor_SKU: string | null; Powertrain_Application: string; SKU_Description: string; Size_Class: string } | null;
  risk?: Record<string, string | number | null> | null;
}

/* ---------------------------------------------------------------- page aggregations (api/pages.py) */
export interface PlanningView {
  filters: Record<string, string[]>;
  kpis: {
    lines: number; cover_units: number; forecast_units_next3: number; buffer_units: number;
    cover_value_usd: number; buffer_value_usd: number | null; service_level_revenue_weighted: number | null;
    series: number; make_to_order_lines: number | null;
  };
  monthly: { Date: string; Forecast: number; P90: number; Revenue: number }[];
  segments: { Segment: string; ABC: string; XYZ: string; Series: number; Revenue_next12: number; Service_level: number; Revenue_share: number | null }[];
  next_cycle: { total: number; rows: { SKU_ID: string; Region: string; Product_Family: string; Segment: string; Service_level: number;
    Leadtime_P50: number; Leadtime_cover: number; Safety_buffer: number; Cover_value_usd: number }[] };
  segmentation: { total: number; rows: { SKU_ID: string; Region: string; Product_Family: string; Revenue_next12: number; ABC: string;
    XYZ: string; Segment: string; Service_level: number; Planning_approach: string }[] };
  capacity: { Product_Family: string; Region: string; Demonstrated_3m_throughput: number; Peak_3m_load_P50: number;
    Peak_3m_load_P90: number; Utilisation_P50: number; Utilisation_P90: number; Capacity_flag: string;
    First_window_above_throughput: string | null }[];
}

export interface AnomalyRegisterRow {
  Date: string; SKU_ID: string; Region: string; Product_Family: string; Customer_Name?: string; Type: string; Category: string;
  Detection: string; Reason: string; Action: string; Confidence: string; Units_Shipped: number | null; Demand: number | null;
  Expected: number | null;
}

export interface AnomaliesView {
  filters: Record<string, string[]>;
  total: number;
  series_affected: number;
  by_category: Record<string, number>;
  by_type: { type: string; label: string; count: number }[];
  timeline: { Date: string; Demand: number; Shipped: number }[];
  flagged_months: { Date: string; count: number; by_category: Record<string, number> }[];
  single_series: boolean;
  points: { Date: string; Type: string; Category: string; Reason: string; Action: string; Units_Shipped: number | null;
    Demand: number | null; Expected: number | null; Confidence: string }[] | null;
  rows: AnomalyRegisterRow[];
  structural: { total: number; rows: { Type: string; Date: string; SKU_ID: string; Region: string; Detail: string; Evidence: string; Action: string }[] };
}

export interface DataHealthView {
  total: number;
  total_all_files: number;
  rows_affected: number;
  by_issue_type: { issue_type: string; count: number }[];
  by_category: Record<string, number>;
  by_file: Record<string, number>;
  rule_summary: { file: string; category: string; issue_type: string; action: string; rows: number }[];
  before_after: { file: string; rows_before: number; rows_after: number; columns_before: number; columns_after: number;
    null_cells_before: number; null_cells_after: number; nulls_by_column_before: Record<string, number>;
    nulls_by_column_after: Record<string, number> }[];
  rows: { file: string; row_ref: string; date: string; sku_id: string; region: string; issue_type: string; category: string;
    field: string; original: string; corrected: string; action: string; rule: string }[];
}
