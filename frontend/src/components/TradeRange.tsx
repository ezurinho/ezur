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
    const entryPct = clamp(entry);
    const stopPct = clamp(stop);
    const targetPct = clamp(target);
    return {
      entry: entryPct,
      stop: stopPct,
      target: targetPct,
      price: clamp(price),
      // Rojo de la entrada al stop y verde de la entrada al objetivo. En un
      // corto el stop queda a la derecha, así que las zonas se calculan desde
      // la entrada y no desde el borde izquierdo.
      lossLeft: Math.min(entryPct, stopPct),
      lossWidth: Math.abs(entryPct - stopPct),
      winLeft: Math.min(entryPct, targetPct),
      winWidth: Math.abs(entryPct - targetPct),
      progress:
        side === "long"
          ? Math.min(100, Math.max(0, ((price - entry) / (target - entry || 1)) * 100))
          : Math.min(100, Math.max(0, ((entry - price) / (entry - target || 1)) * 100)),
    };
  }, [side, entry, stop, target, price]);

  if (!geometry || price === null) {
    // El aviso nombra lo que falta de verdad: sin precio no es culpa del objetivo.
    return (
      <p className="muted small">
        {target === null
          ? "Sin objetivo definido: la barra necesita stop y objetivo."
          : "Sin precio actual: la barra necesita el último precio para situar la operación."}
      </p>
    );
  }

  const inProfit = side === "long" ? price >= entry : price <= entry;
  // Justo en la entrada no se gana ni se pierde: verde ahí sería una promesa.
  const flat = price === entry;
  const tone = flat ? "" : inProfit ? "tone-good" : "tone-bad";
  const format = (value: number) =>
    value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  return (
    <div className="trade-range" data-trade-range data-side={side}>
      <div className="trade-range-labels">
        {/* En un corto el eje va de objetivo a stop: las etiquetas siguen al
            eje, no al hábito de leer «stop» primero. */}
        {(side === "long"
          ? [
              <span key="stop" className="tone-bad mono">stop {format(stop)}</span>,
              <span key="entry" className="mono">entrada {format(entry)}</span>,
              <span key="target" className="tone-good mono">objetivo {format(target as number)}</span>,
            ]
          : [
              <span key="target" className="tone-good mono">objetivo {format(target as number)}</span>,
              <span key="entry" className="mono">entrada {format(entry)}</span>,
              <span key="stop" className="tone-bad mono">stop {format(stop)}</span>,
            ]
        )}
      </div>
      <div className="trade-range-track" role="img" aria-label={`precio ${format(price)} entre stop y objetivo`}>
        <span
          className="trade-range-loss"
          style={{ left: `${geometry.lossLeft}%`, width: `${geometry.lossWidth}%` }}
        />
        <span
          className="trade-range-win"
          style={{ left: `${geometry.winLeft}%`, width: `${geometry.winWidth}%` }}
        />
        <span className="trade-range-entry" style={{ left: `${geometry.entry}%` }} aria-hidden="true" />
        <span
          className={`trade-range-price ${flat ? "" : inProfit ? "up" : "down"}`.trim()}
          style={{ left: `${geometry.price}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="trade-range-foot">
        <span className={`mono ${tone}`}>{format(price)}</span>
        <span className="muted small">{Math.round(geometry.progress)} % del camino al objetivo</span>
      </div>
    </div>
  );
}
