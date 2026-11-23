import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { MarkerLayer } from "../components/MarkerLayer";
import { ZoneLayer } from "../components/ZoneLayer";
import { api } from "../api";
import { useStore } from "../store";
import type { Candle } from "../types";

const TIMEFRAMES = ["1m", "5m", "15m", "30m"];

export function ChartPage() {
  const { snapshot } = useStore();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [timeframe, setTimeframe] = useState("1m");

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 440,
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
      rightPriceScale: { borderColor: "#1b2533" },
      timeScale: { timeVisible: true, borderColor: "#1b2533" },
      crosshair: {
        mode: 0,
        vertLine: { color: "#37e0d066", width: 1, style: 3, labelBackgroundColor: "#12303a" },
        horzLine: { color: "#37e0d066", width: 1, style: 3, labelBackgroundColor: "#12303a" },
      },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#3ddc84",
      downColor: "#ff5c6c",
      borderVisible: false,
      wickUpColor: "#3ddc84aa",
      wickDownColor: "#ff5c6caa",
      priceLineColor: "#37e0d0",
      priceLineStyle: 2,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .chart(timeframe)
      .then((payload) => {
        if (cancelled || !seriesRef.current) return;
        const candles = payload.candles as Candle[];
        seriesRef.current.setData(
          candles.map((candle) => ({
            time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
            open: candle.o,
            high: candle.h,
            low: candle.l,
            close: candle.c,
          })),
        );
        chartRef.current?.timeScale().fitContent();
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [timeframe]);

  const chart = snapshot?.chart;

  return (
    <div className="page">
      <h2>Gráfico</h2>
      <div className="button-row">
        {TIMEFRAMES.map((value) => (
          <button
            key={value}
            type="button"
            className={value === timeframe ? "btn active" : "btn"}
            onClick={() => setTimeframe(value)}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="card chart-card">
        <div ref={containerRef} className="chart-canvas" data-chart />
        {chart ? (
          <>
            <ZoneLayer zones={chart.zones} />
            <MarkerLayer markers={chart.markers} />
          </>
        ) : null}
      </div>
    </div>
  );
}
