import { useId, useMemo, useRef, useState } from "react";
import type { Candle } from "../types";

interface Props {
  candles: Candle[];
  height?: number;
  points?: number;
  label?: string;
  /** Antes de la primera respuesta se dibuja una silueta; después, si no hay
   *  velas, se dice: un esqueleto eterno finge que algo está cargando. */
  loading?: boolean;
}

function pathFor(values: number[], width: number, height: number, pad = 4) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / Math.max(1, values.length - 1);
  return {
    min,
    max,
    step,
    points: values.map((value, index) => ({
      x: index * step,
      y: height - pad - ((value - min) / span) * (height - pad * 2),
    })),
  };
}

/**
 * Hand-drawn area chart for the price of the open window.
 *
 * The candles chart (lightweight-charts) is for reading structure; this one
 * answers one question at a glance — is the line going up or down — and shows
 * the exact value under the cursor. No library, no axis soup, and the same
 * accent as the rest of the HUD.
 */
export function MarketPulse({
  candles,
  height = 120,
  points = 90,
  label = "precio",
  loading = false,
}: Props) {
  const gradient = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const sampled = useMemo(() => {
    if (candles.length <= points) return candles;
    const step = Math.ceil(candles.length / points);
    return candles.filter((_, index) => index % step === 0 || index === candles.length - 1);
  }, [candles, points]);

  const geometry = useMemo(() => {
    if (sampled.length < 2) return null;
    const width = 320;
    const closes = sampled.map((candle) => candle.c);
    const line = pathFor(closes, width, height);
    const polyline = line.points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" L");
    return {
      width,
      line,
      path: `M${polyline}`,
      area: `M0,${height} L${polyline} L${width},${height} Z`,
      // Plana no es alcista: el mismo criterio que la minigráfica del inicio.
      direction:
        closes[closes.length - 1] > closes[0]
          ? "up"
          : closes[closes.length - 1] < closes[0]
            ? "down"
            : "flat",
    };
  }, [sampled, height]);

  if (!geometry) {
    return loading ? (
      <div className="market-pulse-empty skeleton skeleton-block" />
    ) : (
      <p className="empty">Sin velas todavía: el mercado aún no ha entregado dos velas.</p>
    );
  }

  const color =
    geometry.direction === "up"
      ? "var(--good)"
      : geometry.direction === "down"
        ? "var(--bad)"
        : "var(--muted)";
  // El puntero puede quedarse en un índice que la vela recortada ya no tiene:
  // sin acotarlo, `sampled[hover].c` revienta al llegar menos velas.
  const hoverIndex = hover !== null ? Math.min(hover, sampled.length - 1) : null;

  const onMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const ratio = Math.min(0.999, Math.max(0, (event.clientX - rect.left) / rect.width));
    setHover(Math.round(ratio * (sampled.length - 1)));
  };

  const active = hoverIndex !== null ? geometry.line.points[hoverIndex] : null;
  const activeCandle = hoverIndex !== null ? sampled[hoverIndex] : sampled[sampled.length - 1];
  const value = hoverIndex !== null ? sampled[hoverIndex].c : sampled[sampled.length - 1].c;

  return (
    <div className="market-pulse" style={{ ["--pulse-color" as string]: color }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${geometry.width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label}: ${value.toFixed(2)}${
          activeCandle
            ? ` · ${new Date(activeCandle.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
            : ""
        }`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`pulse-${gradient}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.34" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path className="pulse-area" d={geometry.area} fill={`url(#pulse-${gradient})`} />
        <path
          className="pulse-line"
          d={geometry.path}
          fill="none"
          stroke={color}
          strokeWidth="1.6"
          pathLength={1}
        />
        {active ? (
          <line
            className="pulse-cursor"
            x1={active.x}
            y1={0}
            x2={active.x}
            y2={height}
            stroke={color}
            strokeOpacity="0.35"
            strokeDasharray="3 3"
          />
        ) : null}
        <circle cx={geometry.line.points[geometry.line.points.length - 1].x - 1} cy={geometry.line.points[geometry.line.points.length - 1].y} r="2.6" fill={color} className="pulse-dot" />
      </svg>
      <div className="pulse-foot">
        <b className="mono">
          {value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </b>
        <span className="muted small mono">
          {activeCandle ? new Date(activeCandle.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
        </span>
      </div>
    </div>
  );
}
