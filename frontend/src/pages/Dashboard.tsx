import { SymbolsTable } from "../components/SymbolsTable";
import { StrategyPanel } from "../components/StrategyPanel";
import { DispatchButton } from "../components/Controls";
import { Gauge } from "../components/Gauge";
import { BlockedBanner } from "../components/BlockedBanner";
import { PromotionCard } from "../components/PromotionCard";
import { Review2025Card } from "../components/Review2025Card";
import { Reasoning } from "../components/Reasoning";
import { Sparkline } from "../components/Sparkline";
import { useStore } from "../store";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Info } from "../components/Info";
import {
  ageLabel,
  formatDateTime,
  formatValue,
  limitEntries,
  phaseLabel,
  qualityLabel,
  sessionWindow,
  sideLabel,
} from "../utils";
import { plainReason } from "../reasons";

interface Kpi {
  label: string;
  value?: string;
  raw?: number;
  format?: (value: number) => string;
  tone?: "good" | "bad" | "neutral";
  foot?: string;
  series?: number[];
  seriesLabel?: string;
  info?: string;
}

/**
 * La equidad del motor es realizada: suma el P&L al cerrar, no marca a mercado.
 * El pie lo dice para que el número no se lea como saldo con la posición viva.
 */
export function equityFoot(closures: number, hasPosition: boolean): string {
  const count = `${closures} ${closures === 1 ? "cierre" : "cierres"}`;
  return hasPosition ? `${count} · sin la abierta` : `${count} · solo cerradas`;
}

/**
 * La línea de histórico del KPI «Operaciones hoy».
 *
 * El PF y la esperanza son de todo el historial. Un cierre sin medición no es
 * un cero: si falta el dato se dice «—», y un PF sin pérdidas se dice infinito
 * en vez de 1,00, que se leería como empate técnico.
 */
export function historyFoot(closed: Record<string, number | null | undefined>): string {
  const trades = closed.trades;
  // Sin recuento no se sabe si hay cero cierres o ninguno medido todavía.
  if (typeof trades !== "number") return "Historial sin leer: no hay PF ni esperanza que enseñar";
  if (trades <= 0) return "Sin cierres todavía: no hay PF ni esperanza que medir";
  const wins = closed.wins ?? 0;
  const losses = closed.losses ?? 0;
  const pfValue = closed.profit_factor;
  const pf =
    typeof pfValue === "number"
      ? losses === 0 && wins > 0
        ? "∞"
        : pfValue.toFixed(2)
      : "—";
  const expectancy =
    typeof closed.expectancy_r === "number" ? `${closed.expectancy_r.toFixed(2)} R` : "—";
  return `Histórico (${trades} cierres): PF ${pf} · ${expectancy}`;
}

/**
 * La curva de equidad es por cierre: sus diferencias son el resultado de cada
 * operación. Pintar la equidad bajo «P&L diario» sería otra cosa disfrazada.
 * Con menos de dos cierres no hay diferencias que enseñar.
 */
export function pnlByClose(equity: number[]): number[] | undefined {
  if (equity.length < 2) return undefined;
  return equity.slice(1).map((value, index) => value - equity[index]);
}

