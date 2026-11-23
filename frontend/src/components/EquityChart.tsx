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
      layout: {
        background: { color: "transparent" },
        textColor: "#a9b6c6",
        fontFamily: "JetBrains Mono, Cascadia Mono, ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#ffffff08" },
        horzLines: { color: "#ffffff08" },
      },
      timeScale: { timeVisible: true, borderColor: "#1b2533" },
      rightPriceScale: { borderColor: "#1b2533" },
      crosshair: {
        vertLine: { color: "#37e0d066", style: 3, labelBackgroundColor: "#12303a" },
        horzLine: { color: "#37e0d066", style: 3, labelBackgroundColor: "#12303a" },
      },
    });
    const series = chart.addAreaSeries({
      lineColor: "#37e0d0",
      topColor: "#37e0d055",
      bottomColor: "#37e0d000",
      lineWidth: 2,
      priceLineVisible: false,
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
