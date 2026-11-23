import { useEffect, useState } from "react";
import { DynamicTable, type Column } from "../components/DynamicTable";
import { api } from "../api";
import { useUiMode } from "../mode";
import { formatDateTime, formatValue } from "../utils";

type Row = Record<string, unknown>;

const PERIODS = ["today", "week", "month", "30d", "all"] as const;
type Period = (typeof PERIODS)[number];

const PERIOD_WORDS: Record<Period, string> = {
  today: "hoy",
  week: "7 días",
  month: "mes",
  "30d": "30 días",
  all: "todo",
};

const SIDE_WORD: Record<string, string> = { long: "compra", short: "venta" };
const EXIT_WORD: Record<string, string> = {
  stop: "saltó el stop",
  target: "objetivo",
  manual: "a mano",
  session_close: "fin del día",
  cancel: "cancelada",
};

/** Beginner columns: when, what, how much. No R, no prices, no diagnostics. */
export const SIMPLE_COLUMNS: Column<Row>[] = [
  { key: "closed_ts", header: "Cuándo", render: (row) => formatDateTime(String(row.closed_ts)) },
  {
    key: "side",
    header: "Qué hizo",
    render: (row) => SIDE_WORD[String(row.side)] ?? String(row.side),
  },
  {
    key: "pnl_net",
    header: "Resultado",
    render: (row) => {
      const value = Number(row.pnl_net ?? 0);
      return (
        <span className={value > 0 ? "tone-good" : value < 0 ? "tone-bad" : ""}>
          {value > 0 ? "+" : ""}
          {formatValue(value, "price")}
        </span>
      );
    },
  },
  {
    key: "exit_reason",
    header: "Por qué cerró",
    render: (row) => EXIT_WORD[String(row.exit_reason)] ?? String(row.exit_reason),
  },
];

/** Server-side range: a browser-side filter over 200 rows is a lie by omission. */
function periodStart(period: Period): string | undefined {
  if (period === "all") return undefined;
  const now = new Date();
  if (period === "today") {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return start.toISOString();
  }
  const days = period === "week" ? 7 : 30;
  return new Date(now.getTime() - days * 86_400_000).toISOString();
}

const COLUMNS: Column<Row>[] = [
  { key: "closed_ts", header: "Cierre", render: (row) => formatDateTime(String(row.closed_ts)) },
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
  const { isSimple } = useUiMode();
  const [rows, setRows] = useState<Row[]>([]);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("all");
  const [error, setError] = useState<string | null>(null);

  const start = periodStart(period);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .trades({ limit: 200, start })
      .then((data) => {
        if (!cancelled) setRows(data as unknown as Row[]);
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [start]);

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
            {isSimple ? PERIOD_WORDS[value] : value}
          </button>
        ))}
        {isSimple ? null : (
          <a className="btn" href={api.tradesCsvUrl({ start })} download>
            Exportar CSV
          </a>
        )}
      </div>
      {isSimple ? (
        <p className="simple-lead">
          Cada línea es una operación ya cerrada. El resultado es dinero, ya descontadas las comisiones.
        </p>
      ) : null}
      {error ? <p className="tone-bad">{error}</p> : null}
      <section className="card">
        <DynamicTable
          rows={rows}
          columns={isSimple ? SIMPLE_COLUMNS : COLUMNS}
          emptyLabel={isSimple ? "Todavía no hay operaciones" : "Sin operaciones registradas"}
          rowKey={(row) => String(row.id ?? Math.random())}
        />
      </section>
    </div>
  );
}