export function DashboardPage() {
  const { snapshot } = useStore();
  if (!snapshot) return <DashboardSkeleton />;

  const { risk, strategy, instruments, quotes, position, session } = snapshot;
  const stats = snapshot.stats as {
    equity?: { equity: number }[];
    closed?: Record<string, number>;
  };
  const equitySeries = (stats.equity ?? []).map((point) => point.equity);
  const closed = stats.closed ?? {};

  const capital = risk.equity - risk.daily_pnl || risk.equity;
  const dailyPct = capital ? (risk.daily_pnl / capital) * 100 : 0;
  const pnlSeries = pnlByClose(equitySeries);

  const kpis: Kpi[] = [
    {
      label: "Equidad",
      raw: risk.equity,
      format: (value) => formatValue(value, "price", 2),
      foot: equityFoot(equitySeries.length, Boolean(position)),
      series: equitySeries.length > 1 ? equitySeries : undefined,
      info: "Capital inicial más el resultado neto de las operaciones cerradas. La posición abierta no entra hasta que se cierra: el motor no calcula su resultado flotante.",
    },
    {
      label: "P&L diario",
      raw: risk.daily_pnl,
      format: (value) => formatValue(value, "price", 2),
      tone: risk.daily_pnl > 0 ? "good" : risk.daily_pnl < 0 ? "bad" : "neutral",
      foot: `${dailyPct > 0 ? "+" : ""}${dailyPct.toFixed(2)} % del capital`,
      series: pnlSeries,
      seriesLabel: "resultado de los últimos cierres",
      info: "Lo ganado o perdido hoy, ya descontadas comisiones y deslizamiento.",
    },
    {
      label: "Riesgo abierto",
      raw: risk.open_risk,
      format: (value) => formatValue(value, "price", 2),
      tone: risk.open_risk > 0 ? "bad" : "neutral",
      foot: position ? `${position.symbol} · ${position.units} u` : "sin posición",
      info: "Dinero que perderías si el stop de la operación abierta salta ahora mismo, antes de comisiones.",
    },
    {
      label: "Operaciones hoy",
      raw: risk.daily_trades,
      format: (value) => String(Math.round(value)),
      // El PF y la esperanza son de todo el historial, no del día: decirlo
      // aquí evita leerlos como si describieran las operaciones de hoy.
      foot: historyFoot(closed),
      info: "PF es ganancias divididas por pérdidas; la esperanza es lo que ganas de media por operación, en múltiplos de R.",
    },
  ];

  // El muro real lo aplica el motor sobre el capital inicial; con la equidad
  // del día saldría otro número. Esa equity solo queda como último respaldo.
  // Sin límite ni porcentaje en el snapshot no hay muro: no se inventa un 3 %.
  const initialCapital = risk.limits.initial_capital ?? null;
  const lossBase = initialCapital ?? capital;
  const maxDailyLossUsd =
    typeof risk.limits.daily_loss_limit === "number"
      ? risk.limits.daily_loss_limit
      : typeof risk.limits.max_daily_loss_pct === "number" && lossBase > 0
        ? (lossBase * risk.limits.max_daily_loss_pct) / 100
        : null;
  const lossUsedUsd = Math.max(0, -risk.daily_pnl);
  const maxTrades =
    typeof risk.limits.max_trades_per_day === "number" ? risk.limits.max_trades_per_day : null;

  return (
    <div className="page">
      <h2 className="page-title">
        Inicio
        <span className="muted small mono page-sub">{session.id}</span>
      </h2>

      <BlockedBanner snapshot={snapshot} />

      <Reasoning snapshot={snapshot} />

      <div className="kpi-grid">
        {kpis.map((kpi, index) => (
          <article key={kpi.label} className="kpi">
            <span className="kpi-index" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="kpi-label">
              {kpi.label}
              {kpi.info ? <Info term={kpi.label} text={kpi.info} /> : null}
            </span>
            <strong className={`kpi-value ${kpi.tone ? `tone-${kpi.tone}` : ""}`}>
              {kpi.raw !== undefined ? (
                <AnimatedNumber value={kpi.raw} format={kpi.format} />
              ) : (
                kpi.value
              )}
            </strong>
            {kpi.series ? (
              <Sparkline values={kpi.series} label={kpi.seriesLabel ?? `${kpi.label} reciente`} />
            ) : null}
            {kpi.foot ? <span className="kpi-foot">{kpi.foot}</span> : null}
          </article>
        ))}
      </div>

      <PromotionCard promotion={snapshot.promotion ?? null} />

      <Review2025Card />

      <div className="grid-two">
        <StrategyPanel strategy={strategy} />
        <section className="card">
          <header className="card-header">
            <h3>Sesión</h3>
            <span className={session.is_open ? "badge badge-running" : "badge badge-stopped"}>
              {phaseLabel(session.phase)}
            </span>
          </header>
          <dl className="kv-panel">
            <div className="kv-row">
              <dt>Horario</dt>
              <dd>
                {(() => {
                  const window = sessionWindow(session.open_ts, session.close_ts);
                  return window ? `${window.utc} UTC · ${window.local} tu hora` : "sin horario";
                })()}
              </dd>
            </div>
            <div className="kv-row">
              <dt>Modo</dt>
              <dd>{snapshot.mode}</dd>
            </div>
            <div className="kv-row">
              <dt>Proveedor</dt>
              <dd>{snapshot.data.provider}</dd>
            </div>
            <div className="kv-row">
              <dt>Calidad</dt>
              <dd className={snapshot.data.quality === "ok" ? "tone-good" : "tone-warn"}>
                {qualityLabel(snapshot.data.quality)} · último dato {ageLabel(snapshot.data.staleness_ms)}
              </dd>
            </div>
            <div className="kv-row">
              <dt>Velas</dt>
              <dd>{snapshot.data.bars_available}</dd>
            </div>
            <div className="kv-row">
              <dt>Última vela</dt>
              <dd>{formatDateTime(snapshot.data.last_bar_ts)}</dd>
            </div>
          </dl>
          <SymbolsTable instruments={instruments} quotes={quotes} />
        </section>
      </div>

      <div className="grid-two">
        <section className="card">
          <header className="card-header">
            <h3>Posición</h3>
            {position ? <span className={`badge ${position.side === "long" ? "badge-running" : "badge-error"}`}>{sideLabel(position.side)}</span> : null}
          </header>
          {position ? (
            <dl className="kv-panel">
              <div className="kv-row">
                <dt>Instrumento</dt>
                <dd>{position.symbol}</dd>
              </div>
              <div className="kv-row">
                <dt>Unidades</dt>
                <dd>{position.units}</dd>
              </div>
              <div className="kv-row">
                <dt>Entrada</dt>
                <dd>{formatValue(position.entry_price, "price", 2)}</dd>
              </div>
              <div className="kv-row">
                <dt>Stop</dt>
                <dd className="tone-bad">{formatValue(position.stop_price, "price", 2)}</dd>
              </div>
              {position.target_price ? (
                <div className="kv-row">
                  <dt>Objetivo</dt>
                  <dd className="tone-good">{formatValue(position.target_price, "price", 2)}</dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <p className="empty">Sin posición abierta</p>
          )}
          <div className="button-row">
            <DispatchButton action="start" label="Iniciar" />
            <DispatchButton action="pause" label="Pausar" />
            <DispatchButton action="stop" label="Detener" />
          </div>
        </section>

        <section className="card">
          <header className="card-header">
            <h3>Riesgo</h3>
            <span className={risk.blocked ? "badge badge-error" : "badge badge-running"}>
              {risk.blocked ? "bloqueado" : "habilitado"}
            </span>
          </header>
          <p className={risk.blocked ? "tone-bad small" : "tone-good small"}>
            {/* El recuento de rechazos ya lo fecha el aviso de arriba: aquí
                solo va el motivo, una vez y en palabras. */}
            {risk.blocked
              ? plainReason(risk.block_reason, {
                  lossStreakCooldownMin: risk.limits.loss_streak_cooldown_min ?? 0,
                })
              : "Operativa habilitada"}
          </p>
          <div className="gauge-row">
            {maxDailyLossUsd !== null ? (
              <Gauge
                value={lossUsedUsd}
                max={Math.max(1, Math.round(maxDailyLossUsd))}
                unit="USD"
                label="pérdida diaria"
                warnAt={0.6}
                size={88}
              />
            ) : (
              <p className="muted small">Sin muro de pérdida diaria en el snapshot.</p>
            )}
            {maxTrades !== null ? (
              <Gauge
                value={risk.daily_trades}
                max={maxTrades}
                unit="ops"
                label="operaciones"
                warnAt={0.66}
                size={88}
              />
            ) : (
              <p className="muted small">Sin tope de operaciones en el snapshot.</p>
            )}
          </div>
          <dl className="kv-panel">
            {limitEntries(risk.limits).map((row) => (
              <div key={row.key} className="kv-row">
                <dt>{row.label}</dt>
                <dd className="mono">{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}

/** Una pantalla de carga que no finge datos: dice «cargando» con forma. */
function DashboardSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Cargando estado del motor">
      <div className="skeleton skeleton-title" />

      <div className="kpi-grid">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="kpi skeleton-card">
            <span className="skeleton skeleton-line short" />
            <span className="skeleton skeleton-line tall" />
            <span className="skeleton skeleton-line" />
          </div>
        ))}
      </div>
      <div className="grid-two">
        {[0, 1].map((index) => (
          <div key={index} className="card skeleton-block" />
        ))}
      </div>
    </div>
  );
}
