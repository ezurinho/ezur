import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { MarkerLayer } from "../components/MarkerLayer";
import { ZoneLayer } from "../components/ZoneLayer";
import { useClock } from "../components/Sparkline";
import { useUiMode } from "../mode";
import { useTheme } from "../theme";
import { api } from "../api";
import { useStore } from "../store";
import { marketFreshness } from "../utils";
import type { Candle } from "../types";

const TIMEFRAMES = ["1m", "5m", "15m", "30m"] as const;
// La frase del modo básico nombra la vela que hay en pantalla; con 5m fijo
// decir «cada vela es un minuto» era falso en cuanto el operador cambiaba.
const VELA_WORDS: Record<(typeof TIMEFRAMES)[number], string> = {
  "1m": "un minuto",
  "5m": "cinco minutos",
  "15m": "quince minutos",
  "30m": "media hora",
};
const CHART_TYPES = ["candles", "line", "area"] as const;
type ChartType = (typeof CHART_TYPES)[number];
const TYPE_LABELS: Record<ChartType, string> = {
  candles: "velas",
  line: "línea",
  area: "área",
};
const PREF_KEY = "ezur.chart.prefs";

interface Prefs {
  timeframe: (typeof TIMEFRAMES)[number];
  type: ChartType;
  grid: boolean;
  overlays: Overlays;
}

/** Bar under the crosshair, or the close when the series has no OHLC. */
interface HoverBar {
  o?: number;
  h?: number;
  l?: number;
  c: number;
}

