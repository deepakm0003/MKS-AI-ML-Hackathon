"""Build the presentation deck (16:9 PDF) in the dashboard's design.

    python scripts/make_deck.py            # needs the API running on :8000 (uvicorn api.app:app)

Every number comes from the frozen outputs through the API; the screens in docs/deck/screens/
are headless-Chrome captures of the running dashboard. Output: docs/deck/celeris_presentation.pdf
"""
from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "docs" / "deck"
SCREENS = DECK / "screens"
API = "http://127.0.0.1:8000"
W, H = 960, 540

BG, S1, S2, S3, BORDER = "#080808", "#141414", "#1c1c1c", "#242424", "#282828"
T1, T2, T3 = "#ffffff", "#a1a1a1", "#707070"
LIME, BLUE, LBLUE, GOOD, WARN, CRIT = "#c7ff32", "#3478f6", "#77aaff", "#34d399", "#f5b942", "#ff5c5c"

# ----------------------------------------------------------------------------- fonts
FONTS = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("UI", str(FONTS / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UIB", str(FONTS / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("MONO", str(FONTS / "consola.ttf")))
    REG, BOLD, MONO = "UI", "UIB", "MONO"
    for f in ["segoeui.ttf", "segoeuib.ttf"]:
        font_manager.fontManager.addfont(str(FONTS / f))
    plt.rcParams["font.family"] = "Segoe UI"
except Exception:  # noqa: BLE001 - other OS: built-in fonts
    REG, BOLD, MONO = "Helvetica", "Helvetica-Bold", "Courier"

plt.rcParams.update({"axes.facecolor": S1, "figure.facecolor": S1, "axes.edgecolor": BORDER, "axes.labelcolor": T2,
                     "xtick.color": T3, "ytick.color": T3, "text.color": T2, "axes.grid": True, "grid.color": S3,
                     "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.load(r)


def fig_image(fig) -> ImageReader:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=S1, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)


def fu(v: float) -> str:
    return f"{v / 1e6:.2f}M" if v >= 1e6 else f"{v / 1e3:.0f}K" if v >= 1e3 else f"{v:.0f}"


# ----------------------------------------------------------------------------- drawing helpers (top-left coords)
class Deck:
    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=(W, H))
        self.c.setTitle("Celeris Demand Intelligence Control Tower")
        self.c.setAuthor("Celeris Control Tower")
        self.n = 0

    def y(self, top: float) -> float:
        return H - top

    def page(self, kicker: str | None = None, title: str | None = None, sub: str | None = None):
        if self.n:
            self.footer()
            self.c.showPage()
        self.n += 1
        self.rect(0, 0, W, H, BG)
        # faint grid like the landing page
        self.c.setStrokeColor("#101410")
        self.c.setLineWidth(0.5)
        for x in range(0, W, 48):
            self.c.line(x, 0, x, H)
        for yy in range(0, H, 48):
            self.c.line(0, yy, W, yy)
        self.logo(36, 24)
        if kicker:
            self.text(kicker.upper(), 36, 74, 8.5, LIME, BOLD)
        if title:
            self.text(title, 36, 100, 22, T1, BOLD)
        if sub:
            self.para(sub, 36, 120, 860, 10.5, T2, 14)

    def footer(self):
        self.c.setStrokeColor(BORDER)
        self.c.line(36, 26, W - 36, 26)
        self.text("Celeris Demand Intelligence Control Tower · MKS AI/ML Hackathon · Phase 2", 36, H - 12, 7.5, T3)
        self.text(str(self.n), W - 36, H - 12, 7.5, T3, align="right")

    def logo(self, x, top):
        self.rect(x, top, 22, 22, S2, r=5)
        self.c.setStrokeColor(LIME)
        self.c.setLineWidth(1.6)
        p = self.c.beginPath()
        p.moveTo(x + 5, self.y(top + 16)); p.lineTo(x + 9.5, self.y(top + 10.5)); p.lineTo(x + 13, self.y(top + 14)); p.lineTo(x + 17, self.y(top + 7))
        self.c.drawPath(p, stroke=1, fill=0)
        self.text("CELERIS", x + 30, top + 15.5, 11, T1, BOLD)
        self.text("Demand Control Tower", x + 92, top + 15.5, 8, T3)

    def rect(self, x, top, w, h, fill, r=0, stroke=None, lw=0.8):
        c = self.c
        c.setFillColor(fill)
        if stroke:
            c.setStrokeColor(stroke)
            c.setLineWidth(lw)
        if r:
            c.roundRect(x, self.y(top + h), w, h, r, stroke=1 if stroke else 0, fill=1 if fill != "none" else 0)
        else:
            c.rect(x, self.y(top + h), w, h, stroke=1 if stroke else 0, fill=1 if fill != "none" else 0)

    def text(self, s, x, top, size=10, color=T1, font=None, align="left"):
        c = self.c
        c.setFont(font or REG, size)
        c.setFillColor(color)
        f = {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align]
        f(x, self.y(top), s)

    def para(self, s, x, top, width, size=10, color=T2, lead=None, font=None) -> float:
        lead = lead or size * 1.35
        words, line, yy = s.split(), "", top
        for w_ in words:
            nxt = f"{line} {w_}".strip()
            if pdfmetrics.stringWidth(nxt, font or REG, size) > width and line:
                self.text(line, x, yy, size, color, font)
                yy += lead
                line = w_
            else:
                line = nxt
        if line:
            self.text(line, x, yy, size, color, font)
            yy += lead
        return yy

    def card(self, x, top, w, h, title=None, sub=None, accent=False):
        self.rect(x, top, w, h, S1, r=9, stroke="#4a5f12" if accent else BORDER)
        if title:
            self.text(title, x + 14, top + 22, 11.5, T1, BOLD)
        if sub:
            self.text(sub, x + 14, top + 36, 8, T3)

    def kpi(self, x, top, w, label, value, sub="", accent=False, h=84, color=None):
        self.card(x, top, w, h, accent=accent)
        self.text(label.upper(), x + 14, top + 20, 7.5, T3, BOLD)
        self.text(value, x + 14, top + 50, 24, color or (LIME if accent else T1), BOLD)
        if sub:
            self.para(sub, x + 14, top + 66, w - 28, 8, T2, 10)

    def image(self, img, x, top, w, h=None, border=True):
        ir = img if isinstance(img, ImageReader) else ImageReader(str(img))
        iw, ih = ir.getSize()
        h = h or w * ih / iw
        self.c.drawImage(ir, x, self.y(top + h), w, h, mask="auto")
        if border:
            self.rect(x, top, w, h, "none", r=0, stroke=BORDER)
        return h

    def screen(self, name, x, top, w, crop=None):
        """Dashboard screenshot, optionally cropped (left, top, right, bottom in px)."""
        from PIL import Image
        im = Image.open(SCREENS / f"{name}.png").convert("RGB")
        if crop:
            im = im.crop(crop)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        h = w * im.height / im.width
        self.rect(x - 1, top - 1, w + 2, h + 2, BORDER, r=6)
        self.c.drawImage(ImageReader(buf), x, self.y(top + h), w, h)
        return h

    def box(self, x, top, w, h, title, lines=(), color=LIME, fill=S1, title_size=10.5, size=8.8):
        self.rect(x, top, w, h, fill, r=7, stroke=BORDER)
        self.rect(x, top + 8, 3, h - 16, color, r=1.5)
        self.text(title, x + 12, top + 18, title_size, T1, BOLD)
        yy = top + 20 + title_size * 1.4
        for ln in lines:
            yy = self.para(ln, x + 12, yy, w - 20, size, T2, size * 1.35)

    def arrow(self, x1, t1, x2, t2, color=T3, lw=1.2, label=None):
        c = self.c
        c.setStrokeColor(color)
        c.setFillColor(color)
        c.setLineWidth(lw)
        c.line(x1, self.y(t1), x2, self.y(t2))
        import math
        a = math.atan2(self.y(t2) - self.y(t1), x2 - x1)
        L = 6
        p = c.beginPath()
        p.moveTo(x2, self.y(t2))
        p.lineTo(x2 - L * math.cos(a - 0.4), self.y(t2) - L * math.sin(a - 0.4))
        p.lineTo(x2 - L * math.cos(a + 0.4), self.y(t2) - L * math.sin(a + 0.4))
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        if label:
            self.text(label, (x1 + x2) / 2, (t1 + t2) / 2 - 4, 7, T3, align="center")

    def bullets(self, items, x, top, width, size=10, gap=6, color=T2):
        yy = top
        for it in items:
            self.rect(x, yy - 6.5, 5, 5, LIME, r=1)
            yy = self.para(it, x + 13, yy, width - 13, size, color, size * 1.35) + gap
        return yy

    def save(self):
        self.footer()
        self.c.save()


# ----------------------------------------------------------------------------- charts
def bar_chart(labels, values, colors, fmt, w=5.2, h=2.6, horizontal=True, ref=None, ref_label=None):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_axisbelow(True)
    if horizontal:
        ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.62)
        for i, v in enumerate(values[::-1]):
            ax.text(v, i, f"  {fmt(v)}", va="center", color=T1, fontsize=9, fontweight="bold")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, max(values) * 1.22)
        if ref is not None:
            ax.axvline(ref, color=WARN, lw=1.2, ls="--")
            ax.text(ref, len(values) - 0.4, f" {ref_label}", color=WARN, fontsize=8)
    else:
        ax.bar(labels, values, color=colors, width=0.6)
        for i, v in enumerate(values):
            ax.text(i, v, fmt(v), ha="center", va="bottom", color=T1, fontsize=9, fontweight="bold")
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, max(values) * 1.2)
    ax.tick_params(length=0)
    return fig_image(fig)


