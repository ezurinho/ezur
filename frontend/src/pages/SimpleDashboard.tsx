import { useEffect, useState } from "react";
import { usePrevious } from "../motion";
import { api } from "../api";
import { DispatchButton } from "../components/Controls";
import { Sparkline, useClock } from "../components/Sparkline";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { MarketPulse } from "../components/MarketPulse";
import { TradeRange } from "../components/TradeRange";
import { Onboarding } from "../components/Onboarding";
import { dominantRejection, plainReason, unblockHint } from "../reasons";
import type { Candle } from "../types";
import { useUiMode } from "../mode";
import { useStore } from "../store";
import { formatDateTime, formatValue, marketFreshness, sideLabel, toFinite } from "../utils";

type Trade = Record<string, unknown>;

const EXIT_WORD: Record<string, string> = {
  stop: "saltó el stop",
  target: "llegó al objetivo",
  manual: "cerrada a mano",
  session_close: "cerrada al final del día",
  cancel: "cancelada",
};

export interface Recap {
  total: number;
  wins: number;
  losses: number;
  /** Operaciones sin pnl_net medido: no suman a favor ni en contra. */
  unmeasured: number;
  worst: number;
  best: number;
  mainReason: string | null;
  fees: number;
  gross: number;
}

/** Resumen en palabras de lo que pasó hoy. Exportado para poder probarlo. */
export function summarize(trades: Trade[]): Recap {
  // Un pnl_net ausente no es un empate: se cuenta aparte en vez de sumar 0 y
  // hacer que la operación parezca medida.
  const pnls = trades
    .map((trade) => toFinite(trade.pnl_net))
    .filter((value): value is number => value !== null);
  const reasons = trades.map((trade) => String(trade.exit_reason ?? ""));
  const counts = reasons.reduce<Record<string, number>>((acc, reason) => {
    acc[reason] = (acc[reason] ?? 0) + 1;
    return acc;
  }, {});
  const mainReason =
    Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  // Una comisión ausente o rota no puede convertir el total en NaN: se salta.
  const fees = trades.reduce((sum, trade) => {
    const value = toFinite(trade.fees);
    return value === null ? sum : sum + Math.abs(value);
  }, 0);
  return {
    total: trades.length,
    unmeasured: trades.length - pnls.length,
    wins: pnls.filter((value) => value > 0).length,
    losses: pnls.filter((value) => value < 0).length,
    worst: pnls.length ? Math.min(...pnls) : 0,
    best: pnls.length ? Math.max(...pnls) : 0,
    mainReason,
    fees,
    // Lo que habría dado el día antes de comisiones: separar los dos números es
    // lo que permite ver si el problema es la regla o el coste.
    gross: pnls.reduce((sum, value) => sum + value, 0) + fees,
  };
}

/**
 * Solo las operaciones cerradas dentro de la sesión actual.
 *
 * La lista de abajo pide las últimas 200 operaciones de toda la historia; si
 * el resumen se hiciera sobre esa lista, «Hoy: 38 operaciones» sería falso en
 * cuanto hubiera días anteriores. Sin fecha de apertura de sesión no se puede
 * afirmar «hoy», así que se devuelve una lista vacía en lugar de exagerar.
 */
export function tradesSince(trades: Trade[], sinceIso: string | null | undefined): Trade[] {
  const since = sinceIso ? Date.parse(sinceIso) : NaN;
  if (Number.isNaN(since)) return [];
  return trades.filter((trade) => {
    const ts = Date.parse(String(trade.closed_ts ?? ""));
    return Number.isFinite(ts) && ts >= since;
  });
}

