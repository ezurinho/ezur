import { useStore } from "../store";
import { DispatchButton } from "../components/Controls";
import { DynamicTable, type Column } from "../components/DynamicTable";
import { formatClock, formatValue } from "../utils";

type Row = Record<string, unknown>;

export function OperationsPage() {
  const { snapshot } = useStore();
  if (!snapshot) return <p className="empty">Conectando…</p>;

  const orderColumns: Column<Row>[] = [
    { key: "id", header: "ID" },
    { key: "symbol", header: "Instrumento" },
    { key: "side", header: "Dirección" },
    { key: "units", header: "Unidades" },
    { key: "kind", header: "Tipo" },
    {
      key: "price",
      header: "Precio",
      render: (row) => formatValue(Number(row.price), "price"),
    },
    { key: "status", header: "Estado" },
    {
      key: "stop_price",
      header: "Stop",
      render: (row) =>
        row.stop_price === null ? "—" : formatValue(Number(row.stop_price), "price"),
    },
    {
      key: "target_price",
      header: "Objetivo",
      render: (row) =>
        row.target_price === null ? "—" : formatValue(Number(row.target_price), "price"),
    },
  ];

  return (
    <div className="page">
      <h2>Operaciones</h2>
      <div className="button-row">
        <DispatchButton action="close" label="Cerrar posición" />
        <DispatchButton action="cancel" label="Cancelar órdenes" />
        <DispatchButton action="emergency" label="Emergencia" />
      </div>

      <section className="card">
        <header className="card-header">
          <h3>Posición abierta</h3>
        </header>
        {snapshot.position ? (
          <dl className="kv-panel">
            <div className="kv-row">
              <dt>Instrumento</dt>
              <dd>{snapshot.position.symbol}</dd>
            </div>
            <div className="kv-row">
              <dt>Dirección</dt>
              <dd>{snapshot.position.side}</dd>
            </div>
            <div className="kv-row">
              <dt>Unidades</dt>
              <dd>{snapshot.position.units}</dd>
            </div>
            <div className="kv-row">
              <dt>Entrada</dt>
              <dd>{formatValue(snapshot.position.entry_price, "price")}</dd>
            </div>
            <div className="kv-row">
              <dt>Stop</dt>
              <dd>{formatValue(snapshot.position.stop_price, "price")}</dd>
            </div>
            <div className="kv-row">
              <dt>Objetivo</dt>
              <dd>{formatValue(snapshot.position.target_price, "price")}</dd>
            </div>
            <div className="kv-row">
              <dt>Apertura</dt>
              <dd>{formatClock(snapshot.position.opened_ts)}</dd>
            </div>
          </dl>
        ) : (
          <p className="empty">Sin posición</p>
        )}
      </section>

      <section className="card">
        <header className="card-header">
          <h3>Órdenes</h3>
        </header>
        <DynamicTable
          rows={snapshot.orders as unknown as Row[]}
          columns={orderColumns}
          emptyLabel="Sin órdenes"
          rowKey={(row) => String(row.id)}
        />
      </section>

      <section className="card">
        <header className="card-header">
          <h3>Límites de sesión</h3>
        </header>
        <dl className="kv-panel">
          <div className="kv-row">
            <dt>Operaciones del día</dt>
            <dd>
              {String(snapshot.day_stats.trades ?? 0)} /{" "}
              {snapshot.risk.limits.max_trades_per_day ?? "—"}
            </dd>
          </div>
          <div className="kv-row">
            <dt>P&L del día</dt>
            <dd>{formatValue(snapshot.risk.daily_pnl, "price")}</dd>
          </div>
          <div className="kv-row">
            <dt>Riesgo abierto</dt>
            <dd>{formatValue(snapshot.risk.open_risk, "price")}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
