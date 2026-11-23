import { useEffect, useRef } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { echarts, THEME_NAME } from "./echarts";

/**
 * Thin React wrapper: one chart instance per mount, options replaced (not merged) on change,
 * resized with its container, disposed on unmount. `label` is the accessible description.
 * `onEvents` maps ECharts event names to handlers.
 */
export function EChart({
  option, height = 320, label,
  onEvents,
}: {
  option: EChartsCoreOption;
  height?: number;
  label: string;
  onEvents?: Record<string, (params: unknown) => void>;
}) {
  const el    = useRef<HTMLDivElement>(null);
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, THEME_NAME, { renderer: "canvas" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption({ aria: { enabled: true, label: { description: label } }, ...option }, { notMerge: true });
  }, [option, label]);

  // Bind / rebind event handlers whenever they change
  useEffect(() => {
    const c = chart.current;
    if (!c || !onEvents) return;
    for (const [ev, handler] of Object.entries(onEvents)) {
      c.off(ev);
      c.on(ev, handler as (p: unknown) => void);
    }
    return () => {
      if (!chart.current) return;
      for (const ev of Object.keys(onEvents)) chart.current.off(ev);
    };
  }, [onEvents]);

  return <div ref={el} className="echart" style={{ height }} role="img" aria-label={label} />;
}
