/**
 * ECharts, imported modularly (only the chart types and components the dashboard uses) and
 * themed from the design tokens - one place to change the look of every chart.
 */
import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent, DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { CHART, SERIES } from "../theme/chart";

echarts.use([
  LineChart, BarChart, HeatmapChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkAreaComponent,
  DataZoomComponent, AriaComponent, VisualMapComponent, CanvasRenderer,
]);

const axis = {
  axisLine: { lineStyle: { color: CHART.axis } },
  axisTick: { show: false },
  axisLabel: { color: CHART.textMuted, fontSize: CHART.fontSize },
  splitLine: { lineStyle: { color: CHART.grid } },
  nameTextStyle: { color: CHART.textMuted },
};

export const THEME_NAME = "celeris";

echarts.registerTheme(THEME_NAME, {
  color: [...SERIES],
  backgroundColor: "transparent",
  textStyle: { fontFamily: CHART.fontFamily, color: CHART.text, fontSize: CHART.fontSize },
  categoryAxis: { ...axis, splitLine: { show: false } },
  valueAxis: { ...axis, axisLine: { show: false } },
  legend: { textStyle: { color: CHART.text }, itemWidth: 14, itemHeight: 8, icon: "roundRect" },
  tooltip: {
    backgroundColor: "#16223a",
    borderColor: "#2e3f5f",
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: "#e8eef7", fontSize: 12 },
    extraCssText: "box-shadow: 0 8px 24px rgba(0,0,0,.45); border-radius: 10px;",
    axisPointer: { lineStyle: { color: "#3a4a66" }, crossStyle: { color: "#3a4a66" } },
  },
  line: { symbol: "none", lineStyle: { width: CHART.lineWidth }, smooth: false },
  bar: { itemStyle: { borderRadius: CHART.barRadius } },
});

export { echarts };
