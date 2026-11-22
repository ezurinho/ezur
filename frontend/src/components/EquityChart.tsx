import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";

interface Point {
  ts: string;
  equity: number;
}

export function EquityChart({ points, height = 220 }: { points: Point[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { color: "#161b22" }, textColor: "#c9d1d9" },
      grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
      timeScale: { timeVisible: true },
      rightPriceScale: { borderColor: "#21262d" },
    });
    const series = chart.addAreaSeries({
      lineColor: "#4c8dff",
      topColor: "#4c8dff55",
      bottomColor: "#4c8dff00",
      lineWidth: 2,
    });
    series.setData(
      points.map((point) => ({
        time: (Date.parse(point.ts) / 1000) as UTCTimestamp,
        value: point.equity,
      })),
    );
    chart.timeScale().fitContent();
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [points, height]);

  if (points.length === 0) {
    return <p className="empty">Sin puntos de equidad</p>;
  }
  return <div ref={containerRef} className="chart-canvas" data-equity-chart />;
}
