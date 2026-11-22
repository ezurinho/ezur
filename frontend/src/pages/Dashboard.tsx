import { SymbolsTable } from "../components/SymbolsTable";
import { StrategyPanel } from "../components/StrategyPanel";
import { DispatchButton } from "../components/Controls";
import { useStore } from "../store";
import { formatValue } from "../utils";

export function DashboardPage() {
  const { snapshot } = useStore();
  if (!snapshot) return <p className="empty">Conectando…</p>;

  const { risk, strategy, instruments, quotes, position, session } = snapshot;
  const kpis = [
    { label: "Equidad", value: formatValue(risk.equity, "price", 2) },
    { label: "P&L diario", value: formatValue(risk.daily_pnl, "price", 2) },
    { label: "Riesgo abierto", value: formatValue(risk.open_risk, "price", 2) },
    { label: "Operaciones hoy", value: String(risk.daily_trades) },
  ];

  return (
    <div className="page">
      <h2>Inicio</h2>
      <div className="kpi-grid">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="card kpi">
            <span className="muted small">{kpi.label}</span>
            <strong>{kpi.value}</strong>
          </div>
        ))}
      </div>

      <div className="grid-two">
        <StrategyPanel strategy={strategy} />
        <section className="card">
          <header className="card-header">
            <h3>Sesión</h3>
          </header>
          <p className="muted small">
            {session.label} · {session.phase} · {snapshot.mode}
          </p>
          <p className="muted small">
            Proveedor {snapshot.data.provider} · calidad {snapshot.data.quality} ·{" "}
            {snapshot.data.bars_available} velas
          </p>
          <SymbolsTable instruments={instruments} quotes={quotes} />
        </section>
      </div>

      <div className="grid-two">
        <section className="card">
          <header className="card-header">
            <h3>Posición</h3>
          </header>
          {position ? (
            <dl className="kv-panel">
              <div className="kv-row">
                <dt>Instrumento</dt>
                <dd>{position.symbol}</dd>
              </div>
              <div className="kv-row">
                <dt>Dirección</dt>
                <dd>{position.side}</dd>
              </div>
              <div className="kv-row">
                <dt>Unidades</dt>
                <dd>{position.units}</dd>
              </div>
              <div className="kv-row">
                <dt>Entrada</dt>
                <dd>{position.entry_price}</dd>
              </div>
              <div className="kv-row">
                <dt>Stop</dt>
                <dd>{position.stop_price}</dd>
              </div>
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
          </header>
          <p className={risk.blocked ? "tone-bad" : "tone-good"}>
            {risk.blocked
              ? `Bloqueado: ${risk.block_reason}${risk.block_count > 1 ? ` (${risk.block_count} señales)` : ""}`
              : "Operativa habilitada"}
          </p>
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
