/**
 * PDF report of one Upload & Forecast run, in the dashboard's design: the same dark palette,
 * lime accent, cards and KPI tiles, and the SAME ECharts options rendered offscreen, so the
 * charts in the PDF are the charts on the page. Text is real (selectable) PDF text.
 */
import type { EChartsCoreOption } from "echarts/core";
import type { ScoreMetrics, ScoreResult } from "../api/types";
import { echarts, THEME_NAME } from "../charts/echarts";
import { timelineOption, verticalBarsOption } from "../charts/options";
import { fmtInt, fmtPct, fmtPctChange, fmtUnits, fmtUsd } from "../lib/format";
import { Pdf } from "../lib/pdf";
import { SERIES } from "../theme/chart";
import { accuracyOption } from "./UploadForecast";

const C = {
  bg: "#080808", s1: "#141414", s2: "#1c1c1c", border: "#282828", t1: "#ffffff", t2: "#a1a1a1", t3: "#707070",
  accent: "#c7ff32", good: "#34d399", warn: "#f5b942", crit: "#ff5c5c", blue: "#3478f6",
};
const M = 36;              // page margin
const GAP = 12;
const TL_H = 188;          // timeline chart height (pt)
const BAR_H = 165;         // family / region chart height (pt)

/** The page's bar chart, with room on the left for the rotated category labels. */
function bars(cats: string[], data: number[], color: string): EChartsCoreOption {
  const o = verticalBarsOption(cats, [{ name: "Forecast units", data, color }],
    { valueFormatter: (v) => fmtUnits(v, 1), showLabels: true, rotateLabels: true }) as { grid?: object };
  return { ...o, grid: { ...(o.grid ?? {}), left: 64, right: 10, containLabel: true } };
}

interface Shot { url: string; w: number; h: number }

/** Render an ECharts option offscreen (no animation) to a JPEG on the card colour. */
async function shoot(option: EChartsCoreOption, width: number, height: number, scale = 2): Promise<Shot> {
  const div = document.createElement("div");
  div.style.cssText = `position:fixed;left:-10000px;top:0;width:${width}px;height:${height}px;`;
  document.body.appendChild(div);
  try {
    const chart = echarts.init(div, THEME_NAME, { renderer: "canvas", width, height });
    chart.setOption({ ...option, animation: false, dataZoom: undefined }, true);
    const png = chart.getDataURL({ type: "png", pixelRatio: scale, backgroundColor: C.s1 });
    chart.dispose();
    const img = await new Promise<HTMLImageElement>((ok, bad) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = bad;
      i.src = png;
    });
    const cv = document.createElement("canvas");
    cv.width = img.naturalWidth;
    cv.height = img.naturalHeight;
    const ctx = cv.getContext("2d")!;
    ctx.fillStyle = C.s1;
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0);
    return { url: cv.toDataURL("image/jpeg", 0.92), w: cv.width, h: cv.height };
  } finally {
    div.remove();
  }
}

