import { useEffect, useState } from "react";
import { DynamicTable, type Column } from "../components/DynamicTable";
import { api } from "../api";
import { formatDate, formatValue } from "../utils";

type Row = Record<string, unknown>;

const PERIODS = ["today", "week", "month", "30d", "all"] as const;

const COLUMNS: Column<Row>[] = [
  { key: "closed_ts", header: "Cierre", render: (row) => formatDate(String(row.closed_ts)) },
  { key: "symbol", header: "Instrumento" },
  { key: "side", header: "Dirección" },
  { key: "units", header: "Unidades" },
  { key: "entry_price", header: "Entrada", render: (row) => formatValue(Number(row.entry_price), "price") },
  { key: "exit_price", header: "Salida", render: (row) => formatValue(Number(row.exit_price), "price") },
  { key: "pnl_net", header: "P&L neto", render: (row) => formatValue(Number(row.pnl_net), "price") },
  { key: "r_multiple", header: "R", render: (row) => formatValue(Number(row.r_multiple), "ratio") },
  { key: "exit_reason", header: "Motivo" },
  { key: "mode", header: "Modo" },
];

export function HistoryPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .trades(200)
      .then((data) => {
        if (!cancelled) setRows(data as unknown as Row[]);
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  const filtered = rows.filter((row) => {
    if (period === "all") return true;
    const stamp = Date.parse(String(row.closed_ts));
    if (Number.isNaN(stamp)) return false;
    const days = { today: 1, week: 7, month: 30, "30d": 30 }[period] ?? 99999;
    return Date.now() - stamp <= days * 86_400_000;
  });

  return (
    <div className="page">
      <h2>Historial</h2>
      <div className="button-row">
        {PERIODS.map((value) => (
          <button
            key={value}
            type="button"
            className={value === period ? "btn active" : "btn"}
            onClick={() => setPeriod(value)}
          >
            {value}
          </button>
        ))}
        <a className="btn" href="/api/trades/export.csv" download>
          Exportar CSV
        </a>
      </div>
      {error ? <p className="tone-bad">{error}</p> : null}
      <section className="card">
        <DynamicTable
          rows={filtered}
          columns={COLUMNS}
          emptyLabel="Sin operaciones registradas"
          rowKey={(row) => String(row.id ?? Math.random())}
        />
      </section>
    </div>
  );
}