function money(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * Qué pasa si la operación toca el stop o el objetivo.
 *
 * `open_risk` sale de la distancia entrada→stop por el valor del tick: es
 * dinero bruto. Decir «pierde 61.04» sin más se lee como neto, así que la
 * frase cierra aclarando que las dos cifras van antes de comisiones.
 */
export function positionOutlook(openRisk: number, rewardRatio: number | null): string {
  const stop = `Si toca el stop pierde ${money(openRisk)}.`;
  const target =
    rewardRatio !== null
      ? ` Si toca el objetivo, gana ${money(openRisk * rewardRatio)} (el objetivo está a ${
          rewardRatio >= 10 ? Math.round(rewardRatio) : rewardRatio.toFixed(1)
        } R).`
      : "";
  return `${stop}${target} Las dos cifras van antes de comisiones.`;
}

/** The price, breathing: it flashes green or red on every change. */
function LivePrice({ price }: { price: number }) {
  const previous = usePrevious(price);
  const direction = previous === undefined || previous === price ? "" : price > previous ? "up" : "down";
  return (
    <span key={price} className={`live-price ${direction ? `flash-${direction}` : ""}`.trim()}>
      {direction ? (direction === "up" ? "▲ " : "▼ ") : ""}
      {formatValue(price, "price")}
    </span>
  );
}

/**
 * The beginner view.
 *
 * One sentence that says what the bot is doing, three numbers that matter and
 * the last few results. Everything else (phases, ATR, gates, funnel) lives one
 * click away in Pro; here it would only be noise.
 */
export function SimpleDashboard() {
  const { snapshot } = useStore();
  const { setMode } = useUiMode();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [tradesLoaded, setTradesLoaded] = useState(false);
  const [tradesError, setTradesError] = useState(false);
  const [pulse, setPulse] = useState<Candle[]>([]);
  const [pulseLoaded, setPulseLoaded] = useState(false);
  const [pulseError, setPulseError] = useState(false);
  const liveBar = snapshot?.data.last_bar_ts ?? null;
  const now = useClock(15_000);

  useEffect(() => {
    let alive = true;
    api
      .trades({ limit: 200 })
      .then((rows) => {
        if (!alive) return;
        setTrades(rows as Trade[]);
        setTradesLoaded(true);
        setTradesError(false);
      })
      .catch(() => {
        if (alive) setTradesError(true);
      });
    return () => {
      alive = false;
    };
  }, [snapshot?.risk.daily_trades]);

  useEffect(() => {
    let alive = true;
    api
      .chart("5m", 120)
      .then((payload) => {
        if (!alive) return;
        setPulse(payload.candles as Candle[]);
        setPulseLoaded(true);
        setPulseError(false);
      })
      .catch(() => {
        if (alive) setPulseError(true);
      });
    return () => {
      alive = false;
    };
    // Solo cambia con una vela nueva: depender del snapshot entero pedía el
    // mismo gráfico una vez por mensaje del motor.
  }, [liveBar]);

  if (!snapshot) {
    return (
      <div className="page" aria-busy="true" aria-label="Cargando estado del motor">
        <div className="simple-hero skeleton-block" />
        <div className="simple-cards">
          {[0, 1, 2].map((index) => (
            <div key={index} className="simple-card skeleton-card">
              <span className="skeleton skeleton-line short" />
              <span className="skeleton skeleton-line tall" />
              <span className="skeleton skeleton-line" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const { risk, position, quotes, session, status } = snapshot;
  const dayTrades = tradesSince(trades, session.open_ts);
  // La lista pide 200: si vienen todas, puede haber más detrás y se dice.
  const truncated = trades.length >= 200;
  const stats = snapshot.stats as { equity?: { equity: number }[] };
  const equitySeries = (stats.equity ?? []).map((point) => point.equity);
  const capital = risk.equity - risk.daily_pnl || risk.equity;
  const dailyPct = capital ? (risk.daily_pnl / capital) * 100 : 0;
  const primarySymbol = snapshot.instruments.find((item) => item.role === "primary")?.symbol;
  const price = primarySymbol ? (quotes[primarySymbol]?.last ?? null) : null;

  // Un bot «trabajando» con un feed parado no está trabajando: la frescura de
  // la última vela se dice al lado del titular, no escondida en la consola.
  const fresh = marketFreshness(snapshot.data.last_bar_ts, now.getTime());
  const blocked = Boolean(risk.blocked || risk.block_reason);
  // «Bloqueado» por tener una posición abierta no es esperar: es gestionarla.
  // Con el stop y el objetivo puestos, el bot sigue trabajando en esa venta.
  const managing = status === "running" && Boolean(position) && risk.block_reason === "position_open";
  const state = status === "running" ? (blocked && !managing ? "waiting" : "working") : status;
  // «Trabajando» con el feed parado es una mentira piadosa: sin velas nuevas
  // no hay decisión posible, y el operador merece saberlo en el titular.
  const blind = status === "running" && (fresh.tone === "stale" || fresh.tone === "none");

  const headline = blind
    ? "ezur no está viendo el mercado"
    : state === "working"
      ? "ezur está trabajando solo"
      : state === "waiting"
        ? "ezur está esperando"
        : state === "paused"
          ? "ezur está en pausa"
          : state === "error"
            ? "ezur se ha detenido por un error"
            : "ezur está detenido";

  const explanation = blind
    ? `No llegan velas nuevas del mercado (${fresh.label}). Sin datos frescos no puede decidir; en cuanto vuelva el feed, sigue sola.`
    : state === "working"
      ? position
        ? `Tiene una ${sideLabel(position.side)} abierta en ${position.symbol}. No tienes que hacer nada.`
        : "Busca una entrada y entra sola cuando la encuentra. No tienes que hacer nada."
      : state === "waiting"
        ? "No puede abrir nuevas operaciones ahora mismo. Abajo te digo por qué, en palabras normales."
        : state === "paused"
          ? "Está en pausa: no mira el mercado. Pulsa Reanudar y sigue sola."
          : "Está detenida. Pulsa Reanudar para que vuelva a operar sola.";

  const reasonContext = {
    lossStreakCooldownMin: risk.limits.loss_streak_cooldown_min ?? 0,
  };
  // El servidor ya descarta un «posición abierta» que el propio snapshot
  // desmiente; aquí solo se traduce el motivo a palabras. Gestionando la
  // posición abierta no hay nada que explicar que no diga el titular.
  const reason = risk.block_reason && !managing ? plainReason(risk.block_reason, reasonContext) : null;
  const unlock = risk.block_reason && !managing ? unblockHint(risk.block_reason, reasonContext) : null;
  const topRejection = dominantRejection(snapshot.strategy.rejections);
  // «Gana más o menos lo mismo» solo es cierto si el objetivo está a 1 R; se
  // mide la distancia real y se calla cuando no hay objetivo declarado.
  const riskPerUnit = position ? Math.abs(position.entry_price - position.stop_price) : 0;
  const rewardPerUnit =
    position && position.target_price !== null
      ? Math.abs(position.target_price - position.entry_price)
      : null;
  const rewardRatio = riskPerUnit > 0 && rewardPerUnit !== null ? rewardPerUnit / riskPerUnit : null;
  const initialCapital = risk.limits.initial_capital ?? null;
  // El muro sale del capital inicial (lo que hace el motor); la equidad del
  // día solo es el último respaldo si el snapshot no trae ninguna de las dos.
  // Sin ninguna de las dos cifras no hay muro que enseñar: un 3 % de fábrica
  // sería una política que nadie ha configurado.
  const lossBase = initialCapital ?? capital;
  const dailyLossLimit =
    typeof risk.limits.daily_loss_limit === "number"
      ? risk.limits.daily_loss_limit
      : typeof risk.limits.max_daily_loss_pct === "number" && lossBase > 0
        ? (lossBase * risk.limits.max_daily_loss_pct) / 100
        : null;
  // Un día verde no borra un mes rojo: se dice cuánto lleva desde el arranque
  // contra el capital con el que empezó, no contra la equity de hoy.
  const sinceStart =
    initialCapital && initialCapital > 0 ? risk.equity - initialCapital : null;
  const sinceStartPct =
    sinceStart !== null && initialCapital ? (sinceStart / initialCapital) * 100 : null;
  const losingPct =
    dailyLossLimit !== null
      ? Math.min(100, Math.max(0, (-risk.daily_pnl / Math.max(1, dailyLossLimit)) * 100))
      : 0;

  return (
    <div className="page simple">
      <Onboarding />
      <section className={`simple-hero state-${blind ? "waiting" : state}`} data-simple-hero>
        <span className="hero-sheen" aria-hidden="true" />
        <span className="simple-led" aria-hidden="true" />
        <div>
          <span
            className={`fresh-chip fresh-${fresh.tone}`}
            title="Antigüedad de la última vela recibida del mercado"
            data-freshness={fresh.tone}
          >
            {fresh.label}
          </span>
          <h2>{headline}</h2>
          <p>{explanation}</p>
          {reason ? <p className="simple-reason">{reason}</p> : null}
          {unlock ? <p className="simple-unlock">{unlock}</p> : null}
          {state === "waiting" && topRejection ? (
            <p className="simple-hint" data-top-rejection>
              {reason && topRejection.code === risk.block_reason
                ? `Ha descartado ${topRejection.count} ${topRejection.count === 1 ? "señal" : "señales"} por este motivo desde que arrancó.`
                : `Lo que más le frena: ${plainReason(topRejection.code)} (${topRejection.count} ${
                    topRejection.count === 1 ? "vez" : "veces"
                  }).`}
            </p>
          ) : null}
        </div>
        <div className="simple-hero-actions">
          {status === "running" ? null : <DispatchButton action="start" label="Reanudar" />}
          <DispatchButton action="stop" label="Detener" />
        </div>
      </section>

      <div className="simple-cards">
        <article className="simple-card">
          <span className="simple-label">Hoy</span>
          <strong className={`simple-big ${risk.daily_pnl > 0 ? "tone-good" : risk.daily_pnl < 0 ? "tone-bad" : ""}`}>
            <AnimatedNumber value={risk.daily_pnl} format={(value) => `${value > 0 ? "+" : ""}${money(value)}`} />
          </strong>
          <span className="simple-foot">
            {dailyPct > 0 ? "+" : ""}
            {dailyPct.toFixed(2)} % del dinero de la cuenta
          </span>
          <div className="simple-bar" aria-hidden="true">
            <span style={{ width: `${losingPct}%` }} />
          </div>
          <span className="simple-hint">
            {dailyLossLimit !== null
              ? `Puede perder como mucho ${money(dailyLossLimit)} al día${
                  risk.limits.soft_brake_at
                    ? `; al llegar a ${money(risk.limits.soft_brake_at)} reduce el tamaño a la mitad`
                    : ""
                }.`
              : "El servidor no envió el límite de pérdida diaria: sin ese dato no se puede decir cuánto puede perder hoy."}
          </span>
        </article>

        <article className="simple-card">
          <span className="simple-label">Dinero en la cuenta</span>
          <strong className="simple-big">
            <AnimatedNumber value={risk.equity} format={money} />
          </strong>
          {equitySeries.length > 1 ? (
            <Sparkline values={equitySeries} label="Evolución del dinero" />
          ) : (
            <span className="simple-foot">empieza aquí</span>
          )}
          {sinceStart !== null ? (
            <span
              className={`simple-foot ${
                sinceStart > 0 ? "tone-good" : sinceStart < 0 ? "tone-bad" : ""
              }`}
              data-since-start
            >
              Desde el inicio: {sinceStart > 0 ? "+" : ""}
              {money(sinceStart)}
              {sinceStartPct !== null
                ? ` (${sinceStartPct > 0 ? "+" : ""}${sinceStartPct.toFixed(2)} %)`
                : ""}
            </span>
          ) : null}
          <span className="simple-hint">
            {position
              ? "Solo operaciones cerradas: la abierta aún no cambia esta cifra. "
              : ""}
            {risk.daily_trades} {risk.daily_trades === 1 ? "operación hoy" : "operaciones hoy"} ·{" "}
            {price !== null ? <>precio ahora <LivePrice price={price} /></> : "sin precio"}
          </span>
        </article>

        <article className="simple-card">
          <span className="simple-label">Operación abierta</span>
          {position ? (
            <>
              <strong className="simple-big">
                {sideLabel(position.side)} {position.units} u
              </strong>
              <span className={`simple-foot ${position.unrealized && position.unrealized > 0 ? "tone-good" : position.unrealized && position.unrealized < 0 ? "tone-bad" : ""}`}>
                {position.unrealized === null
                  ? `Entró a ${formatValue(position.entry_price, "price")}`
                  : position.unrealized === 0
                    ? "Ahora mismo va a la par: ni gana ni pierde."
                    : `${position.unrealized > 0 ? "ganando" : "perdiendo"} ${money(Math.abs(position.unrealized))} ahora mismo`}
              </span>
              <TradeRange
                side={position.side}
                entry={position.entry_price}
                stop={position.stop_price}
                target={position.target_price}
                price={price}
              />
              <span className="simple-hint">{positionOutlook(risk.open_risk, rewardRatio)}</span>
            </>
          ) : (
            <>
              <strong className="simple-big muted-big">ninguna</strong>
              <span className="simple-foot">No hay dinero en riesgo ahora mismo</span>
              <span className="simple-hint">Cuando abra una, aparecerá aquí con su stop y su objetivo.</span>
            </>
          )}
        </article>
      </div>

      <section className="card simple-pulse">
        <header className="card-header">
          <h3>El precio, en corto</h3>
          <span className="muted small">puntos de 5 min · toca la línea</span>
        </header>
        {pulseError && pulse.length === 0 ? (
          <p className="empty tone-warn">
            No se pudo cargar la línea de precio ahora mismo. Se reintenta sola en cada vela.
          </p>
        ) : (
          <MarketPulse candles={pulse} height={110} loading={!pulseLoaded && !pulseError} />
        )}
      </section>

      <section className="card simple-history">
        <header className="card-header">
          <h3>Últimas operaciones</h3>
          <span className="badge">{session.label}</span>
        </header>
        {tradesError ? (
          <p className="empty tone-warn">
            No se pudo cargar el historial de operaciones. Lo que ves arriba en «Hoy» sigue
            siendo el dato del motor.
          </p>
        ) : trades.length === 0 ? (
          <p className="empty">
            {tradesLoaded
              ? "Todavía no ha cerrado ninguna operación."
              : "Leyendo las últimas operaciones…"}
          </p>
        ) : (
          <ul className="simple-list">
            {trades.map((trade) => {
              const pnl = toFinite(trade.pnl_net);
              const measured = pnl !== null;
              const side =
                trade.side === null || trade.side === undefined
                  ? "—"
                  : sideLabel(String(trade.side));
              const reason =
                trade.exit_reason === null || trade.exit_reason === undefined || trade.exit_reason === ""
                  ? "—"
                  : EXIT_WORD[String(trade.exit_reason)] ?? String(trade.exit_reason);
              return (
                <li key={String(trade.id ?? `${trade.side}-${trade.closed_ts}-${trade.pnl_net}`)}>
                  <span className="simple-list-side">{side}</span>
                  <span className="simple-list-when">{formatDateTime(String(trade.closed_ts))}</span>
                  <span className="simple-list-why">{reason}</span>
                  <strong
                    className={
                      measured ? (pnl > 0 ? "tone-good" : pnl < 0 ? "tone-bad" : "") : "muted"
                    }
                  >
                    {pnl === null ? "—" : `${pnl > 0 ? "+" : ""}${money(pnl)}`}
                  </strong>
                </li>
              );
            })}
          </ul>
        )}
        {trades.length > 0 ? (
          dayTrades.length > 0 ? (
            <RecapLine recap={summarize(dayTrades)} />
          ) : (
            <p className="simple-recap" data-recap-today>
              Hoy todavía no ha cerrado ninguna operación.
            </p>
          )
        ) : null}
        {truncated ? (
          <p className="muted small">
            Aquí solo se ven las 200 más recientes; en Historial puedes acotar por fechas.
          </p>
        ) : null}
        <footer className="simple-footer">
          <button type="button" className="btn btn-ghost" onClick={() => setMode("advanced")}>
            Ver todo (modo avanzado)
          </button>
          <span className="muted small">
            Aquí no hay métricas ni R: solo si gana o pierde y por qué cerró. El bot arranca solo.
          </span>
        </footer>
      </section>
    </div>
  );
}

export function RecapLine({ recap }: { recap: Recap }) {
  const reason = recap.mainReason ? EXIT_WORD[recap.mainReason] ?? recap.mainReason : null;
  return (
    <p className="simple-recap" data-recap>
      Hoy: <b>{recap.total}</b> {recap.total === 1 ? "operación" : "operaciones"} ·{" "}
      {/* Un cero en verde se lee como ganancia y un cero en rojo como pérdida. */}
      <b className={recap.wins > 0 ? "tone-good" : undefined}>{recap.wins}</b> a favor ·{" "}
      <b className={recap.losses > 0 ? "tone-bad" : undefined}>{recap.losses}</b> en contra.
      {recap.unmeasured > 0 ? (
        <>
          {" "}
          <b>{recap.unmeasured}</b> sin resultado medido.
        </>
      ) : null}
      {recap.losses > 0 ? <> La peor: <b className="tone-bad">{money(recap.worst)}</b>.</> : null}
      {reason ? <> Lo más habitual: {reason}.</> : null}
      {recap.fees > 0 ? (
        <>
          {" "}
          Las comisiones se llevaron <b className="tone-cost">{money(recap.fees)}</b>; sin ellas el día
          iría en{" "}
          <b className={recap.gross > 0 ? "tone-good" : recap.gross < 0 ? "tone-bad" : ""}>
            {recap.gross > 0 ? "+" : ""}
            {money(recap.gross)}
          </b>
          .
        </>
      ) : null}
    </p>
  );
}
