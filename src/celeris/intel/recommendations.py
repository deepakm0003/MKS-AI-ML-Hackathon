"""Recommendation engine - one action card per exception, filled only from its evidence.

PLAYBOOK holds, per rule: a title, the owning function, a finding sentence, the recommended
action, its trade-off and the decision window. Templates reference evidence fields only, so
every number on a card is a computed value (forecast, backtest, history, price book). An LLM
can later rephrase the cards; it never supplies the numbers.
"""
from __future__ import annotations

import pandas as pd

PLAYBOOK = {
    "CAPACITY_ABOVE_THROUGHPUT": dict(
        title="Forecast load above demonstrated throughput",
        owner="Production planning",
        finding=("{family} in {region}: the 3-month forecast load peaks at {load_p50} units (window ending "
                 "{peak_window}), {util_p50}% of the highest 3-month volume shipped in the last 3 years "
                 "({throughput}); P90 load {load_p90} units ({util_p90}%). First window above it ends "
                 "{first_window}; {capacity_tooling_shortages_36m} capacity/tooling shortages in 36 months."),
        action=("Confirm line capacity for about {excess_units} extra units per 3 months before {first_window}: "
                "plan extra shifts or pre-build in the preceding low-load months, and lock supplier "
                "commitments for the peak window."),
        trade_off="Pre-building ties up working capital; not acting risks repeating past capacity shortages.",
        window="decide at least 3 months before {first_window}"),
    "CAPACITY_TIGHT": dict(
        title="Capacity tight with a shortage history",
        owner="Production planning",
        finding=("{family} in {region}: forecast load reaches {util_p50}% of demonstrated throughput "
                 "({util_p90}% at P90), and the family-region had {capacity_tooling_shortages_36m} "
                 "capacity/tooling shortages in the last 36 months."),
        action="Keep flexible capacity (overtime option, alternate line) reserved for the window ending {peak_window}.",
        trade_off="A reserved option costs little; an unplanned shortage costs lost sales.",
        window="before the window ending {peak_window}"),
    "SUPPLY_RISK_ON_GROWING_DEMAND": dict(
        title="Growing demand on a fragile supply base",
        owner="Procurement",
        finding=("{family} in {region} grows {outlook_pct}% next 12 months, but had {shortages_36m} shortage "
                 "months in 36 months (mostly {dominant_reason}), {lost_units_36m} lost units and a "
                 "{fill_rate}% average fill rate in those months."),
        action=("Raise safety stock to the segment's service level, qualify a second source or expedite option "
                "for the dominant cause, and review supplier performance before the next order release."),
        trade_off="Higher buffer and dual sourcing add cost; ${revenue_next3} of revenue is due in the next 3 months.",
        window="next procurement cycle (release now)"),
    "SEGMENT_OUTPACING_MARKET": dict(
        title="Segment outpacing the market",
        owner="Demand planning / S&OP",
        finding=("{member} ({segment_level}): outlook {outlook_pct}% next 12 months, {outlook_vs_market} pts above the "
                 "market; recent orders {momentum_vs_market} pts vs market; peak months {peak_months}."),
        action="Prioritise allocation and capacity for this segment in the next S&OP cycle; confirm the outlook with sales.",
        trade_off="Allocating ahead of demand risks surplus if the trend fades; the forecast already includes it.",
        window="next S&OP cycle"),
    "SEGMENT_LAGGING_MARKET": dict(
        title="Segment lagging the market",
        owner="Demand planning / Sales",
        finding=("{member} ({segment_level}): recent orders {momentum_vs_market} pts and outlook {outlook_vs_market} pts "
                 "vs the market (outlook {outlook_pct}%)."),
        action="Hold replenishment at the forecast (no upside buffer) and review the account / market position with sales.",
        trade_off="Lean buffers save inventory; recheck if orders recover.",
        window="next S&OP cycle"),
    "FORECAST_VS_MOMENTUM_CONFLICT": dict(
        title="Forecast and recent orders disagree",
        owner="Demand planning",
        finding=("{member}: the forecast is {outlook_vs_market} pts vs the market while recent orders run "
                 "{momentum_vs_market} pts vs the market."),
        action="Run a demand review with sales before releasing orders; plan to the forecast but watch the next 2 months of orders.",
        trade_off="Overriding the model without evidence lowers accuracy (backtested); a review is cheap.",
        window="before the next order release"),
    "EV_SHIFT": dict(
        title="Demand shifting from ICE to EV",
        owner="S&OP / Product management",
        finding=("EV SKUs grow {ev_outlook}% next 12 months (share {ev_share_last12}% -> {ev_share_next12}%) while "
                 "ICE SKUs change {ice_outlook}% (share {ice_share_last12}% -> {ice_share_next12}%)."),
        action="Shift capacity and procurement toward EV SKUs; set last-time-buy and run-down rules for declining ICE SKUs.",
        trade_off="EV ramp risk vs ICE stranded inventory; revenue next 12 m: EV ${ev_revenue_next12}, ICE ${ice_revenue_next12}.",
        window="next quarterly plan"),
    "SKU_DEMAND_SURGE": dict(
        title="Demand surge",
        owner="Procurement / Production planning",
        finding=("{sku} in {region} ({family}): orders +{growth_3m}% (3 m) and +{growth_6m}% (6 m) YoY, "
                 "{vs_family} pts above its family and unusual for this series (z = {z}); forecast "
                 "{forecast_change}% vs last 12 months."),
        action=("Secure supply for {cover_next3} units over the next 3 months (P{service_level} lead-time cover; "
                "forecast {fc_next3}, buffer {buffer_next3}) and review the allocation for the next 3 months."),
        trade_off="Buffer stock if the surge fades vs lost sales if it holds.",
        window="release now"),
    "SKU_DEMAND_DECLINE": dict(
        title="Demand decline",
        owner="Procurement / Sales",
        finding="{sku} in {region}: recent orders {growth_3m}% YoY; forecast {forecast_change}% vs last 12 months.",
        action="Cut replenishment to the forecast ({fc_next3} units next 3 months) and confirm the outlook with the customer ({customer}).",
        trade_off="Lower stock frees cash; confirm before cutting below the forecast.",
        window="next order release"),
    "FORECAST_ANOMALY": dict(
        title="Forecast breaks with recent actuals",
        owner="Demand planning",
        finding=("{sku} in {region}: next-3-month forecast {fc_next3} vs {actual_last3} actual in the last 3 "
                 "months ({jump_3m}%); next 12 months {forecast_change}% vs last 12."),
        action="Validate this forecast before releasing orders (check customer plans and recent order entry).",
        trade_off="A short review avoids ordering on a possible model artefact.",
        window="before the next order release"),
    "HIGH_RISK_HIGH_VALUE": dict(
        title="High-value forecast with low confidence",
        owner="Demand planning",
        finding=("{sku} in {region} (segment {segment}): risk score {risk_score}, backtest WAPE {backtest_wape}%; "
                 "next 12 months likely between {band_low} and {band_high} units; main risk driver: {top_risk_driver}."),
        action="Plan to the P{service_level} lead-time cover ({cover_next3} units next 3 months) and review this item every cycle.",
        trade_off="Buffer cost vs service on an A-class item.",
        window="every planning cycle"),
    "UNSTABLE_RAMP_UP": dict(
        title="Unstable ramp-up of a young series",
        owner="Demand planning",
        finding="{sku} in {region}: {history_months} months of history, last-6-month CV {ramp_cv}.",
        action="Plan to the lead-time cover ({cover_next3} units next 3 months) and compare actuals with the forecast monthly.",
        trade_off="Young series carry the largest forecast errors (backtest).",
        window="monthly"),
    "NEW_LAUNCH_READINESS": dict(
        title="New launch in the forecast window",
        owner="Product management / Production planning",
        finding="{sku} launches {launch} in {region}, replacing {predecessor}; forecast {fc_next12} units in the first 12 forecast months.",
        action="Build launch stock to the ramp-up curve and align the run-down of {predecessor}; track weekly orders after launch.",
        trade_off="Launch stock vs stock-outs at launch; no history, so confidence is low.",
        window="before {launch}"),
    "EOL_RUNDOWN": dict(
        title="End of life in the forecast window",
        owner="Procurement",
        finding="{sku} in {region} reaches EOL {eol}; forecast until then is in the plan.",
        action="Buy only to the forecast, no safety stock; place the last-time buy 3 months before {eol}.",
        trade_off="Stranded stock after EOL vs late-life stock-outs.",
        window="last-time buy 3 months before {eol}"),
    "CUSTOMER_SHUTDOWN": dict(
        title="Scheduled customer shutdown",
        owner="Sales / Production planning",
        finding=("{customer} ({region}) shuts down in {shutdown_months} ({event}); the forecast already removes "
                 "{units_removed} units across {series} SKUs."),
        action="Cut replenishment for those months, rebalance production to other customers and confirm the restart date.",
        trade_off="Revenue removed: ${revenue_removed}.",
        window="3 months before the shutdown"),
}


class _Fmt(dict):
    def __missing__(self, k):
        return "n/a"


def _fmt(v):
    if isinstance(v, bool) or v is None:
        return "n/a" if v is None else str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"
    return str(v)


def render(exc: pd.DataFrame) -> list[dict]:
    cards = []
    for _, e in exc.iterrows():
        pb = PLAYBOOK[e["rule_id"]]
        f = _Fmt({k: _fmt(v) for k, v in e["evidence"].items()})
        cards.append({
            "id": e["exception_id"], "priority": e["priority"], "priority_score": float(e["priority_score"]),
            "rule_id": e["rule_id"], "title": pb["title"], "level": e["level"], "scope": e["scope"],
            "owner": pb["owner"], "finding": pb["finding"].format_map(f), "action": pb["action"].format_map(f),
            "trade_off": pb["trade_off"].format_map(f), "window": pb["window"].format_map(f),
            "confidence": e["confidence"], "impact_usd": round(float(e["impact_usd"])),
            "evidence": e["evidence"],
        })
    return cards
