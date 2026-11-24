"""Build the 12-slide presentation (16:9 PDF) in the dashboard's design.

    python scripts/make_deck.py            # needs the API running on :8000 (uvicorn api.app:app)

Numbers come from the frozen outputs through the API (and the C9c backtest predictions for the
demand-class table); screens in docs/deck/screens/ are headless-Chrome captures of the dashboard.
System-design diagrams (architecture, data flow, sequence, deployment) are drawn as vectors.
Output: docs/deck/celeris_presentation.pdf
"""
from __future__ import annotations

import io
import json
import math
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
AUTHOR, INSTITUTE = "Deepak Meena", "IIIT Delhi"
GITHUB = "https://github.com/deepakm0003/mks-celeris-demand-forecasting"
LIVE = "http://192.168.2.254:8060"
W, H = 960, 540

BG, S1, S2, S3, BORDER = "#080808", "#141414", "#1c1c1c", "#242424", "#2c2c2c"
T1, T2, T3 = "#ffffff", "#a1a1a1", "#707070"
LIME, BLUE, LBLUE, GOOD, WARN, CRIT, VIOLET = "#c7ff32", "#3478f6", "#77aaff", "#34d399", "#f5b942", "#ff5c5c", "#a78bfa"

FONTS = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("UI", str(FONTS / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UIB", str(FONTS / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("MONO", str(FONTS / "consola.ttf")))
    REG, BOLD, MONO = "UI", "UIB", "MONO"
    for f in ["segoeui.ttf", "segoeuib.ttf"]:
        font_manager.fontManager.addfont(str(FONTS / f))
    plt.rcParams["font.family"] = "Segoe UI"
except Exception:  # noqa: BLE001
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


def demand_class_table() -> list[dict]:
    """Accuracy by Syntetos-Boylan demand class on the C9c 6-cutoff backtest (cached as JSON)."""
    cache = DECK / "demand_class_accuracy.json"
    src = ROOT / "artifacts" / "experiments" / "c9c_keep_pull_forward" / "predictions.parquet"
    if src.exists():
        import pandas as pd
        p = pd.read_parquet(src)
        wp = lambda d, c: float((d[c] - d["y"]).abs().sum() / d["y"].sum())
        rows = [{"class": k, "series": int(g["series"].nunique()), "share": float(g["y"].sum() / p["y"].sum()),
                 "model": wp(g, "f"), "naive": wp(g, "f_naive_seasonal")} for k, g in p.groupby("Demand_Class")]
        order = ["smooth", "intermittent", "erratic", "lumpy"]
        rows.sort(key=lambda r: order.index(r["class"]) if r["class"] in order else 9)
        rows.append({"class": "all", "series": int(p["series"].nunique()), "share": 1.0, "model": wp(p, "f"),
                     "naive": wp(p, "f_naive_seasonal")})
        cache.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        return rows
    return json.loads(cache.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- canvas helpers (top-left coords)
class Deck:
    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=(W, H))
        self.c.setTitle("Celeris Demand Intelligence Control Tower")
        self.c.setAuthor("Celeris Control Tower")
        self.n = 0

    def Y(self, top: float) -> float:
        return H - top

    # ---- page
    def page(self, kicker=None, title=None, sub=None):
        if self.n:
            self.footer()
            self.c.showPage()
        self.n += 1
        self.rect(0, 0, W, H, BG)
        self.c.setStrokeColor("#0f130c")
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
            self.para(sub, 36, 120, 880, 10.5, T2, 14)

    def footer(self):
        self.c.setStrokeColor(BORDER)
        self.c.setLineWidth(0.6)
        self.c.line(36, 26, W - 36, 26)
        self.text(f"Celeris Demand Intelligence Control Tower · {AUTHOR}, {INSTITUTE} · MKS AI/ML Hackathon Phase 2", 36, H - 12, 7.5, T3)
        self.text(f"{self.n} / 12", W - 36, H - 12, 7.5, T3, align="right")

    def logo(self, x, top):
        self.rect(x, top, 22, 22, S2, r=5)
        self.c.setStrokeColor(LIME)
        self.c.setLineWidth(1.6)
        p = self.c.beginPath()
        p.moveTo(x + 5, self.Y(top + 16)); p.lineTo(x + 9.5, self.Y(top + 10.5)); p.lineTo(x + 13, self.Y(top + 14)); p.lineTo(x + 17, self.Y(top + 7))
        self.c.drawPath(p, stroke=1, fill=0)
        self.text("CELERIS", x + 30, top + 15.5, 11, T1, BOLD)
        self.text("Demand Control Tower", x + 92, top + 15.5, 8, T3)

    # ---- primitives
    def rect(self, x, top, w, h, fill, r=0, stroke=None, lw=0.8, dash=None):
        c = self.c
        if fill != "none":
            c.setFillColor(fill)
        if stroke:
            c.setStrokeColor(stroke)
            c.setLineWidth(lw)
        c.setDash(*dash) if dash else c.setDash()
        args = (x, self.Y(top + h), w, h)
        kw = dict(stroke=1 if stroke else 0, fill=0 if fill == "none" else 1)
        c.roundRect(*args, r, **kw) if r else c.rect(*args, **kw)
        c.setDash()

    def text(self, s, x, top, size=10, color=T1, font=None, align="left"):
        c = self.c
        c.setFont(font or REG, size)
        c.setFillColor(color)
        {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align](x, self.Y(top), s)

    def para(self, s, x, top, width, size=10, color=T2, lead=None, font=None, align="left") -> float:
        lead = lead or size * 1.35
        line, yy = "", top
        for w_ in s.split():
            nxt = f"{line} {w_}".strip()
            if pdfmetrics.stringWidth(nxt, font or REG, size) > width and line:
                self.text(line, x if align == "left" else x + width / 2, yy, size, color, font, align if align == "left" else "center")
                yy += lead
                line = w_
            else:
                line = nxt
        if line:
            self.text(line, x if align == "left" else x + width / 2, yy, size, color, font, align if align == "left" else "center")
            yy += lead
        return yy

    def line(self, pts, color=T3, lw=1.2, dash=None, head=True):
        c = self.c
        c.setStrokeColor(color)
        c.setFillColor(color)
        c.setLineWidth(lw)
        c.setDash(*dash) if dash else c.setDash()
        p = c.beginPath()
        p.moveTo(pts[0][0], self.Y(pts[0][1]))
        for x, t in pts[1:]:
            p.lineTo(x, self.Y(t))
        c.drawPath(p, stroke=1, fill=0)
        c.setDash()
        if head:
            (x1, t1), (x2, t2) = pts[-2], pts[-1]
            a = math.atan2(self.Y(t2) - self.Y(t1), x2 - x1)
            L = 6.5
            q = c.beginPath()
            q.moveTo(x2, self.Y(t2))
            q.lineTo(x2 - L * math.cos(a - 0.42), self.Y(t2) - L * math.sin(a - 0.42))
            q.lineTo(x2 - L * math.cos(a + 0.42), self.Y(t2) - L * math.sin(a + 0.42))
            q.close()
            c.drawPath(q, stroke=0, fill=1)

    def label(self, s, x, top, color=T3, size=7, bg=BG):
        w = pdfmetrics.stringWidth(s, REG, size) + 8
        self.rect(x - w / 2, top - size - 1, w, size + 5, bg, r=2)
        self.text(s, x, top + 1, size, color, align="center")

    # ---- diagram shapes
    def cylinder(self, x, top, w, h, title, sub="", color=BLUE):
        c = self.c
        e = 7
        c.setFillColor(S2)
        c.setStrokeColor(color)
        c.setLineWidth(1)
        c.rect(x, self.Y(top + h - e), w, h - 2 * e, stroke=0, fill=1)
        c.ellipse(x, self.Y(top + h), x + w, self.Y(top + h - 2 * e), stroke=1, fill=1)
        c.rect(x, self.Y(top + h - e), w, h - 2 * e, stroke=0, fill=1)
        c.line(x, self.Y(top + e), x, self.Y(top + h - e))
        c.line(x + w, self.Y(top + e), x + w, self.Y(top + h - e))
        c.setFillColor(S3)
        c.ellipse(x, self.Y(top + 2 * e), x + w, self.Y(top), stroke=1, fill=1)
        self.text(title, x + w / 2, top + h / 2 + 5, 8.6, T1, BOLD, "center")
        if sub:
            self.para(sub, x + 4, top + h / 2 + 16, w - 8, 6.8, T2, 8.5, align="center")

    def doc(self, x, top, w, h, title, sub="", color=T3):
        c = self.c
        f = 9
        c.setFillColor(S1)
        c.setStrokeColor(color)
        c.setLineWidth(0.9)
        p = c.beginPath()
        p.moveTo(x, self.Y(top)); p.lineTo(x + w - f, self.Y(top)); p.lineTo(x + w, self.Y(top + f))
        p.lineTo(x + w, self.Y(top + h)); p.lineTo(x, self.Y(top + h)); p.close()
        c.drawPath(p, stroke=1, fill=1)
        c.line(x + w - f, self.Y(top), x + w - f, self.Y(top + f))
        c.line(x + w - f, self.Y(top + f), x + w, self.Y(top + f))
        self.text(title, x + 8, top + 15, 8.2, T1, BOLD)
        if sub:
            self.text(sub, x + 8, top + 26, 6.8, T3)

    def process(self, x, top, w, h, n, title, sub="", color=LIME):
        self.rect(x, top, w, h, S1, r=7, stroke=color, lw=1)
        c = self.c
        c.setFillColor(color)
        c.circle(x + 14, self.Y(top + h / 2), 8.5, stroke=0, fill=1)
        self.text(str(n), x + 14, top + h / 2 + 3.2, 8.5, BG, BOLD, "center")
        self.text(title, x + 28, top + h / 2 - 1 if sub else top + h / 2 + 3, 8.6, T1, BOLD)
        if sub:
            self.text(sub, x + 28, top + h / 2 + 10, 6.8, T2)

    def server(self, x, top, w, h, title, lines=(), color=BLUE):
        self.rect(x, top, w, h, S1, r=8, stroke=color, lw=1.1)
        self.rect(x, top, w, 22, S2, r=8)
        self.rect(x, top + 14, w, 8, S2)
        for i in range(3):
            self.c.setFillColor(color if i == 0 else T3)
            self.c.circle(x + 10 + i * 8, self.Y(top + 11), 2.2, stroke=0, fill=1)
        self.text(title, x + 38, top + 14.5, 8.6, T1, BOLD)
        yy = top + 36
        for ln in lines:
            self.rect(x + 8, yy - 9, w - 16, 14, BG, r=3)
            self.text(ln, x + 14, yy + 1, 7.2, T2, MONO)
            yy += 17

    def browser(self, x, top, w, h, title, lines=(), color=LIME):
        self.rect(x, top, w, h, S1, r=8, stroke=color, lw=1.1)
        self.rect(x, top, w, 20, S2, r=8)
        self.rect(x, top + 12, w, 8, S2)
        for i, col in enumerate([CRIT, WARN, GOOD]):
            self.c.setFillColor(col)
            self.c.circle(x + 10 + i * 8, self.Y(top + 10), 2.3, stroke=0, fill=1)
        self.rect(x + 40, top + 5, w - 50, 10, BG, r=4)
        self.text(title, x + 46, top + 13, 6.6, T3, MONO)
        yy = top + 36
        for ln in lines:
            yy = self.para(ln, x + 10, yy, w - 20, 7.4, T2, 10)

    def actor(self, x, top, label):
        c = self.c
        c.setStrokeColor(T2)
        c.setLineWidth(1.2)
        c.circle(x, self.Y(top + 6), 5.5, stroke=1, fill=0)
        c.line(x, self.Y(top + 12), x, self.Y(top + 26))
        c.line(x - 8, self.Y(top + 17), x + 8, self.Y(top + 17))
        c.line(x, self.Y(top + 26), x - 7, self.Y(top + 35))
        c.line(x, self.Y(top + 26), x + 7, self.Y(top + 35))
        self.text(label, x, top + 47, 7.8, T2, align="center")

    def lane(self, x, top, w, h, title):
        self.rect(x, top, w, h, "#0c0c0c", r=10, stroke="#1f1f1f")
        self.text(title.upper(), x + 10, top + 15, 7, T3, BOLD)

    # ---- content blocks
    def card(self, x, top, w, h, title=None, sub=None, accent=False):
        self.rect(x, top, w, h, S1, r=9, stroke="#4a5f12" if accent else BORDER)
        if title:
            self.text(title, x + 14, top + 22, 11.5, T1, BOLD)
        if sub:
            self.text(sub, x + 14, top + 36, 8, T3)

    def kpi(self, x, top, w, label, value, sub="", accent=False, h=80, color=None):
        self.card(x, top, w, h, accent=accent)
        self.text(label.upper(), x + 14, top + 19, 7.5, T3, BOLD)
        self.text(value, x + 14, top + 47, 22, color or (LIME if accent else T1), BOLD)
        if sub:
            self.para(sub, x + 14, top + 63, w - 28, 8, T2, 10)

    def image(self, img, x, top, w, h=None):
        ir = img if isinstance(img, ImageReader) else ImageReader(str(img))
        iw, ih = ir.getSize()
        h = h or w * ih / iw
        self.c.drawImage(ir, x, self.Y(top + h), w, h, mask="auto")
        return h

    def screen(self, name, x, top, w, crop=None):
        from PIL import Image
        im = Image.open(SCREENS / f"{name}.png").convert("RGB")
        if crop:
            im = im.crop(crop)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        h = w * im.height / im.width
        self.rect(x - 1, top - 1, w + 2, h + 2, BORDER, r=6)
        self.c.drawImage(ImageReader(buf), x, self.Y(top + h), w, h)
        return h

    def bullets(self, items, x, top, width, size=10, gap=6, color=T2):
        yy = top
        for it in items:
            self.rect(x, yy - 6.5, 5, 5, LIME, r=1)
            yy = self.para(it, x + 13, yy, width - 13, size, color, size * 1.35) + gap
        return yy

    def table(self, x, top, cols, rows, row_h=20, hl_last=False):
        """cols: [(label, width, align)]; rows: list of lists of (text, color|None)."""
        wsum = sum(c[1] for c in cols)
        self.rect(x, top, wsum, row_h, S2, r=4)
        xx = x
        for lab, w, al in cols:
            self.text(lab, xx + (w - 10 if al == "right" else 10), top + 13.5, 7.5, T3, BOLD, "right" if al == "right" else "left")
            xx += w
        for i, r in enumerate(rows):
            t = top + row_h * (i + 1)
            last = hl_last and i == len(rows) - 1
            if last:
                self.rect(x, t, wsum, row_h, "#16200a", r=4)
            elif i % 2:
                self.rect(x, t, wsum, row_h, "#101010")
            xx = x
            for (lab, w, al), (val, col) in zip(cols, r):
                self.text(val, xx + (w - 10 if al == "right" else 10), t + 13.5, 9, col or (T1 if last else T2),
                          BOLD if last or col else REG, "right" if al == "right" else "left")
                xx += w
        return top + row_h * (len(rows) + 1)

    def link(self, label, url, x, top, size=9.5, color=LBLUE):
        """Clickable link text."""
        self.text(label, x, top, size, color, REG)
        w = pdfmetrics.stringWidth(label, REG, size)
        self.c.linkURL(url, (x, self.Y(top) - 3, x + w, self.Y(top) + size), relative=0)
        return w

    def note(self, title, body, x, top, w, size=9.6):
        """A short explanatory paragraph in a soft card with a lime accent bar."""
        lines = 0
        probe, line = body.split(), ""
        for w_ in probe:
            nxt = f"{line} {w_}".strip()
            if pdfmetrics.stringWidth(nxt, REG, size) > w - 32 and line:
                lines, line = lines + 1, w_
            else:
                line = nxt
        h = 30 + (lines + 1) * size * 1.4
        self.rect(x, top, w, h, "#0f120b", r=8, stroke="#26300f")
        self.rect(x, top + 8, 3, h - 16, LIME, r=1.5)
        self.text(title.upper(), x + 16, top + 17, 7.5, LIME, BOLD)
        self.para(body, x + 16, top + 32, w - 32, size, T2, size * 1.4)
        return top + h

    def save(self):
        self.footer()
        self.c.save()


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
            ax.text(ref, len(values) - 0.45, f" {ref_label}", color=WARN, fontsize=8)
    else:
        ax.bar(labels, values, color=colors, width=0.6)
        for i, v in enumerate(values):
            ax.text(i, v, fmt(v), ha="center", va="bottom", color=T1, fontsize=9, fontweight="bold")
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, max(values) * 1.22)
    ax.tick_params(length=0)
    return fig_image(fig)


# ----------------------------------------------------------------------------- slides
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
    dc = demand_class_table()
    wape, naive = bt["overall"]["WAPE"], bt["seasonal_naive_overall"]["WAPE"]
    acc = lambda v: f"{1 - v:.1%}"
    n_feat = len(man["features"])
    cutoffs = man["backtest"]["cutoffs"]

    d = Deck(DECK / "celeris_presentation.pdf")

    # 1 ---------------------------------------------------------------- title
    d.page()
    d.text("MKS AI/ML HACKATHON · PHASE 2", 36, 92, 9, LIME, BOLD)
    d.text("Demand forecasting", 36, 140, 38, T1, BOLD)
    d.text("that moves business", 36, 184, 38, LIME, BOLD)
    d.para("Celeris Demand Intelligence Control Tower: messy ERP data cleaned and explained, true demand recovered, "
           "a validated 19-month forecast with calibrated uncertainty, and a control tower that turns it into decisions.",
           36, 214, 430, 11, T2, 15)
    d.text(f"{AUTHOR}  ·  {INSTITUTE}", 36, 272, 12.5, T1, BOLD)
    tiles = [("19-month forecast", f"{fu(k['units_19m'])} units", "Nov 2026 – May 2028", True),
             ("Forecast accuracy", acc(bt["total_month"]["WAPE"]), f"company · {acc(bt['family_month']['WAPE'])} family · {acc(wape)} SKU", False),
             ("Revenue · next 12 m", f"${k['revenue_next12'] / 1e9:.2f}B", f"{k['revenue_next12_vs_last12']:+.1%} vs last 12 months", False),
             ("Actions ranked", f"{k['exceptions']}", f"{k['exceptions_by_priority']['CRITICAL']} critical · {k['exceptions_by_priority']['HIGH']} high", False)]
    for i, (lab, val, sub, a) in enumerate(tiles):
        d.kpi(36 + (i % 2) * 218, 300 + (i // 2) * 92, 208, lab, val, sub, accent=a)
    d.screen("home", 488, 140, 436)
    d.text("GITHUB", 488, 432, 7.5, T3, BOLD)
    d.link(GITHUB.replace("https://", ""), GITHUB, 488, 446)
    d.text("LIVE DEMO (college server)", 488, 468, 7.5, T3, BOLD)
    d.link(LIVE.replace("http://", ""), LIVE, 488, 482)

    # 2 ---------------------------------------------------------------- challenge & answer
    d.page("The challenge and our answer", "From a messy ERP extract to confident planning decisions",
           f"A 19-month forecast for {k['series']:,} SKU x region series, from data that is dirty, censored by stockouts and shaken by events - "
           "plus a control tower that explains every number.")
    probs = [("Messy data", f"{rr['rows_ingested']:,} rows with duplicates, date and label variants, unit errors, gaps", CRIT),
             ("Hidden demand", "stockouts make shipments lower than what customers wanted", WARN),
             ("Long horizon", "19 months ahead, per SKU and region, with honest uncertainty", BLUE),
             ("Decisions", "what to order, where capacity is short, who must act and when", LIME)]
    for i, (t, s, col) in enumerate(probs):
        x = 36 + i * 226
        d.rect(x, 152, 214, 84, S1, r=8, stroke=BORDER)
        d.rect(x, 160, 3, 68, col, r=1.5)
        d.text(t, x + 14, 174, 11, T1, BOLD)
        d.para(s, x + 14, 192, 190, 8.8, T2, 11.5)
    d.text("What we delivered", 36, 270, 13, T1, BOLD)
    deliv = [("Clean", f"{dq['total_issues']:,} fixes, each logged with its rule"),
             ("Recover", f"{an['total']:,} anomalies; stockout demand rebuilt"),
             ("Learn", f"{n_feat} features, macro leads, EV shift"),
             ("Forecast", f"{acc(wape)} SKU accuracy, calibrated P10–P90"),
             ("Decide", "12-view control tower, API, upload & score")]
    for i, (t, s) in enumerate(deliv):
        x = 36 + i * 181
        d.rect(x, 284, 171, 74, S1, r=8, stroke=BORDER)
        d.text(f"0{i + 1}", x + 12, 304, 8, LIME, BOLD)
        d.text(t, x + 32, 304, 12, T1, BOLD)
        d.para(s, x + 12, 324, 150, 8.8, T2, 11.5)
    d.bullets([f"Validated on {len(cutoffs)} rolling-origin cutoffs over the full 19-month horizon - never on months the model trained on",
               "Reproducible end to end: one command rebuilds every output; a frozen model, a typed data contract and SHA-256 fingerprints "
               "guarantee the dashboard shows exactly the validated numbers"], 36, 384, 880, 10.5)
    d.note("In one sentence", "We treat forecasting as a product, not a notebook: the data is cleaned with a written reason for every change, "
           "the model is judged only on months it has never seen, and the dashboard can only show numbers that passed validation - "
           "so a planner can trust a figure and trace it back to the raw row it came from.", 36, 436, 888)

    # 3 ---------------------------------------------------------------- architecture (layered system design)
    d.page("System design · architecture", "Layered architecture: batch intelligence, frozen contract, live serving",
           "Sources feed a batch pipeline that writes versioned, validated stores; a stateless API serves them to the browser and runs scenario and scoring jobs.")
    lanes = [(36, "Sources"), (186, "Batch pipeline · python"), (420, "Storage"), (592, "Serving · FastAPI"), (770, "Client")]
    widths = [140, 224, 162, 168, 154]
    for (x, t), w in zip(lanes, widths):
        d.lane(x, 146, w, 352, t)
    srcs = [("train.csv", "248k sales rows"), ("test.csv", "58,219 keys"), ("sku_master.csv", "lifecycle, successor"),
            ("inventory_stockouts", "shortfalls"), ("events_calendar", "strikes, shutdowns"), ("macro_indicators", "PMI, auto, EV")]
    for i, (t, s) in enumerate(srcs):
        d.doc(48, 168 + i * 52, 116, 40, t, s)
    stages = [("Clean + DQ log", "42k fixes"), ("Anomalies + recovery", "true demand"), ("Drivers + features", f"{n_feat} features"),
              ("Backtest + registry", "19 experiments"), ("Freeze + validate", "manifest, SHA-256"), ("Planning intelligence", "351 actions")]
    for i, (t, s) in enumerate(stages):
        d.process(198, 168 + i * 52, 200, 40, i + 1, t, s, LIME if i in (0, 3) else LBLUE if i in (1, 2) else GOOD if i == 4 else WARN)
        if i:
            d.line([(298, 168 + i * 52 - 12), (298, 168 + i * 52)], T3, 1)
    for i in range(6):
        d.line([(164, 188 + i * 52), (196, 188 + i * 52)] if i < 2 else [(164, 188 + i * 52), (180, 188 + i * 52), (180, 188), (196, 188)], T3, 0.9, head=i < 2)
    stores = [("Parquet store", "clean panel, demand"), ("Experiment registry", "metrics, predictions"),
              ("Frozen outputs", "forecast, bands, model"), ("Data contract", "YAML: grain, keys, types")]
    for i, (t, s) in enumerate(stores):
        d.cylinder(434, 168 + i * 80, 134, 64, t, s, BLUE if i < 2 else LIME)
    for (y1, y2) in [(188, 200), (344, 248), (400, 330)]:
        d.line([(398, y1), (432, y2)], T3, 1)
    d.server(604, 168, 144, 186, "api/app.py", ["/views/*  filters", "/datasets/*", "/intelligence/*", "/scenario", "/score/jobs", "/  (dashboard)"], BLUE)
    d.rect(604, 366, 144, 116, S1, r=8, stroke=BORDER)
    d.text("Background worker", 616, 384, 8.6, T1, BOLD)
    d.para("upload scoring: clean -> recover -> features -> frozen model -> bands", 616, 398, 122, 7.4, T2, 9.5)
    d.line([(568, 200), (602, 230)], T3, 1)
    d.line([(568, 360), (602, 300)], T3, 1)
    d.line([(676, 354), (676, 366)], T3, 1)
    d.browser(782, 168, 130, 186, "localhost:8000", ["React 18 + TypeScript", "ECharts charts", "12 views", "global filters in URL", "PDF + CSV export"])
    d.line([(748, 250), (780, 250)], LIME, 1.4)
    d.line([(780, 270), (748, 270)], T3, 1)
    d.label("JSON", 764, 244)
    d.actor(846, 392, "Planner / manager")
    d.line([(846, 380), (846, 356)], T3, 1)

    # 4 ---------------------------------------------------------------- data flow (DAG)
    d.page("System design · data flow", "How a raw row becomes a decision",
           "Every stage reads only the previous stage's validated output and writes a machine-readable report. No feature uses data after the forecast origin.")
    nodes = [(36, 160, "Raw extract", f"{rr['rows_ingested']:,} rows", T3), (196, 160, "Clean panel", f"{rr['rows_clean']:,} rows", LIME),
             (356, 160, "Unconstrained demand", f"{an['by_category']['stockout']:,} stockouts rebuilt", LBLUE),
             (516, 160, "Feature frames", f"{n_feat} features x 19 horizons", LBLUE), (676, 160, "Global LightGBM", "Tweedie, one model", LIME),
             (816, 160, "Forecast", "58,219 rows", LIME)]
    for i, (x, t, title, sub, col) in enumerate(nodes):
        w = 128 if i < 5 else 108
        d.rect(x, t, w, 58, S1, r=8, stroke=col, lw=1.1)
        d.text(title, x + 10, t + 24, 9.5, T1, BOLD)
        d.text(sub, x + 10, t + 40, 7.6, T2)
        if i < 5:
            d.line([(x + w, t + 29), (nodes[i + 1][0], t + 29)], LIME, 1.4)
    side = [(196, 262, "DQ issue log", f"{dq['total_issues']:,} fixes"), (356, 262, "Anomaly register", f"{an['total']:,} months"),
            (516, 262, "Drivers", "lead / lag, EV shift"), (676, 262, "Backtest", f"{len(cutoffs)} cutoffs, {len(reg)} runs"),
            (816, 262, "Bands", "P10 / P50 / P90")]
    for x, t, title, sub in side:
        d.cylinder(x + 6, t, 108, 58, title, sub, BLUE)
        d.line([(x + 60, 218), (x + 60, t)], T3, 0.9, dash=(2, 2))
    d.rect(516, 360, 408, 58, S1, r=8, stroke=GOOD, lw=1.1)
    d.text("Planning intelligence", 528, 384, 9.5, T1, BOLD)
    d.text(f"{k['exceptions']} ranked actions · procurement plan · capacity and supply risk · scenarios", 528, 400, 7.6, T2)
    d.line([(870, 320), (870, 358)], GOOD, 1.2)
    d.rect(36, 360, 460, 58, S1, r=8, stroke=WARN, lw=1.1)
    d.text("Business rules the model cannot learn", 48, 384, 9.5, T1, BOLD)
    d.text("zero outside launch-EOL · successor ramp x predecessor run-down · customer shutdowns", 48, 400, 7.6, T2)
    d.line([(496, 389), (514, 389)], WARN, 1.2)
    d.bullets(["No look-ahead: features use data up to the origin only; calendar, lifecycle, scheduled events and macro values are the only known-future inputs",
               "The model learns demand, not shipments: stockout months are rebuilt from the stockout file and diff-in-diff estimates before training"],
              36, 448, 880, 9.5, 4)

    # 5 ---------------------------------------------------------------- data quality + true demand
    d.page("Data quality and true demand", "Every fix logged, every anomaly explained",
           f"{dq['total_issues']:,} corrections across 6 files (validation PASS) and {an['total']:,} flagged months on {an['series_affected']:,} series, each with type, reason, action and confidence.")
    labels = ["Label variants", "Date formats", "Missing values recovered", "Duplicates removed", "Price fixes", "Unit errors"]
    vals = [rr["label_corrections"], rr["date_corrections"], rr["missing_values_recovered"], rr["duplicates_removed"], rr["price_corrections"], rr["unit_corrections"]]
    d.card(36, 150, 436, 292, "Corrections by type", "stage-1 run report")
    d.image(bar_chart(labels, vals, [LIME] * 6, lambda v: f"{v:,.0f}", w=5.4, h=3.0), 48, 194, 412)
    cats = ["stockout", "real_event", "data_error", "gap", "spike", "unknown"]
    nm = {"stockout": "Stockout (recovered)", "real_event": "Real event", "data_error": "Data error", "gap": "Missing month",
          "spike": "One-off spike", "unknown": "Unexplained drop"}
    d.card(488, 150, 436, 292, "Flagged months by category", "anomaly register")
    d.image(bar_chart([nm[c] for c in cats], [an["by_category"].get(c, 0) for c in cats], [CRIT, BLUE, WARN, T3, LIME, LBLUE],
                      lambda v: f"{v:,.0f}", w=5.4, h=3.0), 500, 194, 412)
    d.bullets([f"train.csv {rr['rows_ingested']:,} -> {rr['rows_clean']:,} rows; reloads and duplicate keys removed; x10 unit blocks rebuilt from revenue and the stockout file",
               "Events are measured before they are excluded: only events with a material impact are kept out of training"], 36, 462, 880, 9.5, 3)

    # 6 ---------------------------------------------------------------- model + validation design
    d.page("Model and validation", f"One global model, {n_feat} features, tested like production",
           f"Direct multi-horizon LightGBM (Tweedie loss on demand/scale) over every series. Rolling-origin backtest: train before each origin, "
           f"forecast the next 19 months, repeat {len(cutoffs)} times.")
    groups = [("Demand history", "lags 1-12, rolling stats, last year", LIME), ("Seasonality", "family x region index", BLUE),
              ("Lifecycle", "age, months to EOL, ramp", WARN), ("Macro leads", "auto output, orders, PMI, EV", LBLUE),
              ("Calendar & events", "holidays, shutdowns, strikes", GOOD), ("Attributes", "family, region, channel, customer", T3)]
    d.card(36, 150, 360, 300, "Feature groups")
    for i, (t, s, col) in enumerate(groups):
        x, top = 50 + (i % 2) * 170, 182 + (i // 2) * 84
        d.rect(x, top, 160, 72, S2, r=7)
        d.rect(x, top + 8, 3, 56, col, r=1.5)
        d.text(t, x + 12, top + 24, 9.5, T1, BOLD)
        d.para(s, x + 12, top + 40, 140, 8.2, T2, 10.5)
    d.card(412, 150, 512, 300, "Rolling-origin backtest", "train (grey) · 19-month test window (lime) · same folds for all 19 experiments")
    x0, x1 = 470, 904
    t0, t1 = 2019.0, 2026 + 10 / 12

    def xm(ym: str) -> float:
        y_, m_ = int(ym[:4]), int(ym[5:])
        return x0 + (y_ + (m_ - 1) / 12 - t0) / (t1 - t0) * (x1 - x0)
    for i, c in enumerate(cutoffs):
        top = 196 + i * 36
        e = int(c[:4]) * 12 + int(c[5:]) - 1 + 19
        end = f"{e // 12}-{e % 12 + 1:02d}"
        d.text(f"fold {i + 1}", 426, top + 11, 7.5, T3)
        d.rect(x0, top, xm(c) - x0, 16, S3, r=3)
        d.rect(xm(c), top, min(xm(end), x1) - xm(c), 16, LIME, r=3)
        d.text(c, xm(c) - 5, top + 11.5, 7, T2, align="right")
    for yr in range(2019, 2027):
        d.text(str(yr), xm(f"{yr}-01"), 424, 7.5, T3, align="center")
    d.note("Why this design", "One model for every series lets small, sparse products borrow patterns from large ones, and predicting "
           "demand divided by each series' own scale keeps big and small series on the same footing. Each row asks 'standing at "
           "this month, what will demand be h months later?', so the same model covers all 19 horizons without feeding its own errors back in.",
           36, 460, 888, 9.2)

    # 7 ---------------------------------------------------------------- accuracy incl. demand classes
    d.page("Accuracy", f"{acc(bt['total_month']['WAPE'])} at company level, beats the baseline in every demand class",
           "Accuracy = 1 - WAPE on the 6-cutoff backtest (months the model never saw). Baseline = seasonal naive (same month last year).")
    for i, (lab, val, sub, a) in enumerate([("Company x month", acc(bt["total_month"]["WAPE"]), "total demand", True),
                                             ("Family x month", acc(bt["family_month"]["WAPE"]), "planning level", False),
                                             ("SKU x region x month", acc(wape), f"baseline {acc(naive)}", False),
                                             ("Bias", f"{bt['overall']['Bias']:+.1%}", "slight under-forecast", False)]):
        d.kpi(36 + i * 226, 146, 214, lab, val, sub, accent=a, h=74)
    d.card(36, 234, 500, 268, "Accuracy by demand class (Syntetos-Boylan)", "SKU x region x month · 6 cutoffs")
    rows = []
    for r in dc:
        name = "All series" if r["class"] == "all" else r["class"].capitalize()
        gain = (1 - r["model"]) - (1 - r["naive"])
        rows.append([(name, None), (f"{r['series']:,}", None), (f"{r['share']:.0%}", None), (acc(r["model"]), LIME),
                     (acc(r["naive"]), None), (f"+{gain * 100:.1f} pts", GOOD)])
    d.table(50, 280, [("Demand class", 116, "l"), ("Series", 62, "right"), ("Volume", 62, "right"), ("Model", 76, "right"),
                      ("Baseline", 76, "right"), ("Gain", 80, "right")], rows, row_h=24, hl_last=True)
    hb = ["1-3m", "4-6m", "7-12m", "13-19m"]
    d.card(552, 234, 372, 268, "Accuracy by horizon", "SKU level · model (lime) vs baseline level (dashed)")
    fig, ax = plt.subplots(figsize=(4.6, 2.75))
    vals = [1 - bt["by_horizon_bucket"][h]["WAPE"] for h in hb]
    ax.set_axisbelow(True)
    ax.bar(hb, vals, color=LIME, width=0.58)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.1%}", ha="center", color=T1, fontsize=9, fontweight="bold")
    ax.axhline(1 - naive, color=T3, ls="--", lw=1.2)
    ax.text(3.35, 1 - naive + 0.012, f"baseline {1 - naive:.0%}", color=T3, fontsize=8, ha="right")
    ax.set_ylim(0.5, 0.8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)
    d.image(fig_image(fig), 566, 280, 344)

    # 8 ---------------------------------------------------------------- experiments + uncertainty
    d.page("Model selection and uncertainty", f"{len(reg)} experiments, one promotion rule, calibrated bands",
           "A challenger is promoted only if it lowers WAPE, wins most cutoffs and is worse on none. Bands: stratified split-conformal on the model's own backtest.")
    regs = sorted(reg, key=lambda r: r["WAPE"])[:10]
    sel = man["selected_model"]
    d.card(36, 150, 468, 348, "Accuracy by experiment (best 10)", "SKU level · selected model lime, first champion blue")
    d.image(bar_chart([r["experiment"].replace("_", " ") for r in regs], [1 - r["WAPE"] for r in regs],
                      [LIME if r["experiment"] == sel else BLUE if r["experiment"] == "champion" else T3 for r in regs],
                      lambda v: f"{v:.2%}", w=5.6, h=3.9), 48, 194, 444)
    lv = {}
    for r in cov:
        lv.setdefault(r["Level"], []).append(r["Coverage_P10_P90"])
    levels = [l_ for l_ in ["total", "family", "region", "channel", "customer", "family_region"] if l_ in lv]
    d.card(520, 150, 404, 252, "Held-out P10–P90 coverage", "target 80% · mean over 6 cutoffs")
    d.image(bar_chart([l_.replace("_", " x ") for l_ in levels], [sum(lv[l_]) / len(lv[l_]) for l_ in levels], [LBLUE] * len(levels),
                      lambda v: f"{v:.0%}", w=4.9, h=2.4, ref=0.8, ref_label="80%"), 532, 194, 380)
    d.kpi(520, 414, 404, "19-month total · P10 – P90", f"{fu(k['units_19m_p10'])} – {fu(k['units_19m_p90'])}",
          f"point forecast {fu(k['units_19m'])} units", accent=True, h=84)

    # 9 ---------------------------------------------------------------- forecast + decisions
    d.page("Forecast and decisions", f"{fu(k['units_19m'])} units over Nov 2026 – May 2028, turned into ranked actions",
           f"Next 12 months: {fu(k['units_next12'])} units ({k['units_next12_vs_last12']:+.1%}) and ${k['revenue_next12'] / 1e9:.2f}B revenue "
           f"({k['revenue_next12_vs_last12']:+.1%}) at the announced list prices.")
    hist, fc = tl["history"][-48:], tl["forecast"]
    fig, ax = plt.subplots(figsize=(11, 2.2))
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
    d.card(36, 146, 888, 238, "Company demand: history -> forecast", "recovered (unconstrained) demand, calibrated company band")
    d.image(fig_image(fig), 48, 186, 864)
    for i, (lab, val, sub, col) in enumerate([("Critical actions", str(k["exceptions_by_priority"]["CRITICAL"]), f"{k['exceptions']} ranked, each with owner and deadline", CRIT),
                                               ("Next-cycle cover", f"${pl['cover_value_usd'] / 1e6:.0f}M", f"{fu(pl['cover_units'])} units, 3-month lead time", None),
                                               ("Service level", f"{pl['service_level_revenue_weighted']:.1%}", "revenue-weighted ABC-XYZ target", None),
                                               ("Capacity flags", str(k["capacity_flags"].get("ABOVE_DEMONSTRATED_THROUGHPUT", 0)), "family x region above demonstrated throughput", WARN)]):
        d.kpi(36 + i * 226, 396, 214, lab, val, sub, color=col, h=88)

    # 10 --------------------------------------------------------------- control tower
    d.page("The control tower", "12 views, global filters, every number from the contract",
           "Overview · Demand Explorer · Risk & Exceptions · Planning · Scenario Lab · Model Trust · Upload & Forecast · Calendar · Macro Drivers · Data Health · Anomaly Monitor")
    d.screen("overview", 36, 146, 440, crop=(0, 0, 1600, 900))
    d.screen("risk", 484, 146, 440, crop=(0, 0, 1600, 900))
    for i, n in enumerate(["explorer", "planning", "scenarios", "trust"]):
        d.screen(n, 36 + i * 224, 404, 216, crop=(260, 130, 1600, 580))

    # 11 --------------------------------------------------------------- upload & forecast (sequence diagram)
    d.page("System design · Upload & Forecast", "Sequence: scoring an uploaded file with the frozen model",
           "Same cleaning, demand recovery, features, model, business rules and bands as the official run. Uploading the official files reproduces the frozen submission exactly (tested).")
    parts = [("Planner", 70), ("Browser (React)", 210), ("FastAPI", 370), ("Job worker", 530), ("Pipeline modules", 690), ("Frozen model", 850)]
    for name, x in parts:
        if name == "Planner":
            d.actor(x, 140, name)
        else:
            d.rect(x - 62, 146, 124, 30, S2, r=6, stroke=LIME if name in ("Job worker", "Frozen model") else BLUE, lw=1)
            d.text(name, x, 165, 8.8, T1, BOLD, "center")
        d.line([(x, 190), (x, 456)], "#3a3a3a", 0.8, dash=(3, 3), head=False)
    msgs = [(70, 210, 206, "drop train / test CSV"), (210, 370, 228, "POST /score/uploads"), (370, 210, 250, "format, rows, months, checks"),
            (210, 370, 272, "POST /score/jobs (origin)"), (370, 530, 294, "queue job"), (530, 690, 316, "clean -> recover -> features"),
            (690, 850, 338, "predict (no look-ahead)"), (850, 530, 360, "forecast + rules + P10-P90"), (530, 530, 382, "accuracy vs actuals, revenue"),
            (210, 370, 404, "GET /score/jobs/{id}  (progress)"), (370, 210, 426, "result JSON, CSV downloads"), (210, 70, 448, "charts, accuracy, PDF report")]
    for x1, x2, t, lab in msgs:
        if x1 == x2:
            d.line([(x1, t - 6), (x1 + 34, t - 6), (x1 + 34, t + 4), (x1 + 4, t + 4)], LIME, 1)
            d.text(lab, x1 + 40, t + 1, 7.4, T2)
            continue
        back = x2 < x1
        d.line([(x1, t), (x2 + (4 if back else -4), t)], T3 if back else LIME, 1, dash=(3, 2) if back else None)
        d.label(lab, (x1 + x2) / 2, t - 3, T1 if not back else T2, 7.2)
    for x, t, h in [(370, 222, 210), (530, 288, 100), (690, 310, 34), (850, 332, 34)]:
        d.rect(x - 4, t, 8, h, "#2b3a0c", r=2)
    d.note("What this proves", "Upload & Forecast is not a separate model: it calls the same cleaning, recovery and feature code "
           "and the same frozen model file. Uploading the official train.csv and test.csv returns the frozen submission row for row "
           "(58,219 rows, difference below 1e-13 units) - a built-in reproducibility test.", 36, 462, 888, 9.2)

    # 12 --------------------------------------------------------------- deployment + engineering + close
    d.page("System design · deployment and quality", "One server to run, one command to rebuild, tests on every number",
           "deploy.sh runs the pipeline, builds the dashboard and starts one uvicorn process; model experiments run on a separate GPU server.")
    d.lane(36, 150, 556, 248, "Deployment")
    d.server(56, 182, 236, 196, "App server · uvicorn :8000", ["FastAPI  /views /score ...", "dashboard/dist (React build)", "outputs/final + intelligence",
                                                              "outputs/scoring (uploads)", "contract + manifest checks"], BLUE)
    d.server(324, 182, 248, 112, "GPU server · experiments", ["run_backtest.py  (6 cutoffs)", "registry -> promotion rule", "promoted model -> app server"], LIME)
    d.rect(324, 306, 248, 72, S1, r=8, stroke=BORDER)
    d.text("Optional nginx", 336, 326, 8.6, T1, BOLD)
    d.para("custom domain: /api -> :8000, static files; the app also strips /api itself", 336, 340, 226, 7.4, T2, 9.5)
    d.line([(324, 280), (294, 280)], T3, 1, dash=(3, 2))
    d.text("Engineering quality", 612, 166, 12, T1, BOLD)
    d.bullets(["214 tests: 173 backend (pytest) + 41 frontend (vitest)", "data contract: every dataset's grain, key, columns and types",
               "frozen backend: SHA-256 manifest, validation all PASS", "experiment registry with an explicit promotion rule",
               "one command rebuilds everything: python run_pipeline.py"], 612, 190, 312, 9.5, 5)
    d.note("How it runs", "Experiments run on the GPU server and only a model that passes the promotion rule is frozen. The app "
           "server then serves that frozen state: the API reads only contract-checked files and the dashboard only calls the API, "
           "so what a judge sees is exactly what was validated.", 612, 300, 312, 9)
    d.text("Thank you", 36, 446, 34, LIME, BOLD)
    d.text(f"{AUTHOR} · {INSTITUTE}", 300, 440, 12, T1, BOLD)
    d.text("GitHub:", 300, 458, 9, T3); d.link(GITHUB.replace("https://", ""), GITHUB, 340, 458, 9)
    d.text("Live demo:", 612, 458, 9, T3); d.link(LIVE.replace("http://", ""), LIVE, 664, 458, 9)
    d.text(f"{fu(k['units_19m'])} units forecast · {acc(bt['total_month']['WAPE'])} company accuracy · {k['exceptions']} ranked actions · 12 views",
           36, 486, 11, T2)
    d.save()
    print(f"wrote {DECK / 'celeris_presentation.pdf'} ({d.n} slides)")


if __name__ == "__main__":
    main()
