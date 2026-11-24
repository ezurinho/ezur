import { useId, useMemo } from "react";

interface Props {
  /** Equity points in order; the drawdown is computed against the running peak. */
  points: { equity: number }[];
  /**
   * Capital con el que empezó la cuenta. Sin él, el primer cierre cargado hace
   * de pico y la caída de la primera operación desaparece de la curva.
   */
  baseline?: number | null;
  height?: number;
}

/** Equity drawdown in percent, worst first memory. Exported for tests. */
export function drawdownCurve(
  points: { equity: number }[],
  baseline?: number | null,
): number[] {
  // La cuenta empieza en el capital inicial, no en el primer cierre: si la
  // primera operación pierde, esa caída también es drawdown. Sin capital se usa
  // el primer punto, y la vista lo dice.
  let peak =
    typeof baseline === "number" && Number.isFinite(baseline) && baseline > 0
      ? baseline
      : -Infinity;
  return points.map((point) => {
    peak = Math.max(peak, point.equity);
    const value = peak > 0 ? ((point.equity - peak) / peak) * 100 : 0;
    // Sumar 0 convierte -0 en 0: un «-0.00 %» en pantalla parece un error.
    return value + 0;
  });
}

/**
 * Underwater curve: the distance below the account's high-water mark.
 *
 * The mark starts at the capital the account began with, not at the first
 * loaded close: a losing first trade is a drawdown too. Without that capital
 * the first close is used, and the view says which reference it used.
 *
 * A rising equity line hides how deep the worst dip was. This chart only shows
 * the dip — always at or below zero — so «cómo de mal se puso» has an answer
 * that does not require squinting at the equity chart.
 */
export function Underwater({ points, baseline, height = 120 }: Props) {
  const gradient = useId().replace(/:/g, "");

  const geometry = useMemo(() => {
    if (points.length < 2) return null;
    const values = drawdownCurve(points, baseline);
    const worst = Math.min(...values);
    const span = Math.abs(worst) || 1;
    const width = 320;
    const step = width / (values.length - 1);
    const scaled = values.map((value, index) => ({
      x: index * step,
      y: 4 + (Math.abs(value) / span) * (height - 10),
    }));
    const polyline = scaled.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" L");
    return {
      width,
      worst,
      path: `M0,0 L${polyline} L${width},0 Z`,
      line: `M${polyline}`,
      now: values[values.length - 1],
    };
  }, [points, baseline, height]);

  if (!geometry) return <p className="empty">Sin curva de equidad todavía</p>;

  return (
    <div className="underwater">
      <svg
        viewBox={`0 0 ${geometry.width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`curva de la caída: peor ${geometry.worst.toFixed(2)} %, ahora ${geometry.now.toFixed(2)} %`}
      >
        <defs>
          <linearGradient id={`under-${gradient}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--bad)" stopOpacity="0.42" />
            <stop offset="100%" stopColor="var(--bad)" stopOpacity="0.04" />
          </linearGradient>
        </defs>
        <path d={geometry.path} fill={`url(#under-${gradient})`} className="under-area" />
        <path
          d={geometry.line}
          fill="none"
          stroke="var(--bad)"
          strokeWidth="1.4"
          pathLength={1}
          className="under-line"
        />
      </svg>
      <div className="underwater-foot">
        <span>
          peor caída{" "}
          <b className={`mono ${geometry.worst < 0 ? "tone-bad" : ""}`}>
            {geometry.worst.toFixed(2)} %
          </b>
        </span>
        <span>
          ahora <b className="mono">{geometry.now.toFixed(2)} %</b>
        </span>
      </div>
    </div>
  );
}
