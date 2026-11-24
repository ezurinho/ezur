interface GaugeProps {
  value: number;
  max: number;
  label: string;
  unit?: string;
  size?: number;
  /** Fraction of the arc where the colour turns from cool to hot. */
  warnAt?: number;
}

/**
 * 240° arc gauge for "how much of the limit is used".
 * Colour encodes usage, not direction: green under the warn mark, amber after it,
 * red when the limit is reached or exceeded.
 */
export function Gauge({
  value,
  max,
  label,
  unit = "",
  size = 104,
  warnAt = 0.7,
}: GaugeProps) {
  const ratio = max > 0 ? Math.max(0, Math.min(1.4, value / max)) : 0;
  const clamped = Math.min(1, ratio);
  // El arco se recorta al 100 % por geometría, pero la cifra central no:
  // 9 sobre un máximo de 3 es 300 %, no «lleno».
  const usage = max > 0 ? Math.max(0, (value / max) * 100) : 0;
  const radius = size / 2 - 8;
  const center = size / 2;
  const startAngle = 150;
  const sweep = 240;

  const polar = (angleDeg: number) => {
    const rad = (angleDeg * Math.PI) / 180;
    return {
      x: center + radius * Math.cos(rad),
      y: center + radius * Math.sin(rad),
    };
  };

  const arcPath = (from: number, to: number) => {
    const a = polar(from);
    const b = polar(to);
    const large = Math.abs(to - from) > 180 ? 1 : 0;
    return `M${a.x.toFixed(2)},${a.y.toFixed(2)} A${radius},${radius} 0 ${large} 1 ${b.x.toFixed(2)},${b.y.toFixed(2)}`;
  };

  const tone = ratio >= 1 ? "bad" : ratio >= warnAt ? "warn" : "accent";
  const spoken = (number: number) =>
    number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  const endAngle = startAngle + sweep * clamped;
  const tickAngle = startAngle + sweep * warnAt;
  const tickOuter = polar(tickAngle);
  const tickInner = {
    x: center + (radius - 5) * Math.cos((tickAngle * Math.PI) / 180),
    y: center + (radius - 5) * Math.sin((tickAngle * Math.PI) / 180),
  };

  return (
    <div className="gauge" data-gauge={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${spoken(value)} de ${spoken(max)} ${unit}`}>
        <path
          d={arcPath(startAngle, startAngle + sweep)}
          fill="none"
          stroke="var(--line)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        {clamped > 0.01 ? (
          <path
            className={`gauge-arc tone-${tone}`}
            key={`${label}-${Math.round(clamped * 100)}`}
            d={arcPath(startAngle, endAngle)}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={100}
            strokeDashoffset={0}
          />
        ) : null}
        <line
          x1={tickInner.x}
          y1={tickInner.y}
          x2={tickOuter.x}
          y2={tickOuter.y}
          stroke="var(--muted)"
          strokeWidth="1.5"
        />
        <text
          x={center}
          y={center + 6}
          textAnchor="middle"
          fill="var(--text)"
          fontFamily="var(--font-mono)"
          fontSize="13"
          fontWeight="600"
        >
          {Math.round(usage)}%
        </text>
      </svg>
      <div className="gauge-readout">
        <b>
          {value.toFixed(value % 1 === 0 ? 0 : 2)} / {max}
          {unit ? ` ${unit}` : ""}
        </b>
        <span>{label}</span>
      </div>
    </div>
  );
}
