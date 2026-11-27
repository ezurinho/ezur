import { useEffect, useMemo, useRef, useState } from "react";
import { DynamicTable, type Column } from "../components/DynamicTable";
import { KvPanel } from "../components/KvPanel";
import { useClock } from "../components/Sparkline";
import { api } from "../api";
import { useUiMode } from "../mode";
import { useStore } from "../store";
import { ageLabel, formatDateTime, formatValue, sideLabel, toFinite } from "../utils";
import type { KvEntry } from "../types";

type Row = Record<string, unknown>;

const PERIODS = ["today", "week", "month", "30d", "all"] as const;
type Period = (typeof PERIODS)[number];

const PERIOD_WORDS: Record<Period, string> = {
  today: "hoy",
  week: "7 días",
  month: "mes en curso",
  "30d": "30 días",
  all: "todo",
};

const EXIT_WORD: Record<string, string> = {
  stop: "saltó el stop",
  target: "objetivo",
  manual: "a mano",
  session_close: "fin del día",
  cancel: "cancelada",
};

type HistoryView = "trades" | "summary";

const HISTORY_VIEWS: { id: HistoryView; label: string }[] = [
  { id: "trades", label: "Operaciones" },
  { id: "summary", label: "Resumen" },
];

/** Beginner columns: when, what, how much. No R, no prices, no diagnostics. */
export const SIMPLE_COLUMNS: Column<Row>[] = [
  { key: "closed_ts", header: "Cuándo", render: (row) => formatDateTime(String(row.closed_ts)) },
  {
    key: "side",
    header: "Qué hizo",
    render: (row) =>
      row.side === null || row.side === undefined ? (
        <span className="muted">—</span>
      ) : (
        sideLabel(String(row.side))
      ),
  },
  {
    key: "pnl_net",
    header: "Resultado",
    render: (row) => {
      // Un pnl_net ausente no es un empate: sin dato, «—».
      const value = toFinite(row.pnl_net);
      if (value === null) return <span className="muted">—</span>;
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
    render: (row) => {
      if (row.exit_reason === null || row.exit_reason === undefined || row.exit_reason === "") {
        return <span className="muted">—</span>;
      }
      const reason = String(row.exit_reason);
      return EXIT_WORD[reason] ?? reason;
    },
  },
];

/**
 * Server-side range: a browser-side filter over 200 rows is a lie by omission.
 *
 * «Hoy» es el día de la sesión del motor, que con la plantilla de esta instancia
 * empieza a las 00:00 UTC, no la medianoche del navegador: con otro huso,
 * Historial y la tarjeta «Hoy» del inicio contarían operaciones distintas con
 * la misma palabra. Si el snapshot trae la apertura real de la sesión, manda
 * esa: una plantilla de Nueva York no abre a medianoche UTC.
 */
export function periodStart(
  period: Period,
  now: Date = new Date(),
  sessionOpen: string | null = null,
): string | undefined {
  if (period === "all") return undefined;
  if (period === "today") {
    const opened = sessionOpen ? Date.parse(sessionOpen) : NaN;
    if (Number.isFinite(opened)) return new Date(opened).toISOString();
    return new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
    ).toISOString();
  }
  // «Mes» es el mes en curso, no los últimos treinta días: para eso está «30d».
  if (period === "month") {
    return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
  }
  const days = period === "week" ? 7 : 30;
  return new Date(now.getTime() - days * 86_400_000).toISOString();
}

const COLUMNS: Column<Row>[] = [
  { key: "closed_ts", header: "Cierre", render: (row) => formatDateTime(String(row.closed_ts)) },
  { key: "symbol", header: "Instrumento" },
  { key: "side", header: "Dirección" },
  { key: "units", header: "Unidades" },
  { key: "entry_price", header: "Entrada", render: (row) => formatValue(toFinite(row.entry_price), "price") },
  { key: "exit_price", header: "Salida", render: (row) => formatValue(toFinite(row.exit_price), "price") },
  { key: "pnl_net", header: "P&L neto", render: (row) => formatValue(toFinite(row.pnl_net), "price") },
  { key: "r_multiple", header: "R", render: (row) => formatValue(toFinite(row.r_multiple), "ratio") },
  { key: "exit_reason", header: "Motivo" },
  { key: "mode", header: "Modo" },
];

