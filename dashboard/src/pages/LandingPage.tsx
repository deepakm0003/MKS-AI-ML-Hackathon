/**
 * Celeris — Cinematic Landing Page
 * Pure CSS animations, no extra deps.
 * Data fetched live from the frozen validated pipeline.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../api/client";

/* ─────────────────────────────────────────────────────────────
   Types
───────────────────────────────────────────────────────────── */
interface BacktestMetrics {
  overall: { WAPE: number; Bias: number; MAE: number };
  seasonal_naive_overall: { WAPE: number };
  family_month: { WAPE: number };
  total_month:  { WAPE: number };
  by_Product_Family: Record<string, { WAPE: number }>;
  by_horizon_bucket: Record<string, { WAPE: number }>;
}
interface Health  { validation: string; selected_model: string; frozen_at: string }
interface Briefing { kpis: { units_next12: number; revenue_next12: number; units_19m: number; units_19m_p10: number; units_19m_p90: number; exceptions: number; series: number; units_next12_vs_last12: number; revenue_next12_vs_last12: number } }

function useLandingData() {
  const [bt, setBt] = useState<BacktestMetrics | null>(null);
  const [h,  setH]  = useState<Health | null>(null);
  const [b,  setB]  = useState<Briefing | null>(null);
  useEffect(() => {
    Promise.all([
      request<BacktestMetrics>("/datasets/backtest_metrics"),
      request<Health>("/health"),
      request<Briefing>("/intelligence/briefing"),
    ]).then(([bt, h, b]) => { setBt(bt); setH(h); setB(b); }).catch(() => {});
  }, []);
  return { bt, h, b };
}

/* ─────────────────────────────────────────────────────────────
   useInView — fires once when el enters viewport
───────────────────────────────────────────────────────────── */
function useInView(threshold = 0.15) {
  const ref  = useRef<HTMLDivElement>(null);
  const [vis, setVis] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ob = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVis(true); ob.disconnect(); } }, { threshold });
    ob.observe(el);
    return () => ob.disconnect();
  }, [threshold]);
  return { ref, vis };
}

/* ─────────────────────────────────────────────────────────────
   useCounter — animates 0 → target when triggered
───────────────────────────────────────────────────────────── */
function useCounter(target: number, run: boolean, duration = 1600) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!run) return;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(ease * target));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [run, target, duration]);
  return val;
}

