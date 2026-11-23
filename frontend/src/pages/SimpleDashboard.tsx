import { useEffect, useState } from "react";
import { api } from "../api";
import { DispatchButton } from "../components/Controls";
import { Sparkline } from "../components/Sparkline";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { MarketPulse } from "../components/MarketPulse";
import { Onboarding } from "../components/Onboarding";
import type { Candle } from "../types";
import { useUiMode } from "../mode";
import { useStore } from "../store";
import { formatDateTime, formatValue } from "../utils";

type Trade = Record<string, unknown>;

const SIDE_WORD: Record<string, string> = { long: "compra", short: "venta" };

const EXIT_WORD: Record<string, string> = {
  stop: "saltó el stop",
  target: "llegó al objetivo",
  manual: "cerrada a mano",
  session_close: "cerrada al final del día",
  cancel: "cancelada",
};

function money(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
  const [pulse, setPulse] = useState<Candle[]>([]);
  const liveBar = snapshot?.data.last_bar_ts ?? null;

  useEffect(() => {
    let alive = true;
    api
      .trades({ limit: 4 })
      .then((rows) => {
        if (alive) setTrades(rows as Trade[]);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [snapshot?.risk.daily_trades]);

  useEffect(() => {
    if (!snapshot) return;
    let alive = true;
    api
      .chart("5m", 120)
      .then((payload) => {
        if (alive) setPulse(payload.candles as Candle[]);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [liveBar, snapshot]);

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
  const stats = snapshot.stats as { equity?: { equity: number }[] };
  const equitySeries = (stats.equity ?? []).map((point) => point.equity);
  const capital = risk.equity - risk.daily_pnl || risk.equity;
  const dailyPct = capital ? (risk.daily_pnl / capital) * 100 : 0;
  const price = quotes[Object.keys(quotes)[0] ?? ""]?.last ?? null;

  const blocked = Boolean(risk.blocked || risk.block_reason);
  const state = status === "running" ? (blocked ? "waiting" : "working") : status;

  const headline =
    state === "working"
      ? "ezur está trabajando solo"
      : state === "waiting"
        ? "ezur está esperando"
        : state === "paused"
          ? "ezur está en pausa"
          : state === "error"
            ? "ezur se ha detenido por un error"
            : "ezur está detenido";

  const explanation =
    state === "working"
      ? position
        ? `Tiene una ${SIDE_WORD[position.side] ?? position.side} abierta en ${position.symbol}. No tienes que hacer nada.`
        : "Busca una entrada y entra sola cuando la encuentra. No tienes que hacer nada."
      : state === "waiting"
        ? "No puede abrir nuevas operaciones ahora mismo. Abajo te digo por qué, en palabras normales."
        : state === "paused"
          ? "Está en pausa: no mira el mercado. Pulsa Reanudar y sigue sola."
          : "Está detenida. Pulsa Reanudar para que vuelva a operar sola.";

  const reason = risk.block_reason ? plainReason(risk.block_reason) : null;
  const losingPct = Math.min(
    100,
    Math.max(0, (-risk.daily_pnl / Math.max(1, (capital * (risk.limits.max_daily_loss_pct ?? 3)) / 100)) * 100),
  );

  return (
    <div className="page simple">
      <Onboarding />
      <section className={`simple-hero state-${state}`} data-simple-hero>
        <span className="simple-led" aria-hidden="true" />
        <div>
          <h2>{headline}</h2>
          <p>{explanation}</p>
          {reason ? <p className="simple-reason">{reason}</p> : null}
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
            {dailyPct >= 0 ? "+" : ""}
            {dailyPct.toFixed(2)} % del dinero de la cuenta
          </span>
          <div className="simple-bar" aria-hidden="true">
            <span style={{ width: `${losingPct}%` }} />
          </div>
          <span className="simple-hint">
            Puede perder como mucho {money((capital * (risk.limits.max_daily_loss_pct ?? 3)) / 100)} al día
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
          <span className="simple-hint">
            {risk.daily_trades} {risk.daily_trades === 1 ? "operación hoy" : "operaciones hoy"} ·{" "}
            {price !== null ? `precio ahora ${formatValue(price, "price")}` : "sin precio"}
          </span>
        </article>

        <article className="simple-card">
          <span className="simple-label">Operación abierta</span>
          {position ? (
            <>
              <strong className="simple-big">
                {SIDE_WORD[position.side] ?? position.side} {position.units} u
              </strong>
              <span className="simple-foot">
                Entró a {formatValue(position.entry_price, "price")} en {position.symbol}
              </span>
              <span className="simple-hint">
                Si toca el stop pierde {money(risk.open_risk)}. Si toca el objetivo, gana más o menos lo mismo.
              </span>
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
        <MarketPulse candles={pulse} height={110} />
      </section>

      <section className="card simple-history">
        <header className="card-header">
          <h3>Últimas operaciones</h3>
          <span className="badge">{session.label}</span>
        </header>
        {trades.length === 0 ? (
          <p className="empty">Todavía no ha cerrado ninguna operación.</p>
        ) : (
          <ul className="simple-list">
            {trades.map((trade) => {
              const pnl = Number(trade.pnl_net ?? 0);
              return (
                <li key={String(trade.id ?? Math.random())}>
                  <span className="simple-list-side">{SIDE_WORD[String(trade.side)] ?? String(trade.side)}</span>
                  <span className="simple-list-when">{formatDateTime(String(trade.closed_ts))}</span>
                  <span className="simple-list-why">
                    {EXIT_WORD[String(trade.exit_reason)] ?? String(trade.exit_reason)}
                  </span>
                  <strong className={pnl > 0 ? "tone-good" : pnl < 0 ? "tone-bad" : ""}>
                    {pnl > 0 ? "+" : ""}
                    {money(pnl)}
                  </strong>
                </li>
              );
            })}
          </ul>
        )}
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

function plainReason(code: string): string {
  const table: Record<string, string> = {
    position_open: "Ya tiene una operación abierta. Primero tiene que cerrarse.",
    max_trades_reached: "Ya hizo las operaciones máximas de hoy. Mañana vuelve a empezar.",
    daily_loss_limit: "Hoy ya perdió el máximo permitido. El bot se protege y para.",
    max_drawdown_reached: "La cuenta cayó demasiado desde su punto más alto. Se protege.",
    consecutive_losses: "Falló varias veces seguidas. Espera un poco antes de volver.",
    cooldown_active: "Acaba de cerrar una operación; espera un momento antes de abrir otra.",
    emergency_active: "La parada de emergencia está activada. Desactívala para seguir.",
    order_pending: "Hay una orden en camino; espera a que se ejecute.",
    outside_window: "Está fuera del horario en el que se permite operar.",
    no_price: "Todavía no tiene precio de referencia del mercado.",
  };
  return table[code] ?? `Motivo técnico: ${code}`;
}
