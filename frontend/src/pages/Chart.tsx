import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { MarkerLayer } from "../components/MarkerLayer";
import { ZoneLayer } from "../components/ZoneLayer";
import { useUiMode } from "../mode";
import { useTheme } from "../theme";
import { api } from "../api";
import { useStore } from "../store";
import type { Candle } from "../types";

const TIMEFRAMES = ["1m", "5m", "15m", "30m"] as const;

interface Overlays {
  sma: boolean;
  volume: boolean;
  zones: boolean;
  markers: boolean;
}

/** Simple moving average over closes; null until the window is full. */
export function movingAverage(candles: Candle[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let index = 0; index < candles.length; index += 1) {
    sum += candles[index].c;
    if (index >= period) sum -= candles[index - period].c;
    out.push(index >= period - 1 ? sum / period : null);
  }
  return out;
}

function periodsFromMetrics(metrics: Record<string, { label: string }>): number[] {
  const found = Object.values(metrics)
    .map((metric) => /SMA\((\d+)\)/i.exec(metric.label))
    .filter((match): match is RegExpExecArray => match !== null)
    .map((match) => Number(match[1]));
  return [...new Set(found)].sort((a, b) => a - b).slice(0, 2);
}

export function ChartPage() {
  const { snapshot } = useStore();
  const { isSimple } = useUiMode();
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const smaRefs = useRef<(ISeriesApi<"Line"> | null)[]>([]);
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("1m");
  const [overlays, setOverlays] = useState<Overlays>({
    sma: true,
    volume: true,
    zones: true,
    markers: true,
  });
  const [candles, setCandles] = useState<Candle[]>([]);
  const lastBarRef = useRef<string | null>(null);

  const periods = useMemo(
    () => periodsFromMetrics(snapshot?.strategy.metrics ?? {}),
    [snapshot?.strategy.metrics],
  );

  // Chart is recreated on theme change: lightweight-charts paints on canvas and
  // cannot inherit CSS variables, so the palette is read at creation time.
  useEffect(() => {
    if (!containerRef.current) return;
    const styles = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    const accent = read("--accent", "#37e0d0");
    const good = read("--good", "#3ddc84");
    const bad = read("--bad", "#ff5c6c");
    const line = read("--line", "#1b2533");
    const text = read("--text-dim", "#a9b6c6");
    const muted = read("--muted", "#6f8096");

    const chart = createChart(containerRef.current, {
      height: 440,
      layout: {
        background: { color: "transparent" },
        textColor: text,
        fontFamily: "JetBrains Mono, Cascadia Mono, ui-monospace, monospace",
        fontSize: 11,
      },
      grid: { vertLines: { color: `${muted}14` }, horzLines: { color: `${muted}14` } },
      rightPriceScale: { borderColor: line, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { timeVisible: true, borderColor: line, rightOffset: 4 },
      crosshair: {
        mode: 0,
        vertLine: { color: `${accent}66`, width: 1, style: 3, labelBackgroundColor: accent },
        horzLine: { color: `${accent}66`, width: 1, style: 3, labelBackgroundColor: accent },
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: good,
      downColor: bad,
      borderVisible: false,
      wickUpColor: `${good}aa`,
      wickDownColor: `${bad}aa`,
      priceLineColor: accent,
      priceLineStyle: 2,
    });
    series.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.26 } });

    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const palette = [accent, read("--accent-2", "#6ea8ff"), read("--warn", "#ffb547")];
    smaRefs.current = periods.slice(0, 2).map((_, index) =>
      chart.addLineSeries({
        color: palette[index % palette.length],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      }),
    );

    chartRef.current = chart;
    candleRef.current = series;
    volumeRef.current = volume;
    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      smaRefs.current = [];
    };
  }, [theme, periods]);

  const liveBar = snapshot?.data.last_bar_ts ?? null;

  useEffect(() => {
    let cancelled = false;
    const keepRange = chartRef.current?.timeScale().getVisibleLogicalRange() ?? null;
    api
      .chart(timeframe)
      .then((payload) => {
        if (cancelled || !candleRef.current) return;
        const rows = payload.candles as Candle[];
        setCandles(rows);
        candleRef.current.setData(
          rows.map((candle) => ({
            time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
            open: candle.o,
            high: candle.h,
            low: candle.l,
            close: candle.c,
          })),
        );
        volumeRef.current?.setData(
          rows.map((candle) => ({
            time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
            value: candle.v ?? 0,
            color: candle.c >= candle.o ? "#3ddc8440" : "#ff5c6c40",
          })),
        );
        periods.slice(0, 2).forEach((period, index) => {
          const series = smaRefs.current[index];
          if (!series) return;
          const values = movingAverage(rows, period);
          series.setData(
            rows
              .map((candle, position) => ({ candle, value: values[position] }))
              .filter((entry): entry is { candle: Candle; value: number } => entry.value !== null)
              .map((entry) => ({
                time: (Date.parse(entry.candle.t) / 1000) as UTCTimestamp,
                value: entry.value,
              })),
          );
        });
        const scale = chartRef.current?.timeScale();
        if (lastBarRef.current !== null && keepRange) {
          scale?.setVisibleLogicalRange(keepRange);
        } else {
          scale?.fitContent();
        }
        lastBarRef.current = liveBar;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [timeframe, liveBar, periods]);

  useEffect(() => {
    candleRef.current?.applyOptions({ visible: true });
    volumeRef.current?.applyOptions({ visible: overlays.volume });
    smaRefs.current.forEach((series) => series?.applyOptions({ visible: overlays.sma }));
  }, [overlays]);

  const chart = snapshot?.chart;
  const lastClose = candles.length ? candles[candles.length - 1].c : null;
  const firstClose = candles.length ? candles[0].c : null;
  const changePct =
    lastClose !== null && firstClose ? ((lastClose - firstClose) / firstClose) * 100 : null;

  const toggles = ([
    { key: "sma", label: `medias ${periods.join(" / ")}`, show: periods.length > 0 },
    { key: "volume", label: "volumen", show: true },
    { key: "zones", label: "zonas", show: Boolean(chart?.zones?.length) && !isSimple },
    { key: "markers", label: "marcadores", show: Boolean(chart?.markers?.length) && !isSimple },
  ] as { key: keyof Overlays; label: string; show: boolean }[]).filter((item) => item.show);

  return (
    <div className="page">
      <h2 className="page-title">
        Gráfico
        <span className="live-chip">
          <span className="led led-running" aria-hidden="true" /> en vivo
        </span>
      </h2>

      <p className="simple-lead">
        {isSimple
          ? "Cada vela es un minuto: verde sube, roja baja. La línea de puntos es el precio de ahora."
          : "Las medias suavizan el ruido; el volumen dice cuánta gente movió cada vela. Apaga lo que no estés mirando."}
      </p>

      <div className="chart-toolbar">
        <div className="segmented" role="group" aria-label="Temporalidad">
          {TIMEFRAMES.map((value) => (
            <button
              key={value}
              type="button"
              className={value === timeframe ? "seg active" : "seg"}
              onClick={() => setTimeframe(value)}
              aria-pressed={value === timeframe}
            >
              {value}
            </button>
          ))}
        </div>

        <div className="chart-toggles" role="group" aria-label="Capas del gráfico">
          {toggles.map((item) => (
            <button
              key={item.key}
              type="button"
              className={overlays[item.key] ? "chip active" : "chip"}
              onClick={() => setOverlays({ ...overlays, [item.key]: !overlays[item.key] })}
              aria-pressed={overlays[item.key]}
              data-chart-toggle={item.key}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="chart-readout">
          {lastClose !== null ? (
            <>
              <b className="mono">{lastClose.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b>
              {changePct !== null ? (
                <span className={`mono small ${changePct >= 0 ? "tone-good" : "tone-bad"}`}>
                  {changePct >= 0 ? "+" : ""}
                  {changePct.toFixed(2)} % en la ventana
                </span>
              ) : null}
            </>
          ) : null}
          <button
            type="button"
            className="chip"
            onClick={() => chartRef.current?.timeScale().fitContent()}
          >
            ajustar
          </button>
        </div>
      </div>

      <div className="card chart-card">
        <div ref={containerRef} className="chart-canvas" data-chart />
        {chart && overlays.zones && !isSimple ? <ZoneLayer zones={chart.zones} /> : null}
        {chart && overlays.markers && !isSimple ? <MarkerLayer markers={chart.markers} /> : null}
      </div>
    </div>
  );
}