/* ─────────────────────────────────────────────────────────────
   Helpers
───────────────────────────────────────────────────────────── */
const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`;

/* ─────────────────────────────────────────────────────────────
   Static data
───────────────────────────────────────────────────────────── */
const PIPELINE = [
  { n: "01", title: "Data Cleaning",       color: "#3478f6", detail: "42k corrections · 30+ issue types · machine-readable DQ report" },
  { n: "02", title: "Anomaly Detection",   color: "#77aaff", detail: "Diff-in-diff stockout recovery · 21k flagged points · event impact" },
  { n: "03", title: "Feature Engineering", color: "#a5d6ff", detail: "87 features · ordering cycle · lag stability · EV shift · macro leads" },
  { n: "04", title: "Forecasting",         color: "#c7ff32", detail: "LightGBM C9c · 6-cutoff backtest · P10/P50/P90 · coherent hierarchy" },
];

const FEATURES = [
  { icon: "📊", title: "Executive Overview",    path: "/overview",    desc: "Revenue, demand and 19-month forecast on one continuous timeline." },
  { icon: "🔍", title: "Demand Explorer",        path: "/explorer",    desc: "Drill from family → SKU → region → customer with continuous history–forecast view." },
  { icon: "⚠️", title: "Risk & Exceptions",      path: "/risk",        desc: "Ranked exceptions, capacity risks and world-map regional overview." },
  { icon: "📦", title: "Planning & Procurement", path: "/planning",    desc: "P90 procurement plan, ABC-XYZ segmentation, lead-time buffers." },
  { icon: "🧪", title: "Scenario Lab",           path: "/scenarios",   desc: "What-if macro shocks — PMI, auto production, EV — answered instantly." },
  { icon: "🗓️", title: "Calendar Forecast",      path: "/calendar",    desc: "Pick any date range and explore demand, revenue and procurement needs." },
  { icon: "🛡️", title: "Model Trust",            path: "/trust",       desc: "Backtest audit: WAPE by horizon, segment and experiment registry." },
  { icon: "🔬", title: "Anomaly Monitor",        path: "/anomalies",   desc: "Every flagged data point with recovery methodology explained." },
  { icon: "📡", title: "Data Health",            path: "/data-health", desc: "Every raw-data correction logged — original → fixed — with rule applied." },
  { icon: "🚨", title: "Exception List",         path: "/exceptions",  desc: "All 351 actionable exceptions filterable by priority, owner and impact." },
];

const _FEATURES = FEATURES; void _FEATURES; // kept for future use

const MODEL_FACTS = [
  { label: "Algorithm",      value: "Global LightGBM · Tweedie loss" },
  { label: "Features",       value: "87 engineered features" },
  { label: "Backtest",       value: "6 rolling-origin cutoffs" },
  { label: "Horizon",        value: "19 months (Nov 2026 – May 2028)" },
  { label: "SKU-regions",    value: "3,068 active series" },
  { label: "Experiments",    value: "19 challengers evaluated" },
  { label: "Champion",       value: "C9c · keep pull-forward months" },
  { label: "Validation",     value: "All contract checks PASS" },
];

/* ─────────────────────────────────────────────────────────────
   Shared styles
───────────────────────────────────────────────────────────── */
const WRAP: React.CSSProperties = { maxWidth: 1200, margin: "0 auto", padding: "0 48px" };
const SECTION: React.CSSProperties = { ...WRAP, paddingTop: 96, paddingBottom: 96 };

/* ─────────────────────────────────────────────────────────────
   Sub-components
───────────────────────────────────────────────────────────── */

/** Fade + slide-up on scroll */
function Reveal({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  const { ref, vis } = useInView();
  return (
    <div ref={ref} style={{
      opacity:   vis ? 1 : 0,
      transform: vis ? "translateY(0)" : "translateY(28px)",
      transition: `opacity 0.7s ease ${delay}s, transform 0.7s ease ${delay}s`,
      ...style,
    }}>
      {children}
    </div>
  );
}

/** Animated counter KPI card */
function KpiCard({ label, rawValue, display, sub, accent, blue }: {
  label: string; rawValue: number; display: (n: number) => string; sub: string; accent?: boolean; blue?: boolean;
}) {
  const { ref, vis } = useInView();
  const val = useCounter(rawValue, vis);
  const col = accent ? "#c7ff32" : blue ? "#58a6ff" : "#ffffff";
  const border = accent ? "rgba(199,255,50,0.3)" : blue ? "rgba(88,166,255,0.2)" : "#1f1f1f";
  const bg     = accent ? "rgba(199,255,50,0.04)" : blue ? "rgba(88,166,255,0.03)" : "#0f0f0f";
  return (
    <div ref={ref} style={{ padding: "28px 24px", background: bg, border: `1px solid ${border}`, borderRadius: 12, transition: "border-color 0.2s, transform 0.2s" }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)"; (e.currentTarget as HTMLElement).style.borderColor = accent ? "rgba(199,255,50,0.6)" : blue ? "rgba(88,166,255,0.4)" : "#2a2a2a"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.transform = ""; (e.currentTarget as HTMLElement).style.borderColor = border; }}
    >
      <div style={{ fontSize: 11, fontWeight: 600, color: "#555", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 12 }}>{label}</div>
      <div style={{ fontSize: 36, fontWeight: 700, color: col, lineHeight: 1, fontVariantNumeric: "tabular-nums", marginBottom: 8 }}>{display(val)}</div>
      <div style={{ fontSize: 12, color: "#555" }}>{sub}</div>
    </div>
  );
}

/** Animated accuracy bar */
function AccBar({ label, wape, baseline, delay = 0, vis }: { label: string; wape: number; baseline: number; delay?: number; vis: boolean }) {
  const pct  = wape * 100;
  const bPct = baseline * 100;
  const imp  = ((baseline - wape) / baseline * 100).toFixed(0);
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: "#a0a0a0" }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#c7ff32" }}>{pct.toFixed(1)}%</span>
      </div>
      <div style={{ position: "relative", height: 5, background: "#1a1a1a", borderRadius: 3 }}>
        {/* baseline ghost */}
        <div style={{ position: "absolute", inset: 0, width: `${bPct}%`, background: "#252525", borderRadius: 3 }} />
        {/* model bar */}
        <div style={{
          position: "absolute", inset: 0, height: "100%", borderRadius: 3,
          background: "linear-gradient(90deg,#c7ff32,#a3d416)",
          width: vis ? `${pct}%` : "0%",
          transition: `width 1s cubic-bezier(0.4,0,0.2,1) ${delay}s`,
        }} />
      </div>
      <div style={{ fontSize: 10, color: "#555", marginTop: 4 }}>{imp}% better than seasonal naive · baseline {bPct.toFixed(1)}%</div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Main component
───────────────────────────────────────────────────────────── */
export function LandingPage() {
  const navigate = useNavigate();
  const { bt, h, b } = useLandingData();

  /* ── derived metrics (fall back to real known values while loading) */
  const wape       = bt?.overall.WAPE     ?? 0.2837;
  const baseline   = bt?.seasonal_naive_overall?.WAPE ?? 0.3782;
  const fmWAPE     = bt?.family_month.WAPE ?? 0.0733;
  const tmWAPE     = bt?.total_month.WAPE  ?? 0.0515;
  const mae        = bt?.overall.MAE       ?? 13.43;
  const bias       = bt?.overall.Bias      ?? -0.0284;
  const imp        = ((baseline - wape) / baseline * 100);
  const units19    = b?.kpis.units_19m             ?? 2818668;
  const revenue12  = b?.kpis.revenue_next12        ?? 1609864090;
  const growthU    = b?.kpis.units_next12_vs_last12 ?? 0.061;

  const families = bt?.by_Product_Family
    ? Object.entries(bt.by_Product_Family).sort((a, x) => a[1].WAPE - x[1].WAPE)
    : [];

  const { ref: accRef, vis: accVis } = useInView();

  /* ── hero entrance */
  const [heroIn, setHeroIn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setHeroIn(true), 100); return () => clearTimeout(t); }, []);

  return (
    <div style={{ minHeight: "100vh", background: "#030403", color: "#ffffff", fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif", overflowX: "hidden" }}>

      {/* ═══════════════════════════════════════════════════
          CSS KEYFRAMES injected once
      ══════════════════════════════════════════════════════ */}
      <style>{`
        @keyframes beam1 {
          0%   { transform: translateX(-8%) translateY(-4%) rotate(-35deg); opacity: 0.18; }
          50%  { transform: translateX(4%)  translateY(2%)  rotate(-33deg); opacity: 0.28; }
          100% { transform: translateX(-8%) translateY(-4%) rotate(-35deg); opacity: 0.18; }
        }
        @keyframes beam2 {
          0%   { transform: translateX(5%)  translateY(6%)  rotate(-28deg); opacity: 0.12; }
          50%  { transform: translateX(-3%) translateY(-2%) rotate(-30deg); opacity: 0.22; }
          100% { transform: translateX(5%)  translateY(6%)  rotate(-28deg); opacity: 0.12; }
        }
        @keyframes beam3 {
          0%   { transform: translateX(0%)  translateY(0%)  rotate(-42deg); opacity: 0.08; }
          60%  { transform: translateX(6%)  translateY(-3%) rotate(-40deg); opacity: 0.16; }
          100% { transform: translateX(0%)  translateY(0%)  rotate(-42deg); opacity: 0.08; }
        }
        @keyframes float1 {
          0%,100% { transform: translateY(0px); }
          50%     { transform: translateY(-8px); }
        }
        @keyframes float2 {
          0%,100% { transform: translateY(0px); }
          50%     { transform: translateY(-12px); }
        }
        @keyframes glowPulse {
          0%,100% { opacity: 0.5; }
          50%     { opacity: 1; }
        }
        @keyframes drawLine {
          from { stroke-dashoffset: 1200; }
          to   { stroke-dashoffset: 0; }
        }
        @keyframes fadeUp {
          from { opacity:0; transform:translateY(16px); }
          to   { opacity:1; transform:translateY(0); }
        }
        @keyframes spinSlow {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes shimmer {
          0%   { background-position: -200% 0; }
          100% { background-position:  200% 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
        }
      `}</style>

      {/* ═══════════════════════════════════════════════════
          BACKGROUND LAYERS (fixed, behind everything)
      ══════════════════════════════════════════════════════ */}
      {/* Fine grid */}
      <div style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
        backgroundImage: `linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)`,
        backgroundSize: "72px 72px",
      }} />

      {/* Beam 1 — large diagonal green, upper-left */}
      <div style={{ position: "fixed", zIndex: 0, pointerEvents: "none",
        top: "-20vh", left: "-15vw", width: "55vw", height: "120vh",
        background: "linear-gradient(135deg, transparent 0%, rgba(199,255,50,0.07) 30%, rgba(199,255,50,0.18) 50%, rgba(199,255,50,0.07) 70%, transparent 100%)",
        filter: "blur(80px)",
        animation: "beam1 14s ease-in-out infinite",
        transformOrigin: "center center",
      }} />

      {/* Beam 2 — mid-page, right side */}
      <div style={{ position: "fixed", zIndex: 0, pointerEvents: "none",
        top: "30vh", right: "-20vw", width: "50vw", height: "100vh",
        background: "linear-gradient(135deg, transparent 0%, rgba(199,255,50,0.04) 35%, rgba(199,255,50,0.12) 55%, rgba(199,255,50,0.04) 75%, transparent 100%)",
        filter: "blur(100px)",
        animation: "beam2 18s ease-in-out infinite",
      }} />

      {/* Beam 3 — faint wide sweep, bottom */}
      <div style={{ position: "fixed", zIndex: 0, pointerEvents: "none",
        bottom: "-10vh", left: "10vw", width: "80vw", height: "80vh",
        background: "linear-gradient(135deg, transparent 0%, rgba(199,255,50,0.03) 40%, rgba(199,255,50,0.09) 55%, rgba(199,255,50,0.03) 70%, transparent 100%)",
        filter: "blur(120px)",
        animation: "beam3 22s ease-in-out infinite",
      }} />

      {/* Radial hero glow */}
      <div style={{ position: "fixed", zIndex: 0, pointerEvents: "none",
        top: "0", left: "0", width: "100vw", height: "70vh",
        background: "radial-gradient(ellipse 60% 60% at 35% 40%, rgba(199,255,50,0.07) 0%, transparent 70%)",
        animation: "glowPulse 8s ease-in-out infinite",
      }} />

      {/* ═══════════════════════════════════════════════════
          NAVBAR
      ══════════════════════════════════════════════════════ */}
      <nav style={{ position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 48px", height: 64,
        background: "rgba(3,4,3,0.85)", backdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <svg viewBox="0 0 32 32" width="28" height="28">
            <rect width="32" height="32" rx="7" fill="#111" />
            <path d="M7 22l5-7 4 5 4-6 5-5" stroke="#c7ff32" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span style={{ fontWeight: 800, letterSpacing: "0.18em", fontSize: 13 }}>CELERIS</span>
          <span style={{ fontSize: 11, color: "#555", paddingLeft: 2 }}>AI Demand Control Tower</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {h && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 28, padding: "0 12px",
              background: "rgba(199,255,50,0.07)", border: "1px solid rgba(199,255,50,0.25)",
              borderRadius: 999, fontSize: 11, fontWeight: 600, color: "#c7ff32" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#c7ff32", animation: "glowPulse 2s infinite" }} />
              Validation {h.validation}
            </span>
          )}
          <button onClick={() => navigate("/overview")}
            style={{ height: 36, padding: "0 20px", background: "#c7ff32", color: "#030403",
              border: "none", borderRadius: 8, fontWeight: 700, fontSize: 13, cursor: "pointer",
              transition: "transform 0.15s, box-shadow 0.15s" }}
            onMouseEnter={(e) => { const b = e.currentTarget; b.style.transform = "translateY(-1px)"; b.style.boxShadow = "0 0 20px rgba(199,255,50,0.35)"; }}
            onMouseLeave={(e) => { const b = e.currentTarget; b.style.transform = ""; b.style.boxShadow = ""; }}
          >
            Enter Dashboard →
          </button>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════════════
          HERO
      ══════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", zIndex: 1, minHeight: "100vh", display: "flex", alignItems: "center", paddingTop: 64 }}>
        <div style={{ ...WRAP, paddingTop: 80, paddingBottom: 80, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 64, alignItems: "center" }}>

          {/* Left — text */}
          <div>
            {/* Badge */}
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "5px 14px", marginBottom: 32,
              background: "rgba(199,255,50,0.06)", border: "1px solid rgba(199,255,50,0.18)",
              borderRadius: 999, fontSize: 11, fontWeight: 600, color: "#c7ff32",
              letterSpacing: "0.07em", textTransform: "uppercase",
              opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateY(12px)",
              transition: "opacity 0.8s ease 0.1s, transform 0.8s ease 0.1s",
            }}>
              ✳ MKS AI/ML Hackathon · Phase 2
            </div>

            {/* Headline */}
            <h1 style={{
              fontSize: "clamp(44px, 5.5vw, 80px)", fontWeight: 800,
              letterSpacing: "-0.025em", lineHeight: 1.08, marginBottom: 24,
              opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateY(20px)",
              transition: "opacity 0.8s ease 0.25s, transform 0.8s ease 0.25s",
            }}>
              Demand forecasting<br />
              that <span style={{ color: "#c7ff32" }}>moves business</span>
            </h1>

            <p style={{
              fontSize: 17, color: "#888", lineHeight: 1.7, maxWidth: 480, marginBottom: 40,
              opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateY(16px)",
              transition: "opacity 0.8s ease 0.4s, transform 0.8s ease 0.4s",
            }}>
              Anticipate demand. Understand uncertainty. Turn forecasting intelligence into confident planning decisions.
            </p>

            <div style={{
              display: "flex", gap: 12,
              opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateY(12px)",
              transition: "opacity 0.8s ease 0.55s, transform 0.8s ease 0.55s",
            }}>
              <button onClick={() => navigate("/overview")}
                style={{ height: 48, padding: "0 28px", background: "#c7ff32", color: "#030403",
                  border: "none", borderRadius: 10, fontWeight: 700, fontSize: 15, cursor: "pointer",
                  transition: "transform 0.15s, box-shadow 0.15s" }}
                onMouseEnter={(e) => { const b = e.currentTarget; b.style.transform = "translateY(-2px)"; b.style.boxShadow = "0 0 28px rgba(199,255,50,0.4)"; }}
                onMouseLeave={(e) => { const b = e.currentTarget; b.style.transform = ""; b.style.boxShadow = ""; }}>
                Explore Control Tower →
              </button>
              <button onClick={() => navigate("/trust")}
                style={{ height: 48, padding: "0 28px", background: "transparent", color: "#ccc",
                  border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10, fontWeight: 500, fontSize: 15, cursor: "pointer",
                  transition: "border-color 0.15s, color 0.15s" }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(199,255,50,0.4)"; e.currentTarget.style.color = "#c7ff32"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)"; e.currentTarget.style.color = "#ccc"; }}>
                Forecast Accuracy
              </button>
            </div>
          </div>

          {/* Right — forecast preview card */}
          <div style={{
            opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateX(24px)",
            transition: "opacity 1s ease 0.5s, transform 1s ease 0.5s",
          }}>
            <HeroChart units19={units19} growth={growthU} wape={wape} />
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════
          KPI SECTION
      ══════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", zIndex: 1, ...SECTION }}>
        <Reveal>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
            <KpiCard label="19-month forecast"  rawValue={Math.round(units19 / 1e3)} display={(n) => `${n}K`}      sub="units (Nov 2026 – May 2028)" accent />
            <KpiCard label="Forecast revenue"   rawValue={Math.round(revenue12 / 1e6)} display={(n) => `$${n}M`}  sub={`+${fmtPct(growthU)} vs last 12m`} />
            <KpiCard label="SKU-region series"  rawValue={3068} display={(n) => n.toLocaleString()} sub="active demand series" blue />
            <KpiCard label="Exceptions flagged" rawValue={351}  display={(n) => String(n)} sub="62 critical · 201 high" />
          </div>
        </Reveal>
      </section>

      {/* ═══════════════════════════════════════════════════
          MODEL ACCURACY SECTION
      ══════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", zIndex: 1, ...SECTION, paddingTop: 0 }}>
        <Reveal>
          <p style={{ fontSize: 11, fontWeight: 700, color: "#c7ff32", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>Model Performance</p>
          <h2 style={{ fontSize: "clamp(28px, 3vw, 42px)", fontWeight: 700, letterSpacing: "-0.015em", marginBottom: 12 }}>
            Forecast accuracy you can measure.
          </h2>
          <p style={{ fontSize: 14, color: "#555", maxWidth: 520 }}>
            Validated across 6 rolling-origin cutoffs, 19-month horizon and 224k scored SKU-region-months.
          </p>
        </Reveal>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 40 }}>

          {/* Big WAPE number */}
          <Reveal delay={0.1}>
            <div style={{ padding: "36px 36px", background: "rgba(199,255,50,0.03)", border: "1px solid rgba(199,255,50,0.15)", borderRadius: 14, height: "100%" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#555", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 20 }}>Overall WAPE · 6-cutoff average</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 10 }}>
                <span style={{ fontSize: 72, fontWeight: 800, color: "#c7ff32", lineHeight: 1 }}>{(wape * 100).toFixed(1)}%</span>
                <div>
                  <div style={{ fontSize: 13, color: "#666" }}>WAPE</div>
                  <div style={{ fontSize: 12, color: "#c7ff32", marginTop: 2 }}>−{imp.toFixed(0)}% vs baseline</div>
                </div>
              </div>
              <p style={{ fontSize: 13, color: "#555", marginBottom: 28 }}>
                {imp.toFixed(0)}% improvement over seasonal naive ({(baseline * 100).toFixed(1)}%)
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[
                  { k: "MAE",           v: mae.toFixed(1) },
                  { k: "Bias",          v: fmtPct(bias) },
                  { k: "Family-month",  v: fmtPct(fmWAPE) },
                  { k: "Company-month", v: fmtPct(tmWAPE) },
                ].map(({ k, v }) => (
                  <div key={k} style={{ padding: "12px 14px", background: "#0d0d0d", border: "1px solid #161616", borderRadius: 8 }}>
                    <div style={{ fontSize: 10, color: "#555", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{k}</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: "#fff" }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          {/* Family bars */}
          <Reveal delay={0.2}>
            <div ref={accRef} style={{ padding: "36px 36px", background: "#0a0a0a", border: "1px solid #161616", borderRadius: 14, height: "100%" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#555", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 24 }}>WAPE by product family</div>
              {(families.length > 0 ? families : [
                ["Electrical Assemblies",    { WAPE: 0.263 }],
                ["Powertrain Components",    { WAPE: 0.276 }],
                ["Chassis & Structural",     { WAPE: 0.276 }],
                ["Thermal Management",       { WAPE: 0.279 }],
                ["Brake & Safety Systems",   { WAPE: 0.277 }],
                ["Precision Machined Parts", { WAPE: 0.289 }],
                ["Hydraulic Systems",        { WAPE: 0.295 }],
              ] as [string, { WAPE: number }][]).map(([fam, m], i) => (
                <AccBar key={fam} label={fam} wape={m.WAPE} baseline={baseline} delay={i * 0.08} vis={accVis} />
              ))}
            </div>
          </Reveal>
        </div>

        {/* Horizon cards */}
        <Reveal delay={0.15} style={{ marginTop: 20 }}>
          <div style={{ padding: "32px 36px", background: "#0a0a0a", border: "1px solid #161616", borderRadius: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#555", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 24 }}>WAPE by forecast horizon</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
              {[
                { label: "Near-term",  range: "1–3 months",   wape: bt?.by_horizon_bucket?.["1-3m"]?.WAPE  ?? 0.278, blue: false },
                { label: "Mid-range",  range: "4–6 months",   wape: bt?.by_horizon_bucket?.["4-6m"]?.WAPE  ?? 0.274, blue: false },
                { label: "Planning",   range: "7–12 months",  wape: bt?.by_horizon_bucket?.["7-12m"]?.WAPE ?? 0.281, blue: false },
                { label: "Strategic",  range: "13–19 months", wape: bt?.by_horizon_bucket?.["13-19m"]?.WAPE ?? 0.293, blue: true  },
              ].map(({ label, range, wape: w, blue }, i) => (
                <div key={label} style={{ padding: "20px", background: "#0d0d0d", border: `1px solid ${blue ? "rgba(88,166,255,0.15)" : "#161616"}`, borderRadius: 10 }}>
                  <div style={{ fontSize: 10, color: "#555", marginBottom: 10 }}>{label}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: blue ? "#58a6ff" : "#c7ff32", marginBottom: 6 }}>{(w * 100).toFixed(1)}%</div>
                  <div style={{ fontSize: 11, color: "#555" }}>{range}</div>
                  <div style={{ marginTop: 12, height: 3, background: "#1a1a1a", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: accVis ? `${w * 100}%` : "0%", background: blue ? "#58a6ff" : "#c7ff32", borderRadius: 2, transition: `width 1s ease ${i * 0.12}s` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* ═══════════════════════════════════════════════════
          PIPELINE SECTION
      ══════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", zIndex: 1, ...SECTION }}>
        <Reveal>
          <p style={{ fontSize: 11, fontWeight: 700, color: "#c7ff32", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>Pipeline</p>
          <h2 style={{ fontSize: "clamp(28px, 3vw, 42px)", fontWeight: 700, letterSpacing: "-0.015em" }}>
            From raw data to decisions.
          </h2>
        </Reveal>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0, marginTop: 48, position: "relative" }}>
          {/* Connecting line */}
          <div style={{ position: "absolute", top: 28, left: "12.5%", right: "12.5%", height: 1, background: "linear-gradient(90deg,#3478f6,#77aaff,#a5d6ff,#c7ff32)", opacity: 0.4 }} />
          {PIPELINE.map(({ n, title, color, detail }, i) => (
            <Reveal key={n} delay={i * 0.12}>
              <div style={{ padding: "28px 24px", background: "#0a0a0a",
                borderTop: `2px solid ${color}`,
                borderLeft:   i === 0 ? "1px solid #161616" : "none",
                borderRight:  "1px solid #161616",
                borderBottom: "1px solid #161616",
                borderRadius: i === 0 ? "12px 0 0 12px" : i === 3 ? "0 12px 12px 0" : 0,
                transition: "background 0.2s, transform 0.2s", cursor: "default" }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#0f0f0f"; (e.currentTarget as HTMLElement).style.transform = "translateY(-3px)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#0a0a0a"; (e.currentTarget as HTMLElement).style.transform = ""; }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                  <div style={{ width: 28, height: 28, borderRadius: "50%", border: `1.5px solid ${color}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color, flexShrink: 0 }}>{n}</div>
                </div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#fff", marginBottom: 10 }}>{title}</div>
                <div style={{ fontSize: 11, color: "#555", lineHeight: 1.65 }}>{detail}</div>
              </div>
            </Reveal>
          ))}
        </div>

        {/* Model facts */}
        <Reveal delay={0.1} style={{ marginTop: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {MODEL_FACTS.map(({ label, value }) => (
              <div key={label} style={{ padding: "12px 16px", background: "#0a0a0a", border: "1px solid #161616", borderRadius: 8, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "#555" }}>{label}</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#a0a0a0", textAlign: "right" }}>{value}</span>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* ═══════════════════════════════════════════════════
          FINAL CTA
      ══════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", zIndex: 1, ...WRAP, paddingTop: 32, paddingBottom: 80 }}>
        <Reveal>
          <div style={{ position: "relative", padding: "72px 60px", textAlign: "center",
            background: "radial-gradient(ellipse 70% 70% at 50% 60%, rgba(199,255,50,0.06) 0%, transparent 70%), #0a0a0a",
            border: "1px solid rgba(199,255,50,0.12)", borderRadius: 20, overflow: "hidden" }}>
            {/* Subtle corner glow */}
            <div style={{ position: "absolute", top: -60, left: "50%", transform: "translateX(-50%)", width: 400, height: 200,
              background: "radial-gradient(ellipse, rgba(199,255,50,0.1) 0%, transparent 70%)", pointerEvents: "none" }} />
            <p style={{ fontSize: 11, fontWeight: 700, color: "#c7ff32", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 20 }}>Ready</p>
            <h2 style={{ fontSize: "clamp(28px, 3.5vw, 48px)", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 16 }}>
              Ready to understand<br />what comes next?
            </h2>
            <p style={{ fontSize: 15, color: "#666", maxWidth: 480, margin: "0 auto 40px" }}>
              Explore the forecast. Discover the signals. Make your next decision with confidence.
            </p>
            <button onClick={() => navigate("/overview")}
              style={{ height: 52, padding: "0 40px", background: "#c7ff32", color: "#030403",
                border: "none", borderRadius: 12, fontWeight: 800, fontSize: 16, cursor: "pointer",
                transition: "transform 0.15s, box-shadow 0.15s" }}
              onMouseEnter={(e) => { const b = e.currentTarget; b.style.transform = "translateY(-2px)"; b.style.boxShadow = "0 0 36px rgba(199,255,50,0.45)"; }}
              onMouseLeave={(e) => { const b = e.currentTarget; b.style.transform = ""; b.style.boxShadow = ""; }}>
              Enter Celeris Control Tower →
            </button>
          </div>
        </Reveal>
      </section>

      {/* ═══════════════════════════════════════════════════
          FOOTER
      ══════════════════════════════════════════════════════ */}
      <footer style={{ position: "relative", zIndex: 1, borderTop: "1px solid rgba(255,255,255,0.05)", padding: "24px 48px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <svg viewBox="0 0 32 32" width="20" height="20">
            <rect width="32" height="32" rx="6" fill="#111" />
            <path d="M7 22l5-7 4 5 4-6 5-5" stroke="#c7ff32" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: "#555" }}>CELERIS</span>
          <span style={{ fontSize: 11, color: "#333" }}>Demand Control Tower · MKS AI/ML Hackathon</span>
        </div>
        <div style={{ fontSize: 11, color: "#333" }}>
          {h ? `Model ${h.selected_model} · Frozen ${h.frozen_at}` : "Phase 2 · 19-month horizon"}
        </div>
      </footer>

    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   HeroChart — premium architecture animation
   Isometric-style grid + animated forecast line + glowing bars
───────────────────────────────────────────────────────────── */
function HeroChart({ units19, growth, wape }: { units19: number; growth: number; wape: number }) {
  const [phase, setPhase] = useState(0); // 0=hidden 1=grid 2=bars 3=line 4=done
  const [tick,  setTick]  = useState(0);

  useEffect(() => {
    const steps = [600, 400, 500, 600];
    let t = 0;
    steps.forEach((delay, i) => {
      t += delay;
      const id = setTimeout(() => setPhase(i + 1), t);
      return id;
    });
  }, []);

  // slow tick for the scanning line
  useEffect(() => {
    if (phase < 3) return;
    const id = setInterval(() => setTick((t) => (t + 1) % 100), 60);
    return () => clearInterval(id);
  }, [phase]);

  const W = 500, H = 300;

  // 31 months: 12 history + 19 forecast — relative demand shape
  const DATA = [
    // history (gray) — real shape normalised
    72, 78, 68, 84, 88, 80, 74, 91, 86, 79, 95, 87,
    // forecast (lime) — upward trend with realistic variation
    94, 101, 97, 107, 114, 110, 117, 124, 119, 115, 121, 127, 129, 134, 128, 131, 137, 141, 138,
  ];
  const HIST = 12;
  const mn = Math.min(...DATA), mx = Math.max(...DATA);
  const norm = (v: number) => (v - mn) / (mx - mn);

  const BAR_W = 12, GAP = 4;
  const totalW = DATA.length * (BAR_W + GAP);
  const offsetX = (W - totalW) / 2;
  const CHART_H = 180, CHART_Y = 60;

  // grid lines
  const GRID_LINES = [0, 0.25, 0.5, 0.75, 1];

  // line path for history
  const hPts = DATA.slice(0, HIST).map((v, i) => ({
    x: offsetX + i * (BAR_W + GAP) + BAR_W / 2,
    y: CHART_Y + CHART_H - norm(v) * CHART_H,
  }));
  // line path for forecast
  const fPts = DATA.slice(HIST - 1).map((v, i) => ({
    x: offsetX + (HIST - 1 + i) * (BAR_W + GAP) + BAR_W / 2,
    y: CHART_Y + CHART_H - norm(v) * CHART_H,
  }));

  const toPath = (pts: { x: number; y: number }[]) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  // scan line x position
  const scanX = offsetX + (tick / 100) * totalW;

  // forecast endpoint
  const fcEnd = fPts[fPts.length - 1];

  // total path lengths (approximate)
  const hLen = 450, fLen = 700;

  return (
    <div style={{ position: "relative", animation: "float1 8s ease-in-out infinite" }}>

      {/* ── glass card ─────────────────────────────────────── */}
      <div style={{
        background: "rgba(6,8,6,0.82)",
        border: "1px solid rgba(199,255,50,0.18)",
        borderRadius: 18,
        padding: "0 0 20px",
        backdropFilter: "blur(20px)",
        boxShadow: "0 0 80px rgba(199,255,50,0.07), 0 24px 80px rgba(0,0,0,0.7)",
        overflow: "hidden",
      }}>

        {/* top label bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 20px 12px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
          <div>
            <div style={{ fontSize: 9, color: "#555", textTransform: "uppercase", letterSpacing: "0.1em" }}>Demand Forecast · 19 Months</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#c7ff32", marginTop: 3 }}>Nov 2026 – May 2028</div>
          </div>
          <div style={{ display: "flex", gap: 14 }}>
            {[{ col: "#666", label: "Historical" }, { col: "#c7ff32", label: "Forecast" }].map(({ col, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#777" }}>
                <span style={{ width: 16, height: 2, background: col, borderRadius: 1, display: "inline-block" }} />
                {label}
              </div>
            ))}
          </div>
        </div>

        {/* SVG chart */}
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
          <defs>
            <style>{`
              .h-line { stroke-dasharray:${hLen}; stroke-dashoffset:${phase>=2?0:hLen}; transition:stroke-dashoffset 1.1s cubic-bezier(.4,0,.2,1) .1s }
              .f-line { stroke-dasharray:${fLen}; stroke-dashoffset:${phase>=3?0:fLen}; transition:stroke-dashoffset 1.4s cubic-bezier(.4,0,.2,1) .05s }
              .fc-dot { opacity:${phase>=4?1:0}; transition:opacity .5s ease .2s }
              .bar    { transition:height .6s cubic-bezier(.4,0,.2,1), y .6s cubic-bezier(.4,0,.2,1) }
            `}</style>
            <linearGradient id="barGradH" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(255,255,255,0.18)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.03)" />
            </linearGradient>
            <linearGradient id="barGradF" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(199,255,50,0.7)" />
              <stop offset="100%" stopColor="rgba(199,255,50,0.08)" />
            </linearGradient>
            <radialGradient id="dotGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(199,255,50,0.6)" />
              <stop offset="100%" stopColor="transparent" />
            </radialGradient>
            <clipPath id="chartClip">
              <rect x={offsetX} y={CHART_Y - 4} width={totalW} height={CHART_H + 8} />
            </clipPath>
          </defs>

          {/* horizontal grid lines */}
          {GRID_LINES.map((f) => (
            <line key={f}
              x1={offsetX} x2={offsetX + totalW}
              y1={CHART_Y + CHART_H - f * CHART_H} y2={CHART_Y + CHART_H - f * CHART_H}
              stroke={f === 0 ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.04)"}
              strokeWidth={f === 0 ? 1 : 0.5}
            />
          ))}

          {/* forecast window shading */}
          {phase >= 1 && (
            <rect
              x={offsetX + (HIST - 0.5) * (BAR_W + GAP)}
              y={CHART_Y}
              width={totalW - (HIST - 0.5) * (BAR_W + GAP)}
              height={CHART_H}
              fill="rgba(199,255,50,0.025)"
            />
          )}

          {/* vertical divider */}
          {phase >= 1 && (
            <line
              x1={offsetX + (HIST - 0.5) * (BAR_W + GAP)}
              y1={CHART_Y - 8}
              x2={offsetX + (HIST - 0.5) * (BAR_W + GAP)}
              y2={CHART_Y + CHART_H}
              stroke="rgba(199,255,50,0.3)"
              strokeWidth={1}
              strokeDasharray="3,3"
            />
          )}

          {/* bars */}
          <g clipPath="url(#chartClip)">
            {phase >= 1 && DATA.map((v, i) => {
              const isFc  = i >= HIST;
              const bH    = norm(v) * CHART_H;
              const bY    = CHART_Y + CHART_H - bH;
              const bX    = offsetX + i * (BAR_W + GAP);
              return (
                <rect key={i}
                  className="bar"
                  x={bX} y={bY} width={BAR_W}
                  height={phase >= 2 ? bH : 0}
                  rx={2}
                  fill={isFc ? "url(#barGradF)" : "url(#barGradH)"}
                  style={{ transitionDelay: `${i * 0.025}s` }}
                />
              );
            })}
          </g>

          {/* scanning vertical line (slow left-to-right sweep) */}
          {phase >= 3 && (
            <line
              x1={scanX} y1={CHART_Y} x2={scanX} y2={CHART_Y + CHART_H}
              stroke="rgba(199,255,50,0.15)" strokeWidth={1}
            />
          )}

          {/* history line */}
          {phase >= 2 && (
            <path d={toPath(hPts)} fill="none" stroke="#888" strokeWidth={1.5}
              strokeLinecap="round" className="h-line" />
          )}

          {/* forecast line */}
          {phase >= 3 && (
            <path d={toPath(fPts)} fill="none" stroke="#c7ff32" strokeWidth={2}
              strokeLinecap="round" className="f-line" />
          )}

          {/* glowing endpoint dot */}
          <g className="fc-dot">
            <circle cx={fcEnd.x} cy={fcEnd.y} r={18} fill="url(#dotGlow)" />
            <circle cx={fcEnd.x} cy={fcEnd.y} r={6}  fill="rgba(199,255,50,0.15)" />
            <circle cx={fcEnd.x} cy={fcEnd.y} r={3}  fill="#c7ff32" />
            <circle cx={fcEnd.x} cy={fcEnd.y} r={3}
              fill="none" stroke="#c7ff32" strokeWidth={1}
              style={{ animation: "glowPulse 2s ease-in-out infinite" }}
            />
          </g>

          {/* month axis ticks */}
          {["N'26","D","J'27","F","M","A","M","J","J","A","S","O","N","D","J'28","F","M","A","M'28"].map((label, i) => {
            if (i % 3 !== 0) return null;
            const x = offsetX + (i + 12) * (BAR_W + GAP) + BAR_W / 2;
            if (x > offsetX + totalW) return null;
            return (
              <text key={i} x={x} y={H - 6} textAnchor="middle" fill="#444" fontSize={8}>{label}</text>
            );
          })}
          {/* history axis ticks */}
          {["2026-01","02","03","04","05","06","07","08","09","10","11","12"].map((_, i) => {
            if (i % 4 !== 0) return null;
            const x = offsetX + i * (BAR_W + GAP) + BAR_W / 2;
            const labels = ["Jan","May","Sep","Jan"];
            return (
              <text key={`h${i}`} x={x} y={H - 6} textAnchor="middle" fill="#333" fontSize={8}>
                {labels[Math.floor(i / 4)]}
              </text>
            );
          })}
        </svg>

        {/* bottom stats */}
        <div style={{ display: "flex", gap: 24, padding: "0 20px", borderTop: "1px solid rgba(255,255,255,0.04)", paddingTop: 14 }}>
          {[
            { k: "19M TOTAL",  v: `${(units19 / 1e6).toFixed(2)}M u` },
            { k: "GROWTH",     v: `+${(growth * 100).toFixed(1)}%` },
            { k: "WAPE",       v: `${(wape * 100).toFixed(1)}%` },
          ].map(({ k, v }) => (
            <div key={k}>
              <div style={{ fontSize: 9, color: "#555", letterSpacing: "0.1em", textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#c7ff32", marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