const TRADE_LIMIT = 200;
// La tabla se queda en 200 para no pintar miles de filas; el resumen usa el
// máximo que el CSV ya permite para no llamar «total» a media historia.
const SUMMARY_LIMIT = 5000;

/**
 * La tabla muestra como máximo `TRADE_LIMIT` operaciones. Cuando llega justo
 * ese número, está recortada y callarlo convertiría «todo» en «lo último»: la
 * nota lo dice y ofrece la salida (acotar el periodo o CSV).
 */
export function rowsNote(count: number): string | null {
  if (count < TRADE_LIMIT) return null;
  // El CSV también tiene tope (5000): decirlo evita que alguien crea que
  // exporta «todo» cuando el rango es aún más largo. Con exactamente 200 filas
  // no se sabe si hay más: el aviso habla de posibilidad, no de un hecho.
  return `Se alcanzó el límite de ${TRADE_LIMIT}: puede haber operaciones anteriores. Acota el periodo o usa el CSV (hasta 5000 filas) para verlas.`;
}

export interface HistorySummary {
  rows: number;
  priced: number;
  missing: number;
  wins: number;
  losses: number;
  flats: number;
  grossWin: number;
  grossLoss: number;
  net: number | null;
  fees: number | null;
  rTotal: number | null;
  avgWin: number | null;
  avgLoss: number | null;
  best: number | null;
  worst: number | null;
  winRate: number | null;
  profitFactor: number | null;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

/**
 * Suma solo lo que tiene P&L. Un `null` no es un cero: convertirlo en cero
 * inflaría el número de operaciones y mezclaría «no medido» con «empatado».
 */
export function summarizeHistory(rows: Row[]): HistorySummary {
  const pnls: number[] = [];
  const fees: number[] = [];
  const rs: number[] = [];
  for (const row of rows) {
    const pnl = toFinite(row.pnl_net);
    if (pnl !== null) pnls.push(pnl);
    const fee = toFinite(row.fees);
    if (fee !== null) fees.push(fee);
    const r = toFinite(row.r_multiple);
    if (r !== null) rs.push(r);
  }
  const wins = pnls.filter((value) => value > 0);
  const losses = pnls.filter((value) => value < 0);
  const grossWin = sum(wins);
  const grossLoss = sum(losses);
  return {
    rows: rows.length,
    priced: pnls.length,
    missing: rows.length - pnls.length,
    wins: wins.length,
    losses: losses.length,
    flats: pnls.filter((value) => value === 0).length,
    grossWin,
    grossLoss,
    net: pnls.length ? sum(pnls) : null,
    fees: fees.length ? sum(fees) : null,
    rTotal: rs.length ? sum(rs) : null,
    avgWin: wins.length ? grossWin / wins.length : null,
    avgLoss: losses.length ? grossLoss / losses.length : null,
    best: pnls.length ? Math.max(...pnls) : null,
    worst: pnls.length ? Math.min(...pnls) : null,
    winRate: pnls.length ? wins.length / pnls.length : null,
    // Sin pérdidas el PF no tiene denominador; se pinta «sin pérdidas», no 1.
    profitFactor: grossLoss < 0 ? grossWin / Math.abs(grossLoss) : null,
  };
}

function money(value: number, positiveSign = false): string {
  return `${positiveSign && value > 0 ? "+" : ""}${formatValue(value, "price")}`;
}

function entry(
  label: string,
  value: number | string | null,
  format: KvEntry["format"],
  tone: KvEntry["tone"] = "neutral",
): KvEntry {
  return { label, value, format, unit: null, tone, group: null };
}

export function summaryEntries(summary: HistorySummary): Record<string, KvEntry> {
  const pf = summary.profitFactor;
  return {
    ops: entry("Operaciones", summary.rows, "text"),
    wins: entry("Ganadoras", summary.wins, "text", "good"),
    losses: entry("Perdedoras", summary.losses, "text", "bad"),
    flats: entry("Empates", summary.flats, "text"),
    ...(summary.missing > 0
      ? { missing: entry("Sin P&L", summary.missing, "text", "warn") }
      : {}),
    win_rate: entry(
      "Tasa de acierto",
      summary.winRate === null ? null : summary.winRate * 100,
      "pct",
    ),
    pf: entry(
      "Factor de beneficio",
      pf === null ? (summary.grossWin > 0 ? "∞ (sin pérdidas)" : null) : pf,
      pf === null ? "text" : "ratio",
      pf === null ? "neutral" : pf >= 1 ? "good" : "bad",
    ),
    avg_win: entry("Ganancia media", summary.avgWin, "price", "good"),
    avg_loss: entry("Pérdida media", summary.avgLoss, "price", "bad"),
    best: entry("Mejor operación", summary.best, "price", "good"),
    worst: entry("Peor operación", summary.worst, "price", "bad"),
    fees: entry("Comisiones", summary.fees, "price"),
    r_total: entry(
      "R acumulado",
      summary.rTotal,
      "ratio",
      summary.rTotal !== null && summary.rTotal < 0 ? "bad" : "neutral",
    ),
  };
}

function HistorySummaryView({
  rows,
  loaded,
  error,
  period,
  simple,
  truncated,
}: {
  rows: Row[];
  loaded: boolean;
  error: string | null;
  period: Period;
  simple: boolean;
  truncated: boolean;
}) {
  if (error) return <p className="empty">No se pudo cargar el resumen.</p>;
  if (!loaded) return <p className="empty">Leyendo operaciones…</p>;
  if (rows.length === 0) return <p className="empty">Todavía no hay operaciones en este periodo.</p>;

  const summary = summarizeHistory(rows);
  const hasPnl = summary.priced > 0;
  const net = summary.net;
  const netTone = net === null ? "muted" : net > 0 ? "tone-good" : net < 0 ? "tone-bad" : "";
  const periodWord = PERIOD_WORDS[period];

  return (
    <>
      {truncated ? (
        <p className="tone-warn small" data-summary-limit>
          El resumen suma las {SUMMARY_LIMIT} operaciones más recientes: puede haber más. Acota
          el periodo para que el total sea exacto.
        </p>
      ) : null}
      <div className="kpi-grid" data-history-summary>
        <article className="kpi">
          <span className="kpi-index" aria-hidden="true">01</span>
          <span className="kpi-label">Total ganado</span>
          <span className={`kpi-value ${hasPnl && summary.grossWin > 0 ? "tone-good" : ""}`}>
            {hasPnl ? money(summary.grossWin, true) : "—"}
          </span>
          <span className="kpi-foot">
            <span>{summary.wins} ganadoras</span>
            <span>{periodWord}</span>
          </span>
        </article>
        <article className="kpi">
          <span className="kpi-index" aria-hidden="true">02</span>
          <span className="kpi-label">Total perdido</span>
          <span className={`kpi-value ${hasPnl && summary.grossLoss < 0 ? "tone-bad" : ""}`}>
            {hasPnl ? money(summary.grossLoss) : "—"}
          </span>
          <span className="kpi-foot">
            <span>{summary.losses} perdedoras</span>
            <span>{periodWord}</span>
          </span>
        </article>
        <article className="kpi">
          <span className="kpi-index" aria-hidden="true">03</span>
          <span className="kpi-label">Resultado total</span>
          <span className={`kpi-value ${netTone}`}>{net === null ? "—" : money(net, true)}</span>
          <span className="kpi-foot">
            <span>
              {summary.winRate === null
                ? "sin cierres"
                : `${formatValue(summary.winRate * 100, "pct", 1)} de acierto`}
            </span>
            <span>{periodWord}</span>
          </span>
        </article>
        <article className="kpi">
          <span className="kpi-index" aria-hidden="true">04</span>
          <span className="kpi-label">Operaciones</span>
          <span className="kpi-value">{summary.rows}</span>
          <span className="kpi-foot">
            <span>
              {summary.wins} G · {summary.losses} P
            </span>
            <span>{summary.missing ? `${summary.missing} sin P&L` : periodWord}</span>
          </span>
        </article>
      </div>
      {hasPnl ? (
        <section className="summary-balance" data-history-balance aria-label="Reparto de operaciones">
          <div className="summary-balance-head">
            <span className="summary-balance-title">Reparto del periodo</span>
            <span className="mono small">
              {summary.wins} G · {summary.losses} P
            </span>
          </div>
          <div
            className="summary-balance-track"
            role="img"
            aria-label={`${summary.wins} ganadoras y ${summary.losses} perdedoras`}
          >
            <span
              className="summary-balance-win"
              style={{ width: `${summary.wins + summary.losses > 0 ? (summary.wins / (summary.wins + summary.losses)) * 100 : 0}%` }}
            />
          </div>
          <div className="summary-balance-foot">
            <span className="tone-good">
              {summary.wins + summary.losses > 0
                ? formatValue((summary.wins / (summary.wins + summary.losses)) * 100, "pct", 0)
                : "0 %"}{" "}
              ganadoras
            </span>
            <span className="tone-bad">
              {summary.wins + summary.losses > 0
                ? formatValue((summary.losses / (summary.wins + summary.losses)) * 100, "pct", 0)
                : "0 %"}{" "}
              perdedoras
            </span>
            {summary.flats > 0 ? <span className="muted">{summary.flats} empates</span> : null}
          </div>
        </section>
      ) : null}
      {!simple ? (
        <section className="card">
          <header className="card-header">
            <h3>Detalle del resumen</h3>
          <span className="muted small">
            {summary.rows} operaciones · {periodWord}
          </span>
        </header>
        <KvPanel entries={summaryEntries(summary)} />
          {summary.missing > 0 ? (
            <p className="muted small" data-summary-missing>
              {summary.missing === 1
                ? "1 operación sin P&L no entra"
                : `${summary.missing} operaciones sin P&L no entran`}{" "}
              en los totales.
            </p>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

export function HistoryPage() {
  const { isSimple } = useUiMode();
  const { snapshot } = useStore();
  const [rows, setRows] = useState<Row[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("all");
  const [view, setView] = useState<HistoryView>("trades");
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);
  const tick = useClock(5_000);
  const lastStart = useRef<string | undefined>(undefined);
  // El total de cierres cruza medianoche sin bajar; `daily_trades` se reinicia
  // y haría invisibles las primeras operaciones del día siguiente hasta superar
  // el máximo del anterior. Cualquier cambio (incluido un reset) invalida la lista.
  const closed = snapshot?.stats as { closed?: { trades?: number } } | undefined;
  const closedTrades = typeof closed?.closed?.trades === "number" ? closed.closed.trades : null;
  const refreshAfter = closedTrades ?? snapshot?.risk.daily_trades ?? null;
  const tradesSeen = useRef<number | null>(null);
  useEffect(() => {
    if (refreshAfter === null) return;
    const previous = tradesSeen.current;
    tradesSeen.current = refreshAfter;
    if (previous !== null && refreshAfter !== previous) setNonce((value) => value + 1);
  }, [refreshAfter]);

  const sessionOpen = snapshot?.session.open_ts ?? null;
  // El rango relativo se ancla a medianoche UTC y solo cambia al cambiar de
  // día. Sin esta ancla, «7 días» se queda congelado en el instante en que se
  // montó la página y ni «Actualizar» mueve la ventana.
  const clock = new Date();
  const rangeDay = Date.UTC(clock.getUTCFullYear(), clock.getUTCMonth(), clock.getUTCDate());
  const start = useMemo(
    () => periodStart(period, new Date(rangeDay), sessionOpen),
    [period, sessionOpen, rangeDay],
  );

  const tableRows = rows.slice(0, TRADE_LIMIT);

  useEffect(() => {
    let cancelled = false;
    // Al cambiar de periodo las filas viejas ya no pertenecen a ese rango:
    // dejarlas puestas mientras llega la respuesta es enseñar otro periodo.
    // Al refrescar el mismo periodo sí se quedan: borrarlas y volver a
    // pintarlas solo produce un parpadeo.
    if (lastStart.current !== start) {
      lastStart.current = start;
      setRows([]);
      setLoaded(false);
      setLoadedAt(null);
    }
    setError(null);
    api
      .trades({ limit: SUMMARY_LIMIT, start })
      .then((data) => {
        if (cancelled) return;
        setRows(data as unknown as Row[]);
        setLoaded(true);
        setLoadedAt(Date.now());
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [start, nonce]);

  return (
    <div className="page">
      <h2 className="page-title">
        Historial
        <span className="muted small">
          {/* Con el bot cerrando operaciones, una lista sin fecha de lectura
              se lee como «esto es todo lo que hay ahora mismo». */}
          {loadedAt !== null
            ? `leído ${ageLabel(tick.getTime() - loadedAt)}`
            : error
              ? "sin lectura"
              : "leyendo…"}
        </span>
        <button
          type="button"
          className="btn btn-ghost page-title-action"
          onClick={() => setNonce((value) => value + 1)}
        >
          Actualizar
        </button>
      </h2>
      <div className="history-controls">
        <div className="button-row history-views" role="tablist" aria-label="Vista del historial">
          {HISTORY_VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={view === item.id}
              className={view === item.id ? "btn active" : "btn"}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <span className="history-divider" aria-hidden="true" />
        <div className="button-row history-periods" role="group" aria-label="Periodo">
          {PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              className={value === period ? "btn active" : "btn"}
              aria-pressed={value === period}
              onClick={() => setPeriod(value)}
            >
              {PERIOD_WORDS[value]}
            </button>
          ))}
          {isSimple ? null : (
            <a className="btn" href={api.tradesCsvUrl({ start })} download>
              Exportar CSV
            </a>
          )}
        </div>
      </div>
      {isSimple && view === "trades" ? (
        <p className="simple-lead">
          Cada línea es una operación ya cerrada. El resultado es dinero, ya descontadas las comisiones.
        </p>
      ) : null}
      {isSimple && view === "summary" ? (
        <p className="simple-lead">
          Totales del periodo: solo operaciones cerradas y dinero después de comisiones.
        </p>
      ) : null}
      {period === "today" && snapshot?.session.label ? (
        <p className="muted small" data-today-session>
          «Hoy» cuenta desde que abrió la sesión {snapshot.session.label}
          {sessionOpen ? ` (${formatDateTime(sessionOpen)})` : ""}.
        </p>
      ) : null}
      {error ? <p className="tone-bad">{error}</p> : null}
      {view === "trades" ? (
        <section className="card">
          <DynamicTable
            rows={tableRows}
            columns={isSimple ? SIMPLE_COLUMNS : COLUMNS}
            emptyLabel={
              loaded
                ? isSimple
                  ? "Todavía no hay operaciones"
                  : "Sin operaciones registradas"
                : error
                  ? "No se pudieron cargar las operaciones"
                  : "Leyendo operaciones…"
            }
            rowKey={(row) =>
              String(row.id ?? `${row.closed_ts}-${row.symbol}-${row.side}-${row.entry_price}`)
            }
          />
          {rowsNote(tableRows.length) ? (
            <p className="muted small">{rowsNote(tableRows.length)}</p>
          ) : null}
        </section>
      ) : (
        <HistorySummaryView
          rows={rows}
          loaded={loaded}
          error={error}
          period={period}
          simple={isSimple}
          truncated={rows.length >= SUMMARY_LIMIT}
        />
      )}
    </div>
  );
}
