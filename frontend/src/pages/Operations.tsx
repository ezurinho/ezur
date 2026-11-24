import { useStore } from "../store";
import { DispatchButton } from "../components/Controls";
import { DynamicTable, type Column } from "../components/DynamicTable";
import { formatDateTime, formatValue, sideLabel, toFinite } from "../utils";

type Row = Record<string, unknown>;

export function OperationsPage() {
  const { snapshot } = useStore();
  if (!snapshot) return <p className="empty">Conectando…</p>;

  const lossLimit = snapshot.risk.limits.daily_loss_limit;
  const softBrakeAt = snapshot.risk.limits.soft_brake_at;
  const openRisk = snapshot.risk.open_risk;
  const marginLeft =
    typeof lossLimit === "number" ? Math.max(0, snapshot.risk.daily_pnl + lossLimit) : null;
  // El margen de arriba cuenta lo ya cerrado. Si la abierta salta el stop, el
  // motor suma esa pérdida hoy mismo: callarlo anunciaría un colchón que el
  // siguiente cierre se come de golpe.
  const marginAfterStop =
    marginLeft !== null && typeof openRisk === "number" ? marginLeft - openRisk : null;

  const orderColumns: Column<Row>[] = [
    { key: "id", header: "ID" },
    { key: "symbol", header: "Instrumento" },
    {
      key: "side",
      header: "Dirección",
      render: (row) =>
        row.side === null || row.side === undefined ? "—" : sideLabel(String(row.side)),
    },
    { key: "units", header: "Unidades" },
    { key: "kind", header: "Tipo" },
    {
      key: "price",
      header: "Precio",
      // Una orden a mercado puede no traer precio: `Number(null)` daría 0.00.
      render: (row) => formatValue(toFinite(row.price), "price"),
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
              <dd>{sideLabel(snapshot.position.side)}</dd>
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
              <dd>{formatDateTime(snapshot.position.opened_ts)}</dd>
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
              {typeof snapshot.day_stats.trades === "number" ? snapshot.day_stats.trades : "—"} /{" "}
              {snapshot.risk.limits.max_trades_per_day ?? "—"}
            </dd>
          </div>
          <div className="kv-row">
            <dt>P&L del día</dt>
            <dd
              className={
                snapshot.risk.daily_pnl > 0
                  ? "tone-good"
                  : snapshot.risk.daily_pnl < 0
                    ? "tone-bad"
                    : ""
              }
            >
              {formatValue(snapshot.risk.daily_pnl, "price")}
            </dd>
          </div>
          <div className="kv-row">
            <dt>Riesgo abierto</dt>
            <dd>{formatValue(snapshot.risk.open_risk, "price")}</dd>
          </div>
          {typeof lossLimit === "number" && marginLeft !== null ? (
            <>
              <div className="kv-row">
                <dt>Pérdida máxima del día</dt>
                {/* El snapshot manda la magnitud (750, no −750): el signo aquí
                    sería otra convención y la misma cifra saldría negada. */}
                <dd>{formatValue(lossLimit, "price")}</dd>
              </div>
              <div className="kv-row">
                <dt>Margen antes de dejar de abrir</dt>
                <dd className={marginLeft <= 0 ? "tone-bad" : ""}>
                  {formatValue(marginLeft, "price")}
                </dd>
              </div>
              {snapshot.position && marginAfterStop !== null && openRisk > 0 ? (
                <div className="kv-row">
                  <dt>Margen si salta el stop abierto</dt>
                  <dd className={marginAfterStop <= 0 ? "tone-bad" : ""}>
                    {formatValue(marginAfterStop, "price")}
                  </dd>
                </div>
              ) : null}
              {typeof softBrakeAt === "number" ? (
                <div className="kv-row">
                  <dt>Freno suave (mitad de tamaño)</dt>
                  <dd>{formatValue(softBrakeAt, "price")}</dd>
                </div>
              ) : null}
            </>
          ) : null}
        </dl>
        {snapshot.position && marginAfterStop !== null && openRisk > 0 ? (
          <p className="muted small">
            El riesgo abierto mide la pérdida si el stop se ejecuta; no incluye comisiones
            ni deslizamiento, así que el margen real puede quedar algo por debajo.
          </p>
        ) : null}
      </section>
    </div>
  );
}
