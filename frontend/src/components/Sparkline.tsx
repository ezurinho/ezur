import { useEffect, useId, useMemo, useState } from "react";

export function useClock(intervalMs = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

interface SparklineProps {
  values: number[];
  height?: number;
  stroke?: string;
  fill?: boolean;
  label?: string;
}

/** Tiny SVG trend line: no dependency, no axes, no interaction. */
export function Sparkline({
  values,
  height = 26,
  stroke,
  fill = true,
  label,
}: SparklineProps) {
  // Un id por instancia: dos sparklines con la misma dirección compartían
  // `spark-up`, y el `url(#…)` de la segunda apuntaba al gradiente de la
  // primera, con el `currentColor` de otro contenedor.
  const uid = useId();
  const geometry = useMemo(() => {
    const points = values.filter((value) => Number.isFinite(value));
    if (points.length < 2) return null;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;
    const width = 100;
    const step = width / (points.length - 1);
    const coords = points.map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / span) * (height - 2) - 1;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    return {
      line: `M${coords.join(" L")}`,
      area: `M0,${height} L${coords.join(" L")} L${width},${height} Z`,
      // Plana no es alcista: sin cambio, sin color de victoria.
      direction:
        points[points.length - 1] > points[0]
          ? "up"
          : points[points.length - 1] < points[0]
            ? "down"
            : "flat",
    };
  }, [values, height]);

  if (!geometry) return <div className="kpi-spark" />;

  const gradientId = `spark-${geometry.direction}-${uid}`;

  return (
    <svg
      className={`sparkline ${geometry.direction}`}
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={
        label ??
        (geometry.direction === "up"
          ? "tendencia alcista"
          : geometry.direction === "down"
            ? "tendencia bajista"
            : "sin cambio en el periodo")
      }
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill ? (
        <path className="area" d={geometry.area} fill={`url(#${gradientId})`} />
      ) : null}
      <path
        className="line"
        d={geometry.line}
        stroke={stroke ?? "currentColor"}
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={0}
      />
    </svg>
  );
}