function readPrefs(): Prefs | null {
  try {
    const raw = window.localStorage.getItem(PREF_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    if (!parsed.timeframe || !TIMEFRAMES.includes(parsed.timeframe)) return null;
    return {
      timeframe: parsed.timeframe,
      type: parsed.type && CHART_TYPES.includes(parsed.type) ? parsed.type : "candles",
      grid: parsed.grid ?? true,
      overlays: {
        sma: parsed.overlays?.sma ?? true,
        volume: parsed.overlays?.volume ?? true,
        zones: parsed.overlays?.zones ?? true,
        markers: parsed.overlays?.markers ?? true,
      },
    };
  } catch {
    return null;
  }
}

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
  const { theme, accent: accentOverride } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceRef = useRef<
    ISeriesApi<"Candlestick"> | ISeriesApi<"Line"> | ISeriesApi<"Area"> | null
  >(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const smaRefs = useRef<(ISeriesApi<"Line"> | null)[]>([]);
  const initial = useRef(readPrefs());
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>(
    initial.current?.timeframe ?? "1m",
  );
  const [overlays, setOverlays] = useState<Overlays>(
    initial.current?.overlays ?? { sma: true, volume: true, zones: true, markers: true },
  );
  const [chartType, setChartType] = useState<ChartType>(initial.current?.type ?? "candles");
  const [grid, setGrid] = useState<boolean>(initial.current?.grid ?? true);
  const [hover, setHover] = useState<HoverBar | null>(null);

  // La configuración del gráfico es del operador, no de la sesión: se recuerda.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        PREF_KEY,
        JSON.stringify({ timeframe, type: chartType, grid, overlays }),
      );
    } catch {
      /* sin almacenamiento, el gráfico simplemente vuelve a los valores por defecto */
    }
  }, [timeframe, chartType, grid, overlays]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartError, setChartError] = useState<string | null>(null);
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
      grid: {
        vertLines: { color: grid ? `${muted}14` : "transparent" },
        horzLines: { color: grid ? `${muted}14` : "transparent" },
      },
      rightPriceScale: { borderColor: line, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { timeVisible: true, borderColor: line, rightOffset: 4 },
      crosshair: {
        mode: 0,
        vertLine: { color: `${accent}66`, width: 1, style: 3, labelBackgroundColor: accent },
        horzLine: { color: `${accent}66`, width: 1, style: 3, labelBackgroundColor: accent },
      },
    });

    const series =
      chartType === "candles"
        ? chart.addCandlestickSeries({
            upColor: good,
            downColor: bad,
            borderVisible: false,
            wickUpColor: `${good}aa`,
            wickDownColor: `${bad}aa`,
            priceLineColor: accent,
            priceLineStyle: 2,
          })
        : chartType === "line"
          ? chart.addLineSeries({
              color: accent,
              lineWidth: 2,
              priceLineColor: accent,
              priceLineStyle: 2,
            })
          : chart.addAreaSeries({
              lineColor: accent,
              topColor: `${accent}44`,
              bottomColor: `${accent}00`,
              lineWidth: 2,
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

    // Lectura bajo el cursor: el dato que el operador está mirando, no el último.
    chart.subscribeCrosshairMove((param) => {
      const active = priceRef.current;
      if (!active || !param.time) {
        setHover(null);
        return;
      }
      const data = param.seriesData.get(active as ISeriesApi<"Candlestick">) as
        | { open?: number; high?: number; low?: number; close?: number }
        | { value?: number }
        | undefined;
      if (!data) {
        setHover(null);
        return;
      }
      if (typeof (data as { close?: number }).close === "number") {
        const bar = data as { open?: number; high?: number; low?: number; close: number };
        setHover({ o: bar.open, h: bar.high, l: bar.low, c: bar.close });
      } else if (typeof (data as { value?: number }).value === "number") {
        setHover({ c: (data as { value: number }).value });
      } else {
        setHover(null);
      }
    });

    chartRef.current = chart;
    priceRef.current = series;
    volumeRef.current = volume;
    return () => {
      chart.remove();
      chartRef.current = null;
      priceRef.current = null;
      volumeRef.current = null;
      smaRefs.current = [];
      setHover(null);
    };
  }, [theme, periods, chartType, grid, accentOverride]);

  const liveBar = snapshot?.data.last_bar_ts ?? null;
  // Un reloj propio: si el feed se para, no llegan snapshots y el chip se
  // quedaría diciendo «en vivo» para siempre con la última hora congelada.
  const tick = useClock(15_000);
  const fresh = marketFreshness(liveBar, tick.getTime());

  useEffect(() => {
    let cancelled = false;
    const keepRange = chartRef.current?.timeScale().getVisibleLogicalRange() ?? null;
    const styles = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) =>
      styles.getPropertyValue(name).trim() || fallback;
    const upColor = `${read("--good", "#3ddc84")}40`;
    const downColor = `${read("--bad", "#ff5c6c")}40`;
    api
      .chart(timeframe)
      .then((payload) => {
        if (cancelled || !priceRef.current) return;
        setChartError(null);
        const rows = payload.candles as Candle[];
        setCandles(rows);
        if (chartType === "candles") {
          (priceRef.current as ISeriesApi<"Candlestick">).setData(
            rows.map((candle) => ({
              time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
              open: candle.o,
              high: candle.h,
              low: candle.l,
              close: candle.c,
            })),
          );
        } else {
          (priceRef.current as ISeriesApi<"Line">).setData(
            rows.map((candle) => ({
              time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
              value: candle.c,
            })),
          );
        }
        volumeRef.current?.setData(
          rows.map((candle) => ({
            time: (Date.parse(candle.t) / 1000) as UTCTimestamp,
            value: candle.v ?? 0,
            color: candle.c >= candle.o ? upColor : downColor,
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
      .catch((cause: Error) => {
        if (!cancelled) setChartError(cause.message);
      });
    return () => {
      cancelled = true;
    };
    // Recrear el lienzo (tema, rejilla, tipo) deja la serie vacía: sin volver a
    // pedir las velas, el gráfico quedaba en blanco hasta la siguiente vela.
  }, [timeframe, liveBar, periods, chartType, grid, theme, accentOverride]);

  useEffect(() => {
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
        <span className={`live-chip live-${fresh.tone}`} data-freshness={fresh.tone}>
          <span className={`led led-${fresh.tone}`} aria-hidden="true" /> {fresh.label}
        </span>
      </h2>

      <p className="simple-lead">
        {isSimple
          ? `Cada vela resume ${VELA_WORDS[timeframe]}: verde sube, roja baja. La línea de puntos es el precio de ahora. El eje de horas va en UTC, el reloj de la sesión.`
          : "Las medias suavizan el ruido; el volumen dice cuánta gente movió cada vela. Apaga lo que no estés mirando. El eje de horas va en UTC, el reloj del motor."}
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

        <div className="segmented" role="group" aria-label="Tipo de gráfico">
          {CHART_TYPES.map((value) => (
            <button
              key={value}
              type="button"
              className={value === chartType ? "seg active" : "seg"}
              onClick={() => setChartType(value)}
              aria-pressed={value === chartType}
              data-chart-type={value}
            >
              {TYPE_LABELS[value]}
            </button>
          ))}
        </div>

        <div className="chart-toggles" role="group" aria-label="Capas del gráfico">
          <button
            type="button"
            className={grid ? "chip active" : "chip"}
            onClick={() => setGrid((value) => !value)}
            aria-pressed={grid}
            data-chart-toggle="grid"
          >
            rejilla
          </button>
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
          {hover ? (
            <span className="chart-hover mono small" data-chart-hover>
              {hover.h !== undefined && hover.l !== undefined && hover.o !== undefined
                ? `A ${hover.o.toFixed(2)} · M ${hover.h.toFixed(2)} · m ${hover.l.toFixed(2)} · C ${hover.c.toFixed(2)}`
                : `C ${hover.c.toFixed(2)}`}
            </span>
          ) : null}
          {lastClose !== null ? (
            <>
              <b className="mono">{lastClose.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b>
              {changePct !== null ? (
                <span
                  className={`mono small ${
                    changePct > 0 ? "tone-good" : changePct < 0 ? "tone-bad" : ""
                  }`}
                >
                  {changePct > 0 ? "+" : ""}
                  {changePct.toFixed(2)} % en las últimas {candles.length} velas
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

      {chartError ? (
        <p className="tone-bad small">
          No se pudo cargar el histórico del gráfico: {chartError}. Lo que se vea en el lienzo
          puede ser de la carga anterior.
        </p>
      ) : null}

      <div className="card chart-card">
        <div ref={containerRef} className="chart-canvas" data-chart />
        {chart && overlays.zones && !isSimple ? <ZoneLayer zones={chart.zones} /> : null}
        {chart && overlays.markers && !isSimple ? <MarkerLayer markers={chart.markers} /> : null}
      </div>
    </div>
  );
}
