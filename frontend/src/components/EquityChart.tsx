import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useTheme } from "../theme";

interface Point {
  ts: string;
  equity: number;
}

const NO_MARKS: Point[] = [];

/**
 * Equity curve with the theme's accent and a reference line.
 *
 * The baseline is the honest reference: without it a rising line says nothing
 * about whether the account is above or below where it started. The true
 * reference is the starting capital, not the first loaded point — the first
 * point already includes the first trade's result. Without the capital, the
 * line says so: «primer cierre cargado». `fitContent` runs only on the first
 * paint so a live update does not move the view.
 */
export function baselineLine(
  points: { equity: number }[],
  baseline?: number | null,
): { price: number; title: string } | null {
  if (baseline !== null && baseline !== undefined && Number.isFinite(baseline)) {
    return { price: baseline, title: "capital inicial" };
  }
  const first = points[0]?.equity;
  return first === undefined ? null : { price: first, title: "primer cierre cargado" };
}

export function EquityChart({
  points,
  marks,
  baseline,
  height = 220,
}: {
  points: Point[];
  marks?: Point[];
  baseline?: number | null;
  height?: number;
}) {
  const intraday = marks ?? NO_MARKS;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;
    const styles = getComputedStyle(document.documentElement);
    const accent = styles.getPropertyValue("--accent").trim() || "#37e0d0";
    const line = styles.getPropertyValue("--line").trim() || "#1b2533";
    const muted = styles.getPropertyValue("--muted").trim() || "#6f8096";
    const text = styles.getPropertyValue("--text-dim").trim() || "#a9b6c6";
    const good = styles.getPropertyValue("--good").trim() || "#3ddc84";
    const warn = styles.getPropertyValue("--warn").trim() || "#ffb547";

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: "transparent" },
        textColor: text,
        fontFamily: "JetBrains Mono, Cascadia Mono, ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: `${muted}14` },
        horzLines: { color: `${muted}14` },
      },
      timeScale: { timeVisible: true, borderColor: line },
      rightPriceScale: { borderColor: line },
      crosshair: {
        vertLine: { color: `${accent}66`, style: 3, labelBackgroundColor: accent },
        horzLine: { color: `${accent}66`, style: 3, labelBackgroundColor: accent },
      },
    });

    const series = chart.addAreaSeries({
      lineColor: accent,
      topColor: `${accent}55`,
      bottomColor: `${accent}00`,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    series.setData(
      points.map((point) => ({
        time: (Date.parse(point.ts) / 1000) as UTCTimestamp,
        value: point.equity,
      })),
    );

    // Las marcas intradía no son cierres auditados: van en una línea propia,
    // discontinua y sin último valor, para que la curva sólida siga siendo la
    // única que representa la equity reconstruida desde el libro.
    if (intraday.length > 0) {
      const marksSeries = chart.addLineSeries({
        color: warn,
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
        title: "marcas intradía",
      });
      marksSeries.setData(
        intraday.map((point) => ({
          time: (Date.parse(point.ts) / 1000) as UTCTimestamp,
          value: point.equity,
        })),
      );
    }

    const reference = baselineLine(points, baseline);
    if (reference) {
      series.createPriceLine({
        price: reference.price,
        color: `${good}88`,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: reference.title,
      });
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [points, intraday, baseline, height, theme]);

  if (points.length === 0 && intraday.length === 0) {
    return <p className="empty">Sin puntos de equidad</p>;
  }
  return <div ref={containerRef} className="chart-canvas" data-equity-chart />;
}