export async function buildScoreReport(r: ScoreResult, jobId: string): Promise<Blob> {
  const pdf = new Pdf();
  const CW = pdf.W - 2 * M;                      // content width
  const acc = r.accuracy;
  const k = r.kpis;

  // charts first (async), at the pixel size of their slot (2x for print sharpness)
  const pt = (v: number) => Math.round(v * 1.33);
  const [tl, fam, reg, accShot] = await Promise.all([
    shoot(timelineOption(r.timeline, "units", { showShipped: true }), pt(CW - 24), pt(TL_H)),
    shoot(bars(r.by_family.map((x) => x.Member), r.by_family.map((x) => x.Units), SERIES[0]), pt((CW - GAP) / 2 - 24), pt(BAR_H)),
    shoot(bars(r.by_region.map((x) => x.Member), r.by_region.map((x) => x.Units), SERIES[1]), pt((CW - GAP) / 2 - 24), pt(BAR_H)),
    acc ? shoot(accuracyOption(acc.monthly), pt(CW - 24), pt(210)) : Promise.resolve(null),
  ]);

  let y = 0;
  const newPage = () => {
    pdf.addPage(C.bg);
    // header band
    pdf.rect(M, 26, 18, 18, C.s2, { r: 4 });
    pdf.line(M + 4, 39, M + 8, 34, C.accent, 1.4);
    pdf.line(M + 8, 34, M + 11, 37, C.accent, 1.4);
    pdf.line(M + 11, 37, M + 14, 31, C.accent, 1.4);
    pdf.text("CELERIS", M + 26, 39, { size: 10, bold: true });
    pdf.text("AI Demand Control Tower · Upload & Forecast report", M + 80, 39, { size: 8, color: C.t3 });
    pdf.text(new Date().toISOString().slice(0, 16).replace("T", " "), pdf.W - M, 39, { size: 8, color: C.t3, align: "right" });
    pdf.line(M, 54, pdf.W - M, 54, C.border);
    y = 72;
  };
  const ensure = (h: number) => { if (y + h > pdf.H - 52) newPage(); };
  /** Card with a title, a wrapped subtitle and a content slot of contentH points; returns the slot's top. */
  const card = (title: string, subtitle: string | null, contentH: number) => {
    const sub = subtitle ? pdf.wrap(subtitle, CW - 24, 7.5) : [];
    const head = 28 + sub.length * 10;
    const h = head + contentH + 14;
    ensure(h);
    pdf.rect(M, y, CW, h, C.s1, { r: 8, stroke: C.border });
    pdf.text(title, M + 12, y + 20, { size: 11, bold: true });
    sub.forEach((l, i) => pdf.text(l, M + 12, y + 33 + i * 10, { size: 7.5, color: C.t3 }));
    const top = y + head + 4;
    y += h + GAP;
    return top;
  };

  // ------------------------------------------------------------------ page 1: summary + forecast
  newPage();
  pdf.text("UPLOAD & FORECAST · THE FROZEN MODEL ON YOUR DATA", M, y, { size: 7.5, bold: true, color: C.accent });
  y += 22;
  pdf.text("Forecast report", M, y, { size: 22, bold: true });
  y += 18;
  const inputs = `${r.inputs.history === "uploaded" ? "Your sales history" : "Official history"} to ${r.inputs.cutoff} · ` +
    `${r.inputs.rows_to_forecast === "uploaded" ? "your rows to forecast" : r.inputs.rows_to_forecast} · ` +
    `horizon ${r.inputs.horizon[0]} -> ${r.inputs.horizon[1]} (${r.inputs.horizon_months} months) · ` +
    `model ${r.model.name.replace(/_/g, " ")} (frozen ${r.model.frozen_at}, trained through ${r.model.trained_through}) · scored in ${r.seconds}s`;
  y = pdf.paragraph(inputs, M, y, CW, { size: 8.5, color: C.t2, lineHeight: 12 }) + 6;

  const banner = (text: string, color: string) => {
    const lines = pdf.wrap(text, CW - 30, 8.5);
    const h = lines.length * 12 + 14;
    ensure(h);
    pdf.rect(M, y, CW, h, C.s1, { r: 6, stroke: C.border });
    pdf.rect(M, y, 3, h, color);
    lines.forEach((l, i) => pdf.text(l, M + 14, y + 16 + i * 12, { size: 8.5, color: C.t2 }));
    y += h + 8;
  };
  const fc = r.frozen_comparison;
  if (fc) banner(fc.identical
    ? `Identical to the frozen submission on all ${fmtInt(fc.rows)} overlapping rows (largest difference ${fc.max_abs_diff.toExponential(1)} units): the pipeline is reproducible.`
    : `On the ${fmtInt(fc.rows)} rows that are also in the frozen forecast, this data moves the total by ${fmtPctChange(fc.change_pct)} (${fmtInt(fc.total_frozen)} -> ${fmtInt(fc.total)} units).`,
  fc.identical ? C.good : C.blue);
  r.warnings.forEach((w) => banner(w, C.warn));
  y += 4;

  // KPI tiles
  const better = acc?.overall.WAPE != null && acc.overall.Naive_WAPE ? 1 - acc.overall.WAPE / acc.overall.Naive_WAPE : null;
  const ch = r.checks;
  const tiles: { label: string; value: string; sub: string; foot: string; accent?: boolean }[] = [
    { label: "ROWS FORECAST", value: fmtInt(k.rows), sub: `${fmtInt(k.series)} SKU x region series · ${r.inputs.horizon_months} months`,
      foot: k.zero_by_lifecycle ? `${fmtInt(k.zero_by_lifecycle)} rows 0 by lifecycle rule` : "Lifecycle, launch, shutdown rules" },
    { label: "FORECAST DEMAND", value: `${fmtUnits(k.units, 2)} units`, sub: `P10-P90 ${fmtUnits(k.units_p10, 2)} - ${fmtUnits(k.units_p90, 2)}`,
      foot: k.band_method.split("(")[0].trim(), accent: true },
    { label: "FORECAST REVENUE", value: fmtUsd(k.revenue, 2), sub: "At each forecast year's list prices", foot: "History price book + announced rises" },
    acc
      ? { label: "ACCURACY (WAPE)", value: fmtPct(acc.overall.WAPE), sub: better !== null ? `${fmtPct(better, 0)} below seasonal naive (${fmtPct(acc.overall.Naive_WAPE)})` : "",
        foot: `${fmtInt(acc.overall.rows)} rows · ${acc.in_sample ? "in-sample" : "out-of-sample"}`, accent: !acc.in_sample }
      : { label: ch.cleaning ? "DATA FIXED" : "HISTORY CHECKS", value: fmtInt(ch.cleaning?.issues ?? ch.anomalies.flagged),
        sub: ch.cleaning ? `${fmtInt(ch.cleaning.rows_in)} -> ${fmtInt(ch.cleaning.rows_clean)} rows` : "months flagged in the history",
        foot: ch.cleaning ? "Every fix in the issue log" : "Official history" },
  ];
  const tw = (CW - 3 * 8) / 4;
  ensure(84);
  tiles.forEach((t, i) => {
    const x = M + i * (tw + 8);
    pdf.rect(x, y, tw, 84, C.s1, { r: 8, stroke: t.accent ? "#4a5f12" : C.border });
    pdf.text(t.label, x + 10, y + 18, { size: 6.5, bold: true, color: C.t3, maxWidth: tw - 20 });
    pdf.text(t.value, x + 10, y + 42, { size: 15, bold: true, color: t.accent ? C.accent : C.t1, maxWidth: tw - 20 });
    pdf.paragraph(t.sub, x + 10, y + 58, tw - 20, { size: 6.8, color: C.t2, lineHeight: 8.5 });
    pdf.text(t.foot, x + 10, y + 77, { size: 6.2, color: C.t3, maxWidth: tw - 20 });
  });
  y += 84 + GAP;

  const chartCard = (title: string, subtitle: string, shot: Shot, hPt: number) => {
    const top = card(title, subtitle, hPt);
    pdf.image(shot.url, shot, M + 12, top, CW - 24, hPt);
  };
  chartCard("Forecast", `History to ${r.inputs.cutoff} and the forecast with its P10-P90 band · ${r.timeline.band_method}`, tl, TL_H);

  // family + region side by side
  const half = (CW - GAP) / 2;
  const barCard = BAR_H + 52;
  ensure(barCard);
  [["By product family", fam], ["By region", reg]].forEach(([title, shot], i) => {
    const x = M + i * (half + GAP);
    pdf.rect(x, y, half, barCard, C.s1, { r: 8, stroke: C.border });
    pdf.text(title as string, x + 12, y + 20, { size: 11, bold: true });
    pdf.text("Forecast units over the horizon", x + 12, y + 33, { size: 7.5, color: C.t3 });
    pdf.image((shot as Shot).url, shot as Shot, x + 12, y + 42, half - 24, BAR_H);
  });
  y += barCard + GAP;

  // ------------------------------------------------------------------ accuracy
  const table = (cols: { label: string; w: number; right?: boolean }[], rows: string[][], x0 = M + 12, width = CW - 24) => {
    const total = cols.reduce((s, c) => s + c.w, 0);
    const scale = width / total;
    const rowH = 15;
    ensure(rowH * 2);
    pdf.rect(x0, y, width, rowH, C.s2, { r: 3 });
    let x = x0;
    cols.forEach((c) => {
      const w = c.w * scale;
      pdf.text(c.label, c.right ? x + w - 6 : x + 6, y + 10.5, { size: 6.8, bold: true, color: C.t3, align: c.right ? "right" : "left", maxWidth: w - 10 });
      x += w;
    });
    y += rowH;
    rows.forEach((row, ri) => {
      ensure(rowH);
      if (ri % 2) pdf.rect(x0, y, width, rowH, "#101010");
      let xx = x0;
      cols.forEach((c, ci) => {
        const w = c.w * scale;
        pdf.text(row[ci] ?? "", c.right ? xx + w - 6 : xx + 6, y + 10.5, { size: 7.2, color: ci === 0 ? C.t1 : C.t2, align: c.right ? "right" : "left", maxWidth: w - 10 });
        xx += w;
      });
      y += rowH;
    });
  };

  if (acc && accShot) {
    newPage();
    const sub = `${fmtInt(acc.overall.rows)} rows with actuals (${acc.source}) · SKU-month WAPE ${fmtPct(acc.overall.WAPE)} · family-month ${fmtPct(acc.family_month_WAPE)} · ` +
      `total-month ${fmtPct(acc.total_month_WAPE)} · bias ${fmtPctChange(acc.overall.Bias)} · P10-P90 coverage ${fmtPct(acc.overall.Coverage_P10_P90, 0)}`;
    chartCard("Forecast vs actual", sub, accShot, 210);
    pdf.text("Accuracy by horizon, family and region", M, y + 4, { size: 11, bold: true });
    y += 14;
    const mrow = (x: ScoreMetrics, name: string) => [name, fmtInt(x.actual), fmtInt(x.forecast), fmtPct(x.WAPE), fmtPct(x.Naive_WAPE),
      fmtPctChange(x.Bias), fmtPct(x.Coverage_P10_P90, 0)];
    table([{ label: "Segment", w: 3 }, { label: "Actual", w: 1.3, right: true }, { label: "Forecast", w: 1.3, right: true },
      { label: "WAPE", w: 1, right: true }, { label: "Naive WAPE", w: 1.2, right: true }, { label: "Bias", w: 1, right: true },
      { label: "P10-P90 cov.", w: 1.2, right: true }],
    [...acc.by_horizon.map((x) => mrow(x, `Horizon ${x.Member}`)), ...acc.by_family.map((x) => mrow(x, x.Member ?? "")),
      ...acc.by_region.map((x) => mrow(x, x.Member ?? ""))], M, CW);
    y += GAP;
  }

  // ------------------------------------------------------------------ pipeline checks
  newPage();
  pdf.text("What the pipeline did to the data", M, y, { size: 14, bold: true });
  y += 8;
  y = pdf.paragraph("Cleaning, demand recovery and row checks: the same rules as the official run. Every fix is in the issue-log download.",
    M, y + 10, CW, { size: 8, color: C.t3 }) + 4;
  const col = (CW - 2 * GAP) / 3;
  const blocks: { title: string; lead: string; items: [string, string][] }[] = [
    { title: "CLEANING", lead: ch.cleaning
      ? `${fmtInt(ch.cleaning.rows_in)} rows in -> ${fmtInt(ch.cleaning.rows_clean)} clean · ${fmtInt(ch.cleaning.issues)} fixes`
      : "No history uploaded: the official cleaned history was used.",
    items: (ch.cleaning?.by_type ?? []).slice(0, 10).map((t) => [t.issue_type.replace(/_/g, " "), fmtInt(t.rows)]) },
    { title: "DEMAND RECOVERY", lead: `${fmtInt(ch.anomalies.flagged)} months flagged in the history`,
      items: Object.entries(ch.anomalies.by_category).map(([c, n]) => [c.replace(/_/g, " "), fmtInt(n)]) },
    { title: "ROWS TO FORECAST", lead: `${fmtInt(ch.request.accepted)} accepted · ${fmtInt(ch.request.rejected)} rejected`,
      items: [...Object.entries(ch.request.rejected_by_reason).map(([c, n]) => [c, fmtInt(n)] as [string, string]),
        ...Object.entries(k.methods).map(([m, n]) => [`method: ${m.split(":")[0].split("(")[0].trim()}`, fmtInt(n)] as [string, string])] },
  ];
  const leadLines = blocks.map((b) => pdf.wrap(b.lead, col - 20, 7.4));
  const leadH = Math.max(...leadLines.map((l) => l.length)) * 10;
  const bh = 30 + leadH + Math.max(1, ...blocks.map((b) => b.items.length)) * 15 + 12;
  ensure(bh);
  blocks.forEach((b, i) => {
    const x = M + i * (col + GAP);
    pdf.rect(x, y, col, bh, C.s1, { r: 8, stroke: C.border });
    pdf.text(b.title, x + 10, y + 18, { size: 7, bold: true, color: C.t3 });
    leadLines[i].forEach((l, j) => pdf.text(l, x + 10, y + 31 + j * 10, { size: 7.4, color: C.t2 }));
    b.items.forEach(([name, n], j) => {
      const yy = y + 30 + leadH + j * 15;
      pdf.rect(x + 8, yy, col - 16, 12.5, C.s2, { r: 2 });
      pdf.text(name, x + 13, yy + 9, { size: 6.8, color: C.t1, maxWidth: col - 60 });
      pdf.text(n, x + col - 13, yy + 9, { size: 6.8, bold: true, color: C.t1, align: "right" });
    });
  });
  y += bh + GAP + 6;

  // ------------------------------------------------------------------ top series
  pdf.text(`Top ${Math.min(25, r.series.length)} of ${fmtInt(r.series_total)} series by forecast units`, M, y + 4, { size: 11, bold: true });
  y += 14;
  const sc = [{ label: "SKU", w: 1.1 }, { label: "Region", w: 1.4 }, { label: "Family", w: 1.9 }, { label: "Forecast", w: 1, right: true },
    { label: "P10 - P90", w: 1.5, right: true }, { label: "Revenue", w: 1.1, right: true }];
  if (acc) sc.push({ label: "Actual", w: 1, right: true }, { label: "WAPE", w: 0.8, right: true });
  sc.push({ label: "Method", w: 1.6 });
  table(sc, r.series.slice(0, 25).map((s) => [s.SKU_ID, s.Region, s.Product_Family, fmtInt(s.Units), `${fmtInt(s.P10)} - ${fmtInt(s.P90)}`,
    fmtUsd(s.Revenue, 1), ...(acc ? [fmtInt(s.Actual), fmtPct(s.WAPE)] : []), s.Method]), M, CW);
  y += GAP;

  // ------------------------------------------------------------------ method note
  const note = "Method: the uploaded sales history goes through the same stage-1 cleaning, stockout and anomaly demand recovery " +
    "(only months up to the forecast origin, no look-ahead) and feature panel as the official run, then the frozen global " +
    "LightGBM model with the same lifecycle, launch, run-down and customer-shutdown rules and the stratified split-conformal " +
    "P10-P90 bands fitted on its 6-cutoff backtest. Nothing is retrained. Accuracy on months up to " +
    `${r.model.trained_through} is in-sample (the model was trained on them); the out-of-sample figure is the 6-cutoff backtest on Model Trust.`;
  ensure(70);
  y = pdf.paragraph(note, M, y + 8, CW, { size: 7.5, color: C.t3, lineHeight: 10.5 });

  // footers with the final page count
  const n = pdf.pageCount;
  for (let i = 0; i < n; i++) {
    pdf.setPage(i);
    pdf.line(M, pdf.H - 34, pdf.W - M, pdf.H - 34, C.border);
    pdf.text(`Celeris Control Tower · model ${r.model.name.replace(/_/g, " ")} · run ${jobId.slice(0, 8)}`, M, pdf.H - 20, { size: 7, color: C.t3 });
    pdf.text(`Page ${i + 1} / ${n}`, pdf.W - M, pdf.H - 20, { size: 7, color: C.t3, align: "right" });
  }
  return pdf.toBlob({ title: `Celeris forecast report ${r.inputs.cutoff}`, author: "Celeris Control Tower" });
}