def main():
    DECK.mkdir(parents=True, exist_ok=True)
    k = get("/intelligence/briefing")["kpis"]
    bt = get("/datasets/backtest_metrics")
    man = get("/datasets/manifest")
    reg = get("/datasets/experiment_registry?limit=100")["rows"]
    cov = get("/datasets/band_coverage")
    cov = cov["rows"] if isinstance(cov, dict) else cov
    rr = get("/datasets/run_report")
    dq = get("/datasets/dq_report")
    an = get("/views/anomalies?top=1")
    pl = get("/views/planning?top=1")["kpis"]
    tl = get("/views/timeline")
    wape, naive = bt["overall"]["WAPE"], bt["seasonal_naive_overall"]["WAPE"]
    imp = 1 - wape / naive
    n_feat = len(man["features"])

    d = Deck(DECK / "celeris_presentation.pdf")

    # 1 ---------------------------------------------------------------- title
    d.page()
    d.text("MKS AI/ML HACKATHON · PHASE 2", 36, 92, 9, LIME, BOLD)
    d.text("Demand forecasting", 36, 140, 38, T1, BOLD)
    d.text("that moves business", 36, 184, 38, LIME, BOLD)
    d.para("Celeris Demand Intelligence Control Tower: messy ERP data cleaned and explained, true demand recovered, "
           "a validated 19-month forecast with calibrated uncertainty, and a control tower that turns it into decisions.",
           36, 214, 430, 11, T2, 15)
    tiles = [("19-month forecast", f"{fu(k['units_19m'])} units", "Nov 2026 – May 2028", True),
             ("Accuracy · WAPE", f"{wape:.1%}", f"{imp:.0%} lower error than seasonal naive ({naive:.1%})", False),
             ("Revenue · next 12 m", f"${k['revenue_next12'] / 1e9:.2f}B", f"{k['revenue_next12_vs_last12']:+.1%} vs last 12 months", False),
             ("Actions ranked", f"{k['exceptions']}", f"{k['exceptions_by_priority']['CRITICAL']} critical · {k['exceptions_by_priority']['HIGH']} high", False)]
    for i, (lab, val, sub, acc) in enumerate(tiles):
        d.kpi(36 + (i % 2) * 218, 300 + (i // 2) * 96, 208, lab, val, sub, accent=acc)
    d.screen("home", 488, 140, 436)

    # 2 ---------------------------------------------------------------- problem
    d.page("The challenge", "From a messy ERP extract to confident planning decisions",
           "Celeris Automobili needs a 19-month SKU x region forecast it can trust, from data that is dirty, censored by "
           "stockouts and shaken by events - plus a control tower that explains it.")
    probs = [("Messy data", [f"{rr['rows_ingested']:,} raw sales rows, 6 files", "duplicates, date & label variants, x10 unit errors, missing values"], CRIT),
             ("Censored demand", ["stockouts hide true demand", "strikes, shutdowns, pull-forward buying"], WARN),
             ("Long horizon", [f"{k['series']:,} SKU x region series", "19 months: Nov 2026 – May 2028"], BLUE),
             ("Decisions", ["procurement, capacity, supply risk", "who must act, by when, on what evidence"], LIME)]
    for i, (t, ls, col) in enumerate(probs):
        d.box(36 + i * 226, 160, 214, 98, t, ls, col)
    d.text("What we delivered", 36, 296, 13, T1, BOLD)
    deliv = [("1 · Clean", f"{dq['total_issues']:,} fixes, every one logged"),
             ("2 · Anomalies", f"{an['total']:,} months flagged, demand recovered"),
             ("3 · Features", f"{n_feat} features, macro leads, EV shift"),
             ("4 · Forecast", f"WAPE {wape:.1%}, calibrated P10–P90"),
             ("5 · Control tower", "12 views + Upload & Forecast + API")]
    for i, (t, s) in enumerate(deliv):
        x = 36 + i * 181
        d.rect(x, 310, 171, 70, S1, r=8, stroke=BORDER)
        d.text(t, x + 12, 334, 11, LIME, BOLD)
        d.para(s, x + 12, 352, 150, 8.5, T2, 11)
    d.bullets([f"Validated on {len(man['backtest']['cutoffs'])} rolling-origin cutoffs over the full 19-month horizon - "
               f"never on the training months",
               "Reproducible: one command rebuilds every output; the frozen model, data contract and SHA-256 manifest guarantee the dashboard shows exactly the validated numbers"],
              36, 412, 880, 10)

    # 3 ---------------------------------------------------------------- system architecture
    d.page("System design", "Architecture: one pipeline, one contract, one control tower",
           "Batch pipeline produces frozen, validated outputs; a typed data contract and a FastAPI layer serve them to the React dashboard. Upload & Forecast reuses the same pipeline modules on new data.")
    cols = [(36, "Raw data", ["train.csv (248k rows)", "test.csv · sku_master", "inventory_stockouts", "events_calendar", "macro_indicators"], T3),
            (196, "Pipeline · src/celeris", ["1 Clean + DQ log", "2 Anomalies + demand recovery", "3 Drivers + features", "4 Backtest + experiment registry", "5 Final freeze + validation", "6 Planning intelligence"], LIME),
            (376, "Frozen outputs", ["outputs/final (forecast, bands, model, manifest SHA-256)", "outputs/intelligence", "contracts/data_contract.yaml"], LBLUE),
            (556, "FastAPI · api/", ["read-only views (filters)", "scenario engine", "scoring jobs (uploads)", "serves dashboard build"], BLUE),
            (736, "React + ECharts", ["12 views, global filters", "Upload & Forecast", "PDF reports, CSV exports"], LIME)]
    for i, (x, t, ls, col) in enumerate(cols):
        d.box(36 + i * 180, 170, 166, 200, t, ls, col, title_size=11, size=9)
    for i in range(4):
        d.arrow(36 + i * 180 + 166, 270, 36 + (i + 1) * 180, 270, LIME, 1.6)
    # upload loop
    d.rect(196, 392, 708, 62, S1, r=8, stroke=BORDER)
    d.text("Upload & Forecast loop", 210, 412, 10, LIME, BOLD)
    d.para("CSV upload -> /score/jobs -> scoring.py reuses stages 1-3 (clean, recover, features) + the frozen model, rules and bands -> "
           "results, accuracy vs actuals, CSV + PDF. Official files reproduce the frozen submission exactly.", 210, 428, 680, 8.5, T2, 11)
    d.arrow(840, 370, 840, 392, T3)
    d.arrow(300, 392, 300, 370, T3)
    d.rect(36, 392, 150, 62, S1, r=8, stroke=BORDER)
    d.text("Deployment", 48, 412, 10, T1, BOLD)
    d.para("deploy.sh: pipeline -> build -> uvicorn :8000 serves API + UI (nginx optional)", 48, 428, 130, 8, T2, 10)

    # 4 ---------------------------------------------------------------- pipeline numbers
    d.page("Data flow", "The pipeline, stage by stage", "Each stage writes a contract-checked output and a machine-readable report.")
    steps = [("Ingest", f"{rr['rows_ingested']:,}", "raw sales rows"), ("Clean", f"{rr['rows_clean']:,}", f"clean rows · {dq['total_issues']:,} fixes"),
             ("Recover", f"{an['total']:,}", f"months flagged · {an['by_category']['stockout']:,} stockouts"),
             ("Features", f"{n_feat}", "lags, seasonality, lifecycle, macro, events"),
             ("Backtest", f"{len(reg)}", f"experiments · {len(man['backtest']['cutoffs'])} cutoffs"),
             ("Forecast", "58,219", "rows · P10/P50/P90"), ("Decide", f"{k['exceptions']}", "ranked actions")]
    bw = 122
    for i, (t, v, s) in enumerate(steps):
        x = 36 + i * (bw + 6)
        d.rect(x, 170, bw, 150, S1, r=8, stroke="#4a5f12" if i == 5 else BORDER)
        d.text(f"0{i + 1}", x + 12, 192, 8, LIME, BOLD)
        d.text(t, x + 12, 212, 12, T1, BOLD)
        d.text(v, x + 12, 256, 20, LIME if i == 5 else T1, BOLD)
        d.para(s, x + 12, 276, bw - 22, 8, T2, 10)
        if i < len(steps) - 1:
            d.arrow(x + bw - 2, 245, x + bw + 6, 245, LIME)
    d.bullets(["No look-ahead: every feature is computed from data up to the forecast origin; only the calendar, lifecycle dates, scheduled events and the macro file are known in advance",
               "Unconstrained demand is the target: stockout months are rebuilt from the stockout file and diff-in-diff estimates, so the model learns demand, not shipments",
               "Business rules the model cannot learn: zero outside launch-EOL, predecessor run-down x successor ramp-up, scheduled customer shutdowns"], 36, 360, 880, 10)

    # 5 ---------------------------------------------------------------- cleaning
    d.page("Stage 1 · data cleaning", "Every fix logged: original value, corrected value, rule",
           f"{dq['total_issues']:,} corrections across 6 files; validation PASS (one row per date x SKU x region, no negative units, revenue reconciles).")
    labels = ["Label variants", "Date formats", "Missing values recovered", "Duplicates removed", "Price fixes", "Unit errors"]
    vals = [rr["label_corrections"], rr["date_corrections"], rr["missing_values_recovered"], rr["duplicates_removed"], rr["price_corrections"], rr["unit_corrections"]]
    d.card(36, 150, 430, 300, "Corrections by type", "stage-1 run report")
    d.image(bar_chart(labels, vals, [LIME] * 6, lambda v: f"{v:,.0f}", w=5.4, h=3.2), 50, 196, 400, border=False)
    d.screen("data-health", 486, 150, 438, crop=(260, 130, 1600, 1000))
    d.para(f"train.csv: {rr['rows_ingested']:,} -> {rr['rows_clean']:,} rows; reloaded records and duplicate keys removed; x10 unit blocks rebuilt from revenue and the stockout file.",
           486, 452, 438, 9, T2, 12)

    # 6 ---------------------------------------------------------------- anomalies
    d.page("Stage 2 · anomalies & true demand", "Separate data errors from real events - then recover unconstrained demand",
           f"{an['total']:,} flagged months on {an['series_affected']:,} series, each with type, reason, action and confidence.")
    cats = ["stockout", "real_event", "data_error", "gap", "spike", "unknown"]
    nm = {"stockout": "Stockout (recovered)", "real_event": "Real event", "data_error": "Data error", "gap": "Missing month", "spike": "One-off spike", "unknown": "Unexplained drop"}
    d.card(36, 150, 400, 300, "Flagged months by category", "anomaly register")
    d.image(bar_chart([nm[c] for c in cats], [an["by_category"].get(c, 0) for c in cats], [CRIT, BLUE, WARN, T3, LIME, LBLUE], lambda v: f"{v:,.0f}", w=5, h=3.2), 50, 196, 372, border=False)
    d.screen("anomalies", 456, 150, 468, crop=(260, 130, 1600, 940))
    d.bullets(["Stockouts: demand = shipments + measured shortfall (stockout file, diff-in-diff vs peers)",
               "Events measured before excluding: only events with a material impact are kept out of training"], 456, 470, 468, 9, 3)

    # 7 ---------------------------------------------------------------- features & drivers
    d.page("Stage 3 · drivers & features", f"{n_feat} features for one global model over every series and horizon",
           "Direct multi-horizon design: one row = (series, origin month, horizon 1-19). Macro indicators lead demand by 1-4 months, checked for stability.")
    groups = [("Demand history", ["lags 1-12, rolling means / std / max", "same month last year, trend"], LIME),
              ("Seasonality", ["family x region seasonal index", "target month, origin month"], BLUE),
              ("Lifecycle", ["age, months to EOL, launch ramp", "predecessor / successor"], WARN),
              ("Macro leads", ["auto production, vehicle orders", "PMI, raw-material cost, EV index"], LBLUE),
              ("Calendar & events", ["holidays (lunar, Ramadan, summer)", "customer shutdowns & strikes"], GOOD),
              ("Static attributes", ["family, region, channel, customer", "powertrain, size class"], T3)]
    for i, (t, ls, col) in enumerate(groups):
        d.box(36 + (i % 3) * 148, 150 + (i // 3) * 110, 140, 100, t, ls, col)
    d.screen("macro", 492, 150, 432, crop=(260, 130, 1600, 1000))

    # 8 ---------------------------------------------------------------- validation
    d.page("Model & validation", "Rolling-origin backtest over the full 19-month horizon",
           f"Global LightGBM (Tweedie) evaluated on {len(man['backtest']['cutoffs'])} cutoffs: train on everything before each origin, score the next 19 months. Same folds for every experiment.")
    # backtest scheme diagram
    d.card(36, 150, 470, 250, "Backtest scheme", "train (grey) · 19-month test window (lime)")
    x0, x1 = 60, 490
    t0, t1 = 2019.0, 2026 + 10 / 12

    def xm(ym: str) -> float:
        y_, m_ = int(ym[:4]), int(ym[5:])
        return x0 + (y_ + (m_ - 1) / 12 - t0) / (t1 - t0) * (x1 - x0)
    for i, c in enumerate(man["backtest"]["cutoffs"]):
        top = 200 + i * 26
        y_, m_ = int(c[:4]), int(c[5:])
        e = y_ * 12 + m_ - 1 + 19
        end = f"{e // 12}-{e % 12 + 1:02d}"
        d.rect(x0, top, xm(c) - x0, 14, S3, r=2)
        d.rect(xm(c), top, min(xm(end), x1) - xm(c), 14, LIME, r=2)
        d.text(c, x0 - 4, top + 10.5, 7, T3, align="right") if False else d.text(c, xm(c) - 4, top + 10.5, 7, T2, align="right")
    for yr in range(2019, 2027):
        d.text(str(yr), xm(f"{yr}-01"), 372, 7, T3, align="center")
    wl = ["Global model", "Seasonal naive"]
    d.card(526, 150, 398, 250, "WAPE · SKU-month", f"{imp:.0%} lower error than seasonal naive")
    d.image(bar_chart(wl, [wape, naive], [LIME, T3], lambda v: f"{v:.1%}", w=4.8, h=1.25), 540, 194, 370, border=False)
    d.text("WAPE by horizon", 540, 300, 9, T2, BOLD)
    hb = ["1-3m", "4-6m", "7-12m", "13-19m"]
    d.image(bar_chart(hb, [bt["by_horizon_bucket"][h]["WAPE"] for h in hb], [BLUE] * 4, lambda v: f"{v:.1%}", w=4.8, h=1.15, horizontal=False), 540, 306, 370, border=False)
    for i, (lab, val, sub) in enumerate([("Family-month WAPE", f"{bt['family_month']['WAPE']:.1%}", "planning level"),
                                          ("Company-month WAPE", f"{bt['total_month']['WAPE']:.1%}", "total demand"),
                                          ("Bias", f"{bt['overall']['Bias']:+.1%}", "slight under-forecast"),
                                          ("MAE", f"{bt['overall']['MAE']:.1f}", "units per SKU-month")]):
        d.kpi(36 + i * 226, 414, 214, lab, val, sub, h=76, accent=i == 0)

    # 9 ---------------------------------------------------------------- experiments
    d.page("Experiments", "19 experiments, one promotion rule",
           "Every challenger runs on the same 6 folds; it is promoted only if it lowers WAPE, wins most series-cutoffs and is not worse on any cutoff.")
    regs = sorted(reg, key=lambda r: r["WAPE"])[:12]
    sel = man["selected_model"]
    d.card(36, 150, 520, 330, "WAPE by experiment (best 12)", "lower is better · selected model in lime, champion in blue")
    d.image(bar_chart([r["experiment"].replace("_", " ") for r in regs], [r["WAPE"] for r in regs],
                      [LIME if r["experiment"] == sel else BLUE if r["experiment"] == "champion" else T3 for r in regs],
                      lambda v: f"{v:.2%}", w=6.2, h=3.7), 50, 196, 490, border=False)
    d.box(576, 150, 348, 150, "Selected: " + sel.replace("_", " "),
          [man["selection_reason"][:220]], LIME, size=9.5)
    d.box(576, 312, 348, 168, "Promotion criteria", ["lower overall WAPE than the champion", "wins the majority of series-cutoffs",
                                                    "no cutoff materially worse", "bias and horizon profile not degraded",
                                                    "band coverage holds", "reproducible from the registry"], BLUE, size=9.5)

    # 10 --------------------------------------------------------------- uncertainty
    d.page("Uncertainty & hierarchy", "Calibrated P10–P90 bands, coherent from SKU to company",
           "Stratified split-conformal bands (size x horizon x age x volatility) fitted on the model's own backtest; aggregate bands from a level-specific error model, so totals are exact sums of SKU forecasts.")
    lv = {}
    for r in cov:
        lv.setdefault(r["Level"], []).append(r["Coverage_P10_P90"])
    levels = [l_ for l_ in ["total", "family", "region", "channel", "customer", "family_region"] if l_ in lv]
    d.card(36, 150, 470, 310, "Held-out P10–P90 coverage by level", "target 80% · mean over 6 cutoffs")
    d.image(bar_chart([l_.replace("_", " x ") for l_ in levels], [sum(lv[l_]) / len(lv[l_]) for l_ in levels], [LBLUE] * len(levels),
                      lambda v: f"{v:.0%}", w=5.6, h=3.4, ref=0.8, ref_label="80% target"), 50, 196, 440, border=False)
    d.kpi(526, 150, 398, "19-month total · P10 – P90", f"{fu(k['units_19m_p10'])} – {fu(k['units_19m_p90'])}", f"point forecast {fu(k['units_19m'])} units", accent=True)
    d.bullets(["Bands widen with horizon, small series, young products and volatile regions - exactly where the backtest error is larger",
               "Every aggregate (family, region, customer, total) equals the sum of its SKU forecasts",
               "Procurement uses the calibrated lead-time quantile, not a rule of thumb"], 526, 262, 398, 9.5)

    # 11 --------------------------------------------------------------- forecast
    d.page("The forecast", f"{fu(k['units_19m'])} units over Nov 2026 – May 2028",
           f"Next 12 months: {fu(k['units_next12'])} units ({k['units_next12_vs_last12']:+.1%}) and ${k['revenue_next12'] / 1e9:.2f}B revenue ({k['revenue_next12_vs_last12']:+.1%}) at the announced list prices.")
    hist = tl["history"][-48:]
    fc = tl["forecast"]
    fig, ax = plt.subplots(figsize=(11, 2.5))
    hx = list(range(len(hist)))
    fx = list(range(len(hist) - 1, len(hist) + len(fc)))
    ax.plot(hx, [h["Units_unconstrained"] for h in hist], color="#d9d9d9", lw=1.6, label="Actual demand")
    ax.plot(hx, [h["Units_shipped"] for h in hist], color=T3, lw=1, ls="--", label="Shipped")
    ax.fill_between(fx[1:], [f["Units_P10"] for f in fc], [f["Units_P90"] for f in fc], color=LIME, alpha=0.13, lw=0, label="P10–P90")
    ax.plot(fx, [hist[-1]["Units_unconstrained"]] + [f["Units_forecast"] for f in fc], color=LIME, lw=2.2, label="Forecast")
    ax.axvline(len(hist) - 1, color=T3, lw=0.8, ls=":")
    dates = [h["Date"] for h in hist] + [f["Date"] for f in fc]
    ticks = list(range(0, len(dates), 6))
    ax.set_xticks(ticks, [dates[i] for i in ticks])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e3:.0f}K"))
    ax.legend(loc="upper left", frameon=False, ncol=4, labelcolor=T2)
    ax.tick_params(length=0)
    d.card(36, 150, 888, 270, "Company demand: history -> forecast", "recovered (unconstrained) demand, 4 years of history, calibrated company band")
    d.image(fig_image(fig), 50, 194, 860, border=False)
    for i, (lab, val, sub, acc) in enumerate([("19-month forecast", f"{fu(k['units_19m'])}", "units", True),
                                               ("Revenue · 19 months", f"${k['revenue_19m'] / 1e9:.2f}B", "at list prices", False),
                                               ("Series forecast", f"{k['series']:,}", "SKU x region", False),
                                               ("Forecast rows", "58,219", "validated, test order", False)]):
        d.kpi(36 + i * 226, 430, 214, lab, val, sub, h=66, accent=acc)

    # 12 --------------------------------------------------------------- intelligence
    d.page("Planning intelligence", "From forecast to ranked, owned actions",
           "Rule-based recommendations with evidence: impact x severity x urgency x confidence decide the order; every card names an owner and a decision window.")
    for i, (lab, val, sub, col) in enumerate([("Critical actions", str(k["exceptions_by_priority"]["CRITICAL"]), f"{k['exceptions']} actions in total", CRIT),
                                               ("Next-cycle cover", f"${pl['cover_value_usd'] / 1e6:.0f}M", f"{fu(pl['cover_units'])} units, 3-month lead time", None),
                                               ("Service level", f"{pl['service_level_revenue_weighted']:.1%}", "revenue-weighted ABC-XYZ target", None),
                                               ("Capacity flags", str(k["capacity_flags"].get("ABOVE_DEMONSTRATED_THROUGHPUT", 0)), "family x region above demonstrated throughput", WARN)]):
        d.kpi(36 + i * 226, 150, 214, lab, val, sub, color=col)
    d.screen("risk", 36, 250, 440, crop=(260, 120, 1600, 800))
    d.screen("planning", 484, 250, 440, crop=(260, 120, 1600, 800))

    # 13 --------------------------------------------------------------- dashboard
    d.page("The control tower", "12 views, one set of global filters, every number from the contract",
           "Executive Overview · Demand Explorer · Risk & Exceptions · Planning & Procurement · Scenario Lab · Model Trust · Upload & Forecast · Calendar · Macro Drivers · Data Health · Anomaly Monitor")
    d.screen("overview", 36, 146, 440, crop=(0, 0, 1600, 900))
    d.screen("explorer", 484, 146, 440, crop=(0, 0, 1600, 900))
    d.text("Scenario Lab · Model Trust · Calendar Forecast · Data Health - filters travel in the URL, so any view can be shared.", 36, 414, 9, T3)
    for i, n in enumerate(["scenarios", "trust", "calendar", "data-health"]):
        d.screen(n, 36 + i * 224, 424, 216, crop=(260, 130, 1600, 560))

    # 14 --------------------------------------------------------------- upload & forecast
    d.page("Upload & Forecast", "Score any file in the competition format with the frozen model",
           "Sales history (train.csv) and / or rows to forecast (test.csv). The same cleaning, demand recovery, features, model, rules and bands - and accuracy against actuals when they are included.")
    flow = [("Upload", ["format detection", "row & column checks"]), ("Clean", ["stage-1 rules", "issue log"]),
            ("Recover", ["stockouts, anomalies", "no look-ahead"]), ("Score", ["frozen model", "rules + P10-P90"]),
            ("Evaluate", ["WAPE vs actuals", "vs seasonal naive"]), ("Export", ["submission CSV", "PDF report"])]
    for i, (t, ls) in enumerate(flow):
        x = 36 + i * 150
        d.box(x, 150, 140, 70, t, ls, LIME if i in (3, 4) else BLUE)
        if i < len(flow) - 1:
            d.arrow(x + 140, 185, x + 150, 185, LIME)
    d.screen("upload", 36, 236, 560, crop=(260, 60, 1600, 640))
    d.box(612, 236, 312, 120, "Reproducible", ["Uploading the official train.csv + test.csv reproduces the frozen submission exactly (all 58,219 rows, tested)."], GOOD)
    d.box(612, 366, 312, 137, "Honest by design", ["Accuracy on months the model was trained on is labelled in-sample.",
                                                   "Bad rows are rejected with a reason; the issue log, anomaly register and rejected rows are downloadable."], WARN)

    # 15 --------------------------------------------------------------- engineering
    d.page("Engineering quality", "Built to be checked, rerun and deployed",
           "One command rebuilds everything; the contract and the tests stop the dashboard from ever showing an unvalidated number.")
    eng = [("Tests", ["173 backend tests (pytest)", "41 frontend tests (vitest)", "contract enforced on every run"], LIME),
           ("Data contract", ["every dataset: path, grain, key, columns, types", "which view uses it"], BLUE),
           ("Frozen backend", ["manifest with SHA-256 of every file", "validation report: all checks PASS"], GOOD),
           ("API", ["read-only filtered views", "scenario engine, scoring jobs", "OpenAPI docs at /docs"], LBLUE),
           ("Reproducibility", ["python run_pipeline.py", "experiment registry with promotion rule", "upload check vs frozen submission"], WARN),
           ("Deployment", ["deploy.sh: pipeline, build, serve", "one uvicorn process on :8000", "nginx option documented"], T3)]
    for i, (t, ls, col) in enumerate(eng):
        d.box(36 + (i % 3) * 300, 150 + (i // 3) * 150, 288, 136, t, ls, col, title_size=13, size=10.5)

    # 16 --------------------------------------------------------------- close
    d.page("Next", "What comes next")
    d.bullets(["Model accuracy sprint on GPU: wider hyper-parameter search, larger seed / model ensembles (LightGBM + CatBoost), "
               "per-horizon specialists and hierarchical reconciliation - each judged by the same 6-cutoff promotion rule",
               "Monitoring: upload each new month of actuals to track forecast accuracy and drift with the Upload & Forecast page",
               "Planner workflow: owners close exceptions from the Risk page; procurement exports straight from the plan"],
              36, 140, 600, size=12, gap=10)
    d.text("Thank you", 36, 400, 40, LIME, BOLD)
    d.text(f"Forecast {fu(k['units_19m'])} units · WAPE {wape:.1%} · {k['exceptions']} ranked actions · 12 views", 36, 430, 11, T2)
    d.screen("home", 660, 140, 264, crop=(820, 295, 1365, 765))
    d.save()
    print(f"wrote {DECK / 'celeris_presentation.pdf'} ({d.n} slides)")


if __name__ == "__main__":
    main()
