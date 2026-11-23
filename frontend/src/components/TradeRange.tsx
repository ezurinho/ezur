import { useMemo } from "react";

interface Props {
  side: "long" | "short";
  entry: number;
  stop: number;
  target: number | null;
  price: number | null;
  decimals?: number;
}

/**
 * Where the price sits between the stop and the target.
 *
 * A trader reading «stop 61.654 / objetivo 60.832» has to do the geometry in
 * their head. This bar does it: the filled part is how much of the way to the
 * target the trade has travelled, and the dot is the price right now. Red side
 * is loss, green side is gain, labelled with the actual numbers.
 */
export function TradeRange({ side, entry, stop, target, price, decimals = 2 }: Props) {
  const geometry = useMemo(() => {
    if (target === null || price === null) return null;
    const low = Math.min(stop, target);
    const high = Math.max(stop, target);
    const span = high - low || 1;
    const clamp = (value: number) => Math.min(100, Math.max(0, ((value - low) / span) * 100));
    return {
      entry: clamp(entry),
      stop: clamp(stop),
      target: clamp(target),
      price: clamp(price),
      progress:
        side === "long"
          ? Math.min(100, Math.max(0, ((price - entry) / (target - entry || 1)) * 100))
          : Math.min(100, Math.max(0, ((entry - price) / (entry - target || 1)) * 100)),
    };
  }, [side, entry, stop, target, price]);

  if (!geometry || price === null) {
    return <p className="muted small">Sin objetivo definido: la barra necesita stop y objetivo.</p>;
  }

  const inProfit = side === "long" ? price >= entry : price <= entry;
  const format = (value: number) =>
    value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  return (
    <div className="trade-range" data-trade-range>
      <div className="trade-range-labels">
        <span className="tone-bad mono">stop {format(stop)}</span>
        <span className="mono">entrada {format(entry)}</span>
        <span className="tone-good mono">objetivo {format(target as number)}</span>
      </div>
      <div className="trade-range-track" role="img" aria-label={`precio ${format(price)} entre stop y objetivo`}>
        <span className="trade-range-loss" style={{ width: `${Math.min(geometry.entry, geometry.target)}%` }} />
        <span
          className="trade-range-win"
          style={{
            left: `${Math.min(geometry.entry, geometry.target)}%`,
            width: `${Math.abs(geometry.target - geometry.entry)}%`,
          }}
        />
        <span className="trade-range-entry" style={{ left: `${geometry.entry}%` }} aria-hidden="true" />
        <span
          className={`trade-range-price ${inProfit ? "up" : "down"}`}
          style={{ left: `${geometry.price}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="trade-range-foot">
        <span className={`mono ${inProfit ? "tone-good" : "tone-bad"}`}>{format(price)}</span>
        <span className="muted small">{Math.round(geometry.progress)} % del camino al objetivo</span>
      </div>
    </div>
  );
}
