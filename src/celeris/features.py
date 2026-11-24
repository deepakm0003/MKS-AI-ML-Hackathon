"""Stage 3b - feature matrix for a direct multi-horizon global model.

One row = (series, origin month o, horizon h): "standing at the end of month o, what
will demand be in month o+h?" (h = 1..19). Every feature uses only data up to o,
except things that are genuinely known in advance for the target month: the
calendar, holidays, scheduled customer events, product lifecycle dates and the
macro indicators (the macro file already contains values for the forecast window).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FORECAST_END, HISTORY_END, HISTORY_START

HORIZON = 19
MONTHS = pd.period_range(HISTORY_START, FORECAST_END, freq="M").strftime("%Y-%m").tolist()
MIDX = {m: i for i, m in enumerate(MONTHS)}
LAST_HIST = MIDX[HISTORY_END]

CATEGORICAL = ["Product_Family", "Region", "Sales_Channel", "Customer_Name",
               "Powertrain_Application", "Size_Class"]

# indicator, lag (months the indicator leads demand) - from drivers.best_lags
MACRO_LEADS = [("Auto_Production_YoY_Pct", 3), ("Auto_Production_YoY_Pct", 4),
               ("New_Vehicle_Orders_Index", 3), ("New_Vehicle_Orders_Index", 4),
               ("ISM_Manufacturing_PMI", 1), ("ISM_Manufacturing_PMI", 2),
               ("Raw_Material_Cost_Index", 1), ("EV_Adoption_Index", 0)]


class Panel:
    """Series x month matrices built once and sliced per origin."""

    def __init__(self, demand: pd.DataFrame, sku: pd.DataFrame, macro: pd.DataFrame,
                 events_monthly: pd.DataFrame, extra_series: pd.DataFrame | None = None,
                 feature_set: str = "base"):
        self.feature_set = feature_set      # "base" (champion) or "base+cross"
        self._inputs = (demand, sku, macro, events_monthly, extra_series)
        self._siblings: dict = {}
        d = demand
        keys = d[["SKU_ID", "Region"]].drop_duplicates()
        if extra_series is not None:   # test series with no history (new launches)
            keys = pd.concat([keys, extra_series[["SKU_ID", "Region"]]]).drop_duplicates()
        self.keys = keys.sort_values(["SKU_ID", "Region"]).reset_index(drop=True)
        n, T = len(self.keys), len(MONTHS)
        row = {k: i for i, k in enumerate(zip(self.keys["SKU_ID"], self.keys["Region"]))}
        ri = np.array([row[k] for k in zip(d["SKU_ID"], d["Region"])])
        ci = d["Date"].map(MIDX).to_numpy()

        def mat(col, fill=np.nan):
            M = np.full((n, T), fill, dtype=np.float32)
            M[ri, ci] = d[col].to_numpy(dtype=np.float32)
            return M

        self.Y = mat("Demand")                 # target (unconstrained demand), NaN = missing
        self.X = mat("Demand_Model")           # filled history for lags
        self.W = mat("Train_Weight", 0.0)
        self.active = np.zeros((n, T), bool)
        self.active[ri, ci] = True

        # static attributes (last known value per series)
        last = d.sort_values("Date").groupby(["SKU_ID", "Region"]).last()
        m = sku.set_index("SKU_ID")
        st = self.keys.copy()
        for c in ["Sales_Channel", "Customer_Name"]:
            st[c] = [last[c].get(k, np.nan) for k in zip(st["SKU_ID"], st["Region"])]
        if extra_series is not None:
            ex = extra_series.drop_duplicates(["SKU_ID", "Region"]).set_index(["SKU_ID", "Region"])
            for c in ["Sales_Channel", "Customer_Name"]:
                miss = st[c].isna()
                st.loc[miss, c] = [ex[c].get(k) for k in zip(st.loc[miss, "SKU_ID"], st.loc[miss, "Region"])]
        for c in ["Product_Family", "Powertrain_Application", "Size_Class"]:
            st[c] = st["SKU_ID"].map(m[c])
        st["launch_idx"] = st["SKU_ID"].map(m["Launch_Date"]).map(lambda x: _midx(x))
        st["eol_idx"] = st["SKU_ID"].map(m["EOL_Date"]).map(lambda x: _midx(x) if pd.notna(x) else 10_000)
        first_obs = np.where(self.active.any(1), self.active.argmax(1), 10_000)
        st["first_idx"] = first_obs
        for c in CATEGORICAL:
            st[c] = st[c].astype("category")
        self.static = st

        # macro signals by month (index aligned to MONTHS)
        mac = macro.set_index("Date").reindex(MONTHS)
        sig = {}
        for c in mac.columns.drop(["Year", "Month"]):
            v = mac[c].astype(float)
            sig[c] = v if c in ("ISM_Manufacturing_PMI", "Auto_Production_YoY_Pct", "Industrial_Util_Rate_Pct",
                                "EV_Adoption_Index") else 100 * np.log(v / v.shift(12))
        self.macro = pd.DataFrame(sig).to_numpy(dtype=np.float32)
        self.macro_cols = list(sig)

        # holidays: region x month share of the month covered, by holiday kind
        hol = events_monthly[events_monthly["Event_Type"].eq("Holiday")].copy()
        hol["kind"] = np.select([hol["Description"].str.contains("Lunar", case=False),
                                 hol["Description"].str.contains("Ramadan", case=False)],
                                ["lunar", "ramadan"], "summer")
        self.hol = {}
        regions = self.keys["Region"].unique()
        for kind in ["lunar", "ramadan", "summer"]:
            H = pd.DataFrame(0.0, index=regions, columns=MONTHS)
            for _, r in hol[hol["kind"].eq(kind)].iterrows():
                if r["Scope_Region"] in H.index and r["Date"] in H.columns:
                    H.loc[r["Scope_Region"], r["Date"]] += r["Month_Share"]
            self.hol[kind] = H
        # customer events (strikes, shutdowns): customer|region x month
        ce = events_monthly[events_monthly["Event_Type"].eq("Customer Event") &
                            events_monthly["Description"].str.contains("shutdown|strike", case=False)]
        self.cust_event = {(r["Scope_Customer"], r["Scope_Region"], r["Date"]): r["Month_Share"] for _, r in ce.iterrows()}
        # announced list-price changes (known in advance): January rises and mid-year surcharges, in %
        pc = events_monthly[events_monthly["Event_Type"].eq("Price Change") & events_monthly["Scope_Type"].eq("Global")]
        pct = pc.drop_duplicates("Date").set_index("Date")["Pct"].astype(float)
        self.price_jan = np.array([pct.get(m, 0.0) if m.endswith("-01") else 0.0 for m in MONTHS], dtype=np.float32)
        self.price_surcharge = np.array([pct.get(m, 0.0) if not m.endswith("-01") else 0.0 for m in MONTHS], dtype=np.float32)

    def sibling(self, feature_set: str, variant: str | None) -> "Panel":
        """The same inputs (incl. any shocked macro) with another feature set and/or training-month
        variant - used by blends whose members were trained on different variants."""
        key = (feature_set, variant)
        if key not in self._siblings:
            demand, sku, macro, evm, extra = self._inputs
            if variant:
                from .robustness import demand_variant
                demand = demand_variant(demand, variant).sort_index()
            self._siblings[key] = Panel(demand, sku, macro, evm, extra, feature_set=feature_set)
        return self._siblings[key]

    # ------------------------------------------------------------------ per-origin features
    def series_features(self, o: int) -> pd.DataFrame:
        X = self.X[:, : o + 1]
        n = X.shape[0]
        f = {}
        for k in range(1, 13):
            f[f"lag_{k}"] = X[:, o + 1 - k] if o + 1 - k >= 0 else np.full(n, np.nan)
        win = lambda a, b: X[:, max(0, o + 1 - b): o + 1 - a] if o + 1 - a > 0 else np.full((n, 1), np.nan)
        with np.errstate(all="ignore"):
            f["mean_3"] = np.nanmean(win(0, 3), 1)
            f["mean_6"] = np.nanmean(win(0, 6), 1)
            f["mean_12"] = np.nanmean(win(0, 12), 1)
            f["mean_24"] = np.nanmean(win(0, 24), 1)
            f["prev_mean_12"] = np.nanmean(win(12, 24), 1)
            f["std_12"] = np.nanstd(win(0, 12), 1)
            w12, w24 = win(0, 12), win(0, 24)
            f["nz_share_12"] = np.nanmean(w12 > 0, 1)
            f["nz_share_24"] = np.nanmean(w24 > 0, 1)
            nzv = np.where(w12 > 0, w12, np.nan)
            f["order_size_12"] = np.nanmean(nzv, 1)
            f["max_12"] = np.nanmax(w12, 1)
        scale = np.where(np.isfinite(f["mean_12"]) & (f["mean_12"] > 0.1), f["mean_12"], np.nan)
        f["scale"] = scale
        f["trend_12"] = f["mean_12"] / np.where(f["prev_mean_12"] > 0, f["prev_mean_12"], np.nan)
        f["momentum_3"] = f["mean_3"] / scale
        f["cv_12"] = f["std_12"] / scale
        for k in range(1, 13):
            f[f"lag_{k}_n"] = f[f"lag_{k}"] / scale
        # ordering cycle and phase at the origin
        last_order = np.full(n, np.nan)
        cycle = np.full(n, np.nan)
        for i in range(n):
            idx = np.flatnonzero(np.nan_to_num(X[i, max(0, o - 23): o + 1]) > 0)
            if len(idx):
                last_order[i] = (min(o, 23) - idx[-1]) if o >= 23 else (o - idx[-1])
                if len(idx) >= 3:
                    g = np.diff(idx)
                    v, c = np.unique(g, return_counts=True)
                    cycle[i] = v[np.argmax(c)]
        f["months_since_order"] = last_order
        f["cycle"] = cycle
        f["age"] = o - self.static["first_idx"].to_numpy()
        return pd.DataFrame(f)

    def seasonal_index(self, o: int) -> pd.DataFrame:
        """Family x region seasonal index by calendar month, from data up to o only."""
        st = self.static
        X = self.X[:, : o + 1]
        grp = st["Product_Family"].astype(str) + "|" + st["Region"].astype(str)
        tot = pd.DataFrame(X).groupby(grp.values).sum(min_count=1).T
        ma = tot.rolling(12, center=True, min_periods=12).mean()
        ratio = tot / ma
        cal = np.array([int(MONTHS[i][5:]) for i in range(o + 1)])
        si = ratio.groupby(cal).mean()
        si = si.div(si.mean(), axis=1).fillna(1.0)
        return si   # index: calendar month 1..12, columns: family|region

    def frame(self, o: int, horizons=range(1, HORIZON + 1), need_target=True,
              eligible: np.ndarray | None = None) -> pd.DataFrame:
        st = self.static
        sf = self.series_features(o)
        if "cross" in self.feature_set:
            from .cross_series import cross_features
            sf = pd.concat([sf, cross_features(self.X, self.static, o)], axis=1)
        fam_models = None
        if "growth" in self.feature_set:
            from .challenger_features import family_macro_models, growth_series_features
            sf = pd.concat([sf, growth_series_features(self.X, self.static, o)], axis=1)
            fam_models = family_macro_models(self.X, self.static, self.macro, self.macro_cols, o)
            fam_arr = self.static["Product_Family"].astype(str).to_numpy()
        if "interm" in self.feature_set:
            from .challenger_features import intermittent_features
            sf = pd.concat([sf, intermittent_features(self.X, o)], axis=1)
        si = self.seasonal_index(o)
        grp = (st["Product_Family"].astype(str) + "|" + st["Region"].astype(str)).to_numpy()
        base_ok = (st["first_idx"].to_numpy() <= o) if eligible is None else eligible
        out = []
        for h in horizons:
            t = o + h
            if t >= len(MONTHS):
                break
            if need_target:
                ok = base_ok & self.active[:, t] & ~np.isnan(self.Y[:, t])
            else:
                ok = base_ok.copy()
            if not ok.any():
                continue
            fr = sf[ok].copy()
            s = st[ok]
            fr["h"] = h
            fr["origin"] = o
            fr["target_idx"] = t
            cm = int(MONTHS[t][5:])
            fr["target_month"] = cm
            if "price" in self.feature_set:          # early buying before a rise, payback after it
                to_jan = (13 - cm) % 12 or 12          # months from the target month to the next January
                nxt = t + to_jan
                fr["pr_months_to_rise"] = to_jan
                fr["pr_next_pct"] = float(self.price_jan[nxt]) if nxt < len(MONTHS) and to_jan <= 3 else 0.0
                last = t - (cm - 1)                    # this year's January
                fr["pr_last_pct"] = float(self.price_jan[last]) if cm <= 3 else 0.0
                fr["pr_surcharge"] = float(self.price_surcharge[t])
            fr["seas_idx"] = [si.at[cm, g] if g in si.columns else 1.0 for g in grp[ok]]
            fr["seas_idx_origin"] = [si.at[int(MONTHS[o][5:]), g] if g in si.columns else 1.0 for g in grp[ok]]
            # same month last year / two years ago (latest one at or before the origin)
            back = t - 12 * int(np.ceil(h / 12))
            fr["same_month_ly"] = self.X[ok, back] if back >= 0 else np.nan
            fr["same_month_ly_n"] = fr["same_month_ly"] / fr["scale"]
            # SKU-level seasonality: the same calendar month in up to 3 past years, plus a
            # +-1 month window (demand here correlates at lag 12, not at lag 1)
            sm, smw = [], []
            for k in range(3):
                b = back - 12 * k
                if b >= 1:
                    sm.append(self.X[ok, b])
                    smw.append(np.nanmean(self.X[ok][:, b - 1: min(b + 2, o + 1)], 1))
            with np.errstate(all="ignore"):
                for k in range(3):
                    fr[f"same_month_{k + 1}y_n"] = sm[k] / fr["scale"] if k < len(sm) else np.nan
                fr["same_month_mean_n"] = np.nanmean(np.vstack(sm), 0) / fr["scale"] if sm else np.nan
                fr["same_month_win_n"] = np.nanmean(np.vstack(smw), 0) / fr["scale"] if smw else np.nan
                lo = max(0, o - 35)
                m36 = np.nanmean(self.X[ok, lo: o + 1], 1)
                fr["same_month_prof"] = (np.nanmean(np.vstack(sm), 0) / np.where(m36 > 0, m36, np.nan)) if sm else np.nan
            # cycle phase: is the target month an "order month" for this customer?
            cyc = fr["cycle"].to_numpy()
            ph = (fr["months_since_order"].to_numpy() + h)
            fr["phase"] = np.where(cyc > 1, np.mod(ph, np.where(cyc > 0, cyc, 1)), 0)
            fr["phase_due"] = np.where(cyc > 1, (fr["phase"] == 0).astype(float), 1.0)
            # same-phase naive: value one cycle (or k cycles) back
            k = np.where(np.isfinite(cyc) & (cyc >= 1), cyc, 1).astype(int)
            back_c = t - k * np.ceil(h / k).astype(int)
            fr["cycle_naive"] = self.X[np.flatnonzero(ok), np.clip(back_c, 0, None)]
            fr["cycle_naive_n"] = fr["cycle_naive"] / fr["scale"]
            # lifecycle
            fr["months_since_launch"] = t - s["launch_idx"].to_numpy()
            fr["months_to_eol"] = np.minimum(s["eol_idx"].to_numpy() - t, 60)
            # holidays and customer events in the target month
            reg = s["Region"].astype(str).to_numpy()
            for kind, H in self.hol.items():
                fr[f"hol_{kind}"] = H.loc[reg, MONTHS[t]].to_numpy()
                fr[f"hol_{kind}_origin"] = H.loc[reg, MONTHS[o]].to_numpy()
            cust = s["Customer_Name"].astype(str).to_numpy()
            fr["cust_shutdown"] = [self.cust_event.get((c, r, MONTHS[t]), 0.0) for c, r in zip(cust, reg)]
            # macro: value the indicator had `lag` months before the target month, and
            # its change since the origin (the level at the origin is already in the lags)
            for ind, lag in MACRO_LEADS:
                j = self.macro_cols.index(ind)
                v_t, v_o = self.macro[t - lag, j], self.macro[o - lag, j]
                fr[f"m_{ind[:12]}_L{lag}"] = v_t
                fr[f"m_{ind[:12]}_L{lag}_chg"] = v_t - v_o
            if fam_models is not None:
                from .challenger_features import growth_target_features
                for k, v in growth_target_features(fam_models, fam_arr[ok], self.macro, o, t).items():
                    fr[k] = v
            for c in CATEGORICAL:   # keep one fixed category set so codes match across frames
                fr[c] = pd.Categorical(s[c].astype(object), categories=st[c].cat.categories)
            fr["series"] = np.flatnonzero(ok)
            if need_target:
                fr["y"] = self.Y[ok, t]
                fr["w"] = self.W[ok, t]
            out.append(fr)
        if not out:
            return pd.DataFrame()
        df = pd.concat(out, ignore_index=True)
        f64 = df.select_dtypes("float64").columns
        df[f64] = df[f64].astype(np.float32)      # halves memory for the training cache
        return df


def _midx(x):
    if pd.isna(x):
        return np.nan
    p = pd.Period(x, "M")
    return (p - pd.Period(HISTORY_START, "M")).n


FEATURES_EXCLUDE = {"y", "w", "origin", "target_idx", "series", "scale"}


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in FEATURES_EXCLUDE]
