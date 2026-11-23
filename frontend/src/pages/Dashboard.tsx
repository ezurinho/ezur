import { SymbolsTable } from "../components/SymbolsTable";
import { StrategyPanel } from "../components/StrategyPanel";
import { DispatchButton } from "../components/Controls";
import { Gauge } from "../components/Gauge";
import { Sparkline } from "../components/Sparkline";
import { useStore } from "../store";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Info } from "../components/Info";
import { formatDateTime, formatValue } from "../utils";

interface Kpi {
  label: string;
  value?: string;
  raw?: number;
  format?: (value: number) => string;
  tone?: "good" | "bad" | "neutral";
  foot?: string;
  series?: number[];
  info?: string;
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
  const pnlSeries = equitySeries.length > 1 ? equitySeries : [capital, risk.equity];

  const kpis: Kpi[] = [
    {
      label: "Equidad",
      raw: risk.equity,
      format: (value) => formatValue(value, "price", 2),
      foot: `${equitySeries.length} cierres`,
      series: equitySeries.length > 1 ? equitySeries : undefined,
      info: "Todo el dinero de la cuenta ahora mismo, incluido lo que está en operaciones abiertas.",
    },
    {
      label: "P&L diario",
      raw: risk.daily_pnl,
      format: (value) => formatValue(value, "price", 2),
      tone: risk.daily_pnl > 0 ? "good" : risk.daily_pnl < 0 ? "bad" : "neutral",
      foot: `${dailyPct >= 0 ? "+" : ""}${dailyPct.toFixed(2)} % del capital`,
      series: pnlSeries,
      info: "Lo ganado o perdido hoy, ya descontadas comisiones y deslizamiento.",
    },
    {
      label: "Riesgo abierto",
      raw: risk.open_risk,
      format: (value) => formatValue(value, "price", 2),
      tone: risk.open_risk > 0 ? "bad" : "neutral",
      foot: position ? `${position.symbol} · ${position.units} u` : "sin posición",
      info: "Dinero que perderías si el stop de la operación abierta salta ahora mismo.",
    },
    {
      label: "Operaciones hoy",
      raw: risk.daily_trades,
      format: (value) => String(Math.round(value)),
      foot: `PF ${(closed.profit_factor ?? 0).toFixed(2)} · exp ${(closed.expectancy_r ?? 0).toFixed(2)} R`,
      info: "PF es ganancias divididas por pérdidas; la esperanza es lo que ganas de media por operación, en múltiplos de R.",
    },
  ];

  const maxDailyLossPct = risk.limits.max_daily_loss_pct ?? 3;
  const maxDailyLossUsd = (capital * maxDailyLossPct) / 100;
  const lossUsedUsd = Math.max(0, -risk.daily_pnl);
  const maxTrades = risk.limits.max_trades_per_day ?? 3;

  return (
    <div className="page">
      <h2 className="page-title">
        Inicio
        <span className="muted small mono page-sub">{session.id}</span>
      </h2>

      <div className="kpi-grid">
        {kpis.map((kpi) => (
          <article key={kpi.label} className="kpi">
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
            {kpi.series ? <Sparkline values={kpi.series} label={`${kpi.label} reciente`} /> : null}
            {kpi.foot ? <span className="kpi-foot">{kpi.foot}</span> : null}
          </article>
        ))}
      </div>

      <div className="grid-two">
        <StrategyPanel strategy={strategy} />
        <section className="card">
          <header className="card-header">
            <h3>Sesión</h3>
            <span className={session.is_open ? "badge badge-running" : "badge badge-stopped"}>
              {session.phase}
            </span>
          </header>
          <dl className="kv-panel">
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
                {snapshot.data.quality} · {snapshot.data.staleness_ms} ms
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
            {position ? <span className={`badge ${position.side === "long" ? "badge-running" : "badge-error"}`}>{position.side}</span> : null}
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
            {risk.blocked
              ? `Bloqueado: ${risk.block_reason}${risk.block_count > 1 ? ` (${risk.block_count} señales)` : ""}`
              : "Operativa habilitada"}
          </p>
          <div className="gauge-row">
            <Gauge
              value={lossUsedUsd}
              max={Math.max(1, Math.round(maxDailyLossUsd))}
              unit="USD"
              label="pérdida diaria"
              warnAt={0.6}
              size={88}
            />
            <Gauge
              value={risk.daily_trades}
              max={maxTrades}
              unit="ops"
              label="operaciones"
              warnAt={0.66}
              size={88}
            />
          </div>
          <dl className="kv-panel">
            {Object.entries(risk.limits).map(([key, value]) => (
              <div key={key} className="kv-row">
                <dt>{key}</dt>
                <dd>{value}</dd>
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
