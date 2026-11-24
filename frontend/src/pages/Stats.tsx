import { useEffect, useRef, useState } from "react";
import { EquityChart } from "../components/EquityChart";
import { Underwater } from "../components/Underwater";
import { KvPanel } from "../components/KvPanel";
import { useClock } from "../components/Sparkline";
import { api } from "../api";
import { useStore } from "../store";
import { ageLabel, formatValue, sideLabel } from "../utils";
import type { KvEntry } from "../types";

const TABS = ["resumen", "rendimiento", "direccion", "hora", "mes"] as const;
type Tab = (typeof TABS)[number];

interface BucketStats {
  trades: number;
  wins?: number;
  losses?: number;
  win_rate: number;
  profit_factor: number;
  expectancy_r: number;
  pnl_net: number;
  max_drawdown: number;
}

interface StatsPayload {
  // Reloj con el que el servidor agrupó horas y días (plantilla de la sesión).
  timezone?: string;
  closed: Record<string, number> & {
    r_median?: number;
    r_distribution?: Record<string, number>;
    expectancy_r?: number;
    expectancy_ci80_low?: number;
  };
  // el servidor manda estas claves dentro de `closed`; el Record<string, number>
  // de arriba ya las admite, aquí solo se nombran para leerlas sin casts
  by_hour: Record<string, BucketStats>;
  by_weekday: Record<string, BucketStats>;
  by_month: Record<string, BucketStats>;
  by_side: Record<string, BucketStats>;
  by_day: Record<string, BucketStats>;
  equity: { ts: string; equity: number }[];
}

const MONEY_KEYS = new Set([
  "pnl_net",
  "fees",
  "avg_win",
  "avg_loss",
  "max_drawdown",
  "best_trade",
  "worst_trade",
  "pnl_without_top5",
]);

const COUNT_KEYS = new Set([
  "trades",
  "wins",
  "losses",
  "ambiguous_trades",
  "impossible_durations",
  "max_loss_streak",
]);

const DURATION_KEYS = new Set(["avg_duration_minutes"]);

/** Los nombres internos del servidor no son etiquetas: se traducen una vez. */
const STAT_LABELS: Record<string, string> = {
  trades: "Operaciones",
  wins: "Ganadoras",
  losses: "Perdedoras",
  ambiguous_trades: "Resultado ambiguo",
  impossible_durations: "Cierres imposibles",
  win_rate: "Tasa de acierto",
  profit_factor: "Profit factor",
  expectancy_r: "Esperanza por operación",
  expectancy_ci80_low: "Suelo del IC80",
  pnl_net: "P&L neto",
  pnl_gross: "P&L bruto",
  fees: "Comisiones",
  avg_win: "Ganancia media",
  avg_loss: "Pérdida media",
  max_drawdown: "Drawdown máximo",
  best_trade: "Mejor operación",
  worst_trade: "Peor operación",
  max_loss_streak: "Racha de pérdidas",
  top5_share: "Peso de las 5 mejores",
  pnl_without_top5: "P&L sin las 5 mejores",
  r_median: "Mediana en R",
  r_total: "R acumulado",
  avg_duration_minutes: "Duración media",
};

/**
 * El servidor manda las tasas como fracción (0.333 = 33.3 %). Pasarlas tal
 * cual a un formato que añade «%» las deja cien veces más pequeñas. Los
 * recuentos, en cambio, son enteros: «9.00 operaciones» finge una precisión
 * que no existe.
 */
export function toEntries(values: Record<string, number>): Record<string, KvEntry> {
  const entries: Record<string, KvEntry> = {};
  // Sin ninguna pérdida el PF no tiene denominador; el motor manda 1,00 para
  // que el JSON sea válido, y pintarlo tal cual haría pasar un pleno de
  // aciertos por un empate.
  const noLosses = values.losses === 0 && (values.wins ?? 0) > 0;
  for (const [key, value] of Object.entries(values)) {
    if (typeof value !== "number") continue;
    const money = MONEY_KEYS.has(key);
    const rate = key.includes("rate") || key === "top5_share";
    const count = COUNT_KEYS.has(key);
    if (key === "profit_factor" && noLosses) {
      entries[key] = {
        label: STAT_LABELS[key] ?? key,
        value: "∞ (sin pérdidas)",
        format: "text",
        unit: null,
        tone: "neutral",
        group: null,
      };
      continue;
    }
    entries[key] = {
      label: STAT_LABELS[key] ?? key.replace(/_/g, " "),
      value: rate ? value * 100 : value,
      format: money
        ? "price"
        : rate
          ? "pct"
          : DURATION_KEYS.has(key)
            ? "duration"
            : count
              ? "text"
              : "number",
      unit: null,
      tone: money && value < 0 ? "bad" : "neutral",
      group: null,
    };
  }
  return entries;
}

/**
 * El servidor nombra los tramos con sus claves internas: `long` y el
 * `strftime("%a")` del locale del motor. En una tabla en español, «Mon» no es
 * una etiqueta y «long» no se entiende sin saber inglés.
 */
const WEEKDAY_LABELS: Record<string, string> = {
  mon: "lunes",
  tue: "martes",
  wed: "miércoles",
  thu: "jueves",
  fri: "viernes",
  sat: "sábado",
  sun: "domingo",
  lun: "lunes",
  mar: "martes",
  mié: "miércoles",
  mie: "miércoles",
  jue: "jueves",
  vie: "viernes",
  sáb: "sábado",
  sab: "sábado",
  dom: "domingo",
};

export function bucketLabel(bucket: string): string {
  const key = bucket.trim().toLowerCase();
  if (key === "long" || key === "short") return sideLabel(key);
  return WEEKDAY_LABELS[key] ?? bucket;
}

/**
 * Las horas del desglose son las del reloj de la sesión (la plantilla del
 * instrumento), no las del equipo de quien mira. Sin decirlo, un «08:00» de un
 * perfil UTC se lee como la hora local del navegador y el tramo apunta a otra
 * franja del día.
 */
export function hourZoneNote(timezone: string | undefined): string {
  if (!timezone) {
    return "Los tramos de hora, día, semana y mes van por el reloj de la sesión, no por el de tu equipo.";
  }
  return `Los tramos de hora, día, semana y mes van por el reloj de la sesión (${timezone}), no por el de tu equipo: un cierre a las 08:00 de ese reloj cae en «08:00».`;
}

function BreakdownTable({ rows }: { rows: Record<string, BucketStats> }) {
  const buckets = Object.entries(rows);
  if (buckets.length === 0) return <p className="empty">Sin datos por tramo</p>;
  return (
    <table className="dynamic-table">
      <thead>
        <tr>
          <th>Tramo</th>
          <th>Ops</th>
          <th>Win rate</th>
          <th>PF</th>
          <th>Expectativa R</th>
          <th>P&L neto</th>
        </tr>
      </thead>
      <tbody>
        {buckets.map(([bucket, stats]) => (
          <tr key={bucket}>
            <td>{bucketLabel(bucket)}</td>
            <td>{stats.trades}</td>
            <td>{formatValue(stats.win_rate * 100, "pct")}</td>
            <td
              title={
                stats.losses === 0 && (stats.wins ?? 0) > 0
                  ? "Sin pérdidas todavía: el profit factor no tiene denominador"
                  : undefined
              }
            >
              {stats.losses === 0 && (stats.wins ?? 0) > 0
                ? "∞"
                : formatValue(stats.profit_factor, "ratio")}
            </td>
            <td
              className={
                stats.expectancy_r > 0 ? "tone-good" : stats.expectancy_r < 0 ? "tone-bad" : ""
              }
            >
              {formatValue(stats.expectancy_r, "ratio")}
            </td>
            <td className={stats.pnl_net > 0 ? "tone-good" : stats.pnl_net < 0 ? "tone-bad" : ""}>
              {formatValue(stats.pnl_net, "price")}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface ValidationPayload {
  verdict: string;
  failed: string[];
  not_measured: string[];
  outcomes: { id: string; description: string; status: string; detail: string }[];
}

interface FunnelPayload {
  stages: Record<string, number>;
  verdicts: Record<string, number>;
  survival_rate: number;
  by_strategy: Record<string, { experiments: number; verdicts: Record<string, number> }>;
}

const FUNNEL_LABELS: Record<string, string> = {
  experiments: "Experimentos registrados",
  strategies: "Estrategias distintas",
  datasets: "Datasets distintos",
  rejected: "Rechazadas",
  inconclusive: "Inconclusas",
  approved: "Aprobadas",
};

function FunnelPanel({ funnel }: { funnel: FunnelPayload }) {
  const experiments = funnel.stages.experiments;
  const rows = Object.keys(FUNNEL_LABELS).map((key) => ({
    key,
    label: FUNNEL_LABELS[key],
    // Un recuento ausente no es un cero: el embudo no midió ese tramo.
    value: funnel.stages[key],
  }));
  const strategies = Object.entries(funnel.by_strategy);
  return (
    <section className="card" data-funnel>
      <header className="card-header">
        <h3>Embudo de evaluación</h3>
        <span className="badge">
          {typeof experiments !== "number"
            ? "sin dato"
            : experiments > 0
              ? typeof funnel.survival_rate === "number"
                ? `${(funnel.survival_rate * 100).toFixed(1)} % supervivencia`
                : "supervivencia sin dato"
              : "sin datos"}
        </span>
      </header>
      {experiments === 0 ? (
        <p className="empty">Sin experimentos registrados todavía</p>
      ) : (
        <>
          <dl className="kv">
            {rows.map((row) => (
              <div key={row.key} className="kv-row">
                <dt>{row.label}</dt>
                <dd>{row.value ?? "—"}</dd>
              </div>
            ))}
          </dl>
          <ul className="gate-list">
            {strategies.map(([id, node]) => (
              <li key={id} className="gate">
                <strong>{id}</strong> · {node.experiments} experimento(s) ·{" "}
                {Object.entries(node.verdicts)
                  .map(([verdict, count]) => `${verdict} ${count}`)
                  .join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/**
 * ¿El resultado depende de cinco operaciones?
 *
 * `top5_share` es la parte del beneficio bruto que aportan las cinco mejores.
 * Un número alto con pocas operaciones no es una estrategia: es suerte con
 * fecha. Se enseña junto al P&L sin esas cinco para que la resta sea visible.
 */
type ConcentrationInput = {
  trades?: number;
  wins?: number;
  top5_share?: number;
  pnl_without_top5?: number;
};

/** La frase tiene que decir lo que pasa con *estos* números, no con un ideal. */
export function concentrationNote(closed: ConcentrationInput): string {
  const trades = closed.trades ?? 0;
  const wins = closed.wins ?? 0;
  const share = closed.top5_share ?? 0;
  const without = closed.pnl_without_top5 ?? 0;
  const fragile = share > 0.5;
  const sample =
    trades < 10
      ? `Con ${trades} operación${trades === 1 ? "" : "es"} esto todavía es ruido: sirve para ver el mecanismo, no para concluir. `
      : "";
  if (!fragile) {
    // Poca concentración no garantiza que la resta siga en positivo: se mira.
    if (without < 0) {
      return `${sample}El beneficio no se concentra en cinco operaciones (${(share * 100).toFixed(0)} %), pero sin ellas el signo se da la vuelta (${formatSigned(without)}): el resto no se sostiene solo.`;
    }
    return `${sample}El resultado no depende de unas pocas operaciones: quitar las cinco mejores lo deja en ${formatSigned(without)}.`;
  }
  if (wins <= 1) {
    return `${sample}Todo el beneficio bruto sale de ${wins === 0 ? "ninguna operación" : "una sola operación"}: no es una estrategia, es un acierto. Quítalo y la cuenta queda en pérdidas.`;
  }
  return `${sample}Más de la mitad de lo ganado viene de cinco operaciones: sin ellas, el resultado queda en ${formatSigned(without)}. Es la puerta G9/G10 y suele ser la que separa una estrategia de una racha.`;
}

function Concentration({ closed }: { closed: StatsPayload["closed"] }) {
  const trades = closed.trades ?? 0;
  if (trades < 5) {
    return null;
  }
  // Un 0 de relleno se leería como «el resultado no depende de cinco
  // operaciones», que es justo la conclusión que estos números deben sostener.
  const share =
    typeof closed.top5_share === "number" ? Math.max(0, Math.min(1, closed.top5_share)) : null;
  const without = typeof closed.pnl_without_top5 === "number" ? closed.pnl_without_top5 : null;
  const complete = share !== null && without !== null;
  const fragile = complete && share > 0.5;
  return (
    <section className="card" data-concentration>
      <header className="card-header">
        <h3>Concentración del resultado</h3>
        <span className={`badge ${!complete ? "" : fragile ? "tone-bad" : "tone-good"}`}>
          {share !== null ? `${(share * 100).toFixed(0)} % en las 5 mejores` : "sin desglose"}
        </span>
      </header>
      {share !== null ? (
        <div className="concentration-track" aria-hidden="true">
          <span style={{ width: `${share * 100}%` }} />
        </div>
      ) : null}
      <dl className="kv">
        <div className="kv-row">
          <dt>P&L total</dt>
          <dd className="mono">
            {typeof closed.pnl_net === "number" ? formatSigned(closed.pnl_net) : "—"}
          </dd>
        </div>
        <div className="kv-row">
          <dt>P&L sin las 5 mejores</dt>
          <dd
            className={`mono ${
              without === null ? "" : without > 0 ? "tone-good" : without < 0 ? "tone-bad" : ""
            }`}
          >
            {without !== null ? formatSigned(without) : "—"}
          </dd>
        </div>
      </dl>
      <p className={fragile ? "tone-warn small" : "muted small"}>
        {complete
          ? concentrationNote({
              trades: closed.trades,
              wins: closed.wins,
              top5_share: closed.top5_share,
              pnl_without_top5: closed.pnl_without_top5,
            })
          : "El servidor no envió el desglose de concentración: sin ese dato no se puede decir si el resultado depende de cinco operaciones."}
      </p>
    </section>
  );
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

type EvidenceInput = {
  trades?: number;
  expectancy_r?: number;
  expectancy_ci80_low?: number;
};

/**
 * ¿La media por operación demuestra ventaja o es suerte?
 *
 * Una media positiva con pocas operaciones se lee como «funciona»; el suelo
 * del intervalo del 80 % es lo que separa esa frase de la realidad. Misma
 * regla que la puerta G de la validación, dicha sin jerga.
 */
export function evidenceNote(closed: EvidenceInput): string {
  const trades = closed.trades ?? 0;
  const expectancy = closed.expectancy_r ?? 0;
  const low = closed.expectancy_ci80_low ?? 0;
  const sample =
    trades < 30
      ? `Con ${trades} ${trades === 1 ? "operación" : "operaciones"} la muestra es corta: sirve para ver la mecánica, no para concluir. `
      : "";
  if (low > 0) {
    return `${sample}El suelo del intervalo del 80 % queda por encima de cero (${formatSigned(low)} R): hay señales de ventaja, falta más muestra para confirmarla.`;
  }
  if (expectancy > 0) {
    return `${sample}La media es positiva (${formatSigned(expectancy)} R), pero el intervalo del 80 % toca cero (${formatSigned(low)} R): la ventaja no está demostrada.`;
  }
  return `${sample}La media es negativa (${formatSigned(expectancy)} R) y el intervalo del 80 % baja hasta ${formatSigned(low)} R: con estos datos no hay ventaja demostrada; el sistema está perdiendo.`;
}

function Evidence({ closed }: { closed: StatsPayload["closed"] }) {
  const trades = closed.trades ?? 0;
  if (trades === 0) return null;
  // Sin media o sin intervalo no hay veredicto: decir «0.00 R» sería inventar
  // justo el número que decide si la ventaja está demostrada.
  const expectancy = typeof closed.expectancy_r === "number" ? closed.expectancy_r : null;
  const low = typeof closed.expectancy_ci80_low === "number" ? closed.expectancy_ci80_low : null;
  const measured = expectancy !== null && low !== null;
  const tone = (value: number | null) =>
    value === null || value === 0 ? "" : value > 0 ? "tone-good" : "tone-bad";
  return (
    <section className="card" data-evidence>
      <header className="card-header">
        <h3>¿El sistema demuestra ventaja?</h3>
        <span
          className={`badge ${
            low === null || low === 0 ? "" : low > 0 ? "tone-good" : "tone-bad"
          }`}
        >
          {low === null ? "suelo del IC80 sin dato" : `suelo del IC80 ${formatSigned(low)} R`}
        </span>
      </header>
      <dl className="kv">
        <div className="kv-row">
          <dt>Resultado medio por operación</dt>
          <dd className={`mono ${tone(expectancy)}`}>
            {expectancy === null ? "—" : `${formatSigned(expectancy)} R`}
          </dd>
        </div>
        <div className="kv-row">
          <dt>Suelo del intervalo (80 %)</dt>
          <dd className={`mono ${tone(low)}`}>{low === null ? "—" : `${formatSigned(low)} R`}</dd>
        </div>
        <div className="kv-row">
          <dt>Operaciones</dt>
          <dd className="mono">{trades}</dd>
        </div>
      </dl>
      <p className="muted small">
        {measured
          ? evidenceNote({
              trades,
              expectancy_r: closed.expectancy_r,
              expectancy_ci80_low: closed.expectancy_ci80_low,
            })
          : "El servidor no envió la esperanza o su intervalo: sin esos números no se puede decir si hay ventaja."}
      </p>
    </section>
  );
}

function RDistribution({ closed }: { closed: StatsPayload["closed"] }) {
  const buckets = Object.entries(closed.r_distribution ?? {});
  if (buckets.length === 0) return null;
  const total = buckets.reduce((sum, [, count]) => sum + count, 0);
  const peak = Math.max(...buckets.map(([, count]) => count), 1);
  return (
    <section className="card" data-r-distribution>
      <header className="card-header">
        <h3>Distribución de R</h3>
        <span className="muted small">
          {typeof closed.r_median === "number" ? `mediana ${closed.r_median.toFixed(2)} R` : "mediana sin dato"}
          {" · "}
          {typeof closed.expectancy_r === "number"
            ? `media ${closed.expectancy_r.toFixed(2)} R`
            : "media sin dato"}
        </span>
      </header>
      {total === 0 ? (
        <p className="empty">Sin operaciones cerradas</p>
      ) : (
        <ul className="histogram">
          {buckets.map(([label, count]) => (
            <li key={label}>
              <span className="histogram-label">{label}</span>
              <span
                className="histogram-bar"
                // Un tramo vacío no dibuja barra: el mínimo de 2 % es para que
                // los tramos con una sola operación se vean, no para inventar
                // presencia donde no hay ninguna.
                style={{
                  width: count === 0 ? "0%" : `${Math.max(2, (count / peak) * 100)}%`,
                  opacity: count === 0 ? 0 : 1,
                }}
                data-count={count}
              />
              <span className="histogram-value">{count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function StatsPage() {
  const { snapshot } = useStore();
  const initialCapital = snapshot?.risk.limits.initial_capital ?? null;
  const [tab, setTab] = useState<Tab>("resumen");
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [validation, setValidation] = useState<ValidationPayload | null>(null);
  const [funnel, setFunnel] = useState<FunnelPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);
  const tick = useClock(5_000);
  // Un cierre nuevo invalida las cifras: se vuelven a pedir solas. El total no
  // se reinicia con la sesión; usar `daily_trades` perdería el primer cierre
  // posterior a medianoche mientras no superara el máximo del día anterior.
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

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .stats()
      .then((payload) => {
        if (cancelled) return;
        setStats(payload as unknown as StatsPayload);
        setLoadedAt(Date.now());
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });
    api
      .validation()
      .then((payload) => {
        if (!cancelled) setValidation(payload);
      })
      .catch(() => undefined);
    api
      .funnel()
      .then((payload) => {
        if (!cancelled) setFunnel(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  return (
    <div className="page">
      <h2 className="page-title">
        Estadísticas
        <span className="muted small">
          {/* Las cifras se leen al abrir la vista: con el motor cerrando
              operaciones, callar su antigüedad las haría pasar por vivas. */}
          {loadedAt !== null ? `leído ${ageLabel(tick.getTime() - loadedAt)}` : "leyendo…"}
        </span>
        <button
          type="button"
          className="btn btn-ghost page-title-action"
          onClick={() => setNonce((value) => value + 1)}
        >
          Actualizar
        </button>
      </h2>
      <div className="button-row">
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            className={value === tab ? "btn active" : "btn"}
            onClick={() => setTab(value)}
          >
            {value}
          </button>
        ))}
      </div>
      {stats && (tab === "hora" || tab === "mes" || tab === "rendimiento") ? (
        <p className="muted small" data-hour-zone>
          {hourZoneNote(stats.timezone)}
        </p>
      ) : null}
      {error ? <p className="tone-bad">{error}</p> : null}
      {stats && (stats.closed.impossible_durations ?? 0) > 0 ? (
        <p className="tone-warn small" data-impossible-durations>
          {stats.closed.impossible_durations === 1
            ? "1 operación del histórico cierra antes de abrir"
            : `${stats.closed.impossible_durations} operaciones del histórico cierran antes de abrir`}
          : son fechas imposibles que se conservan tal cual. La duración media y el orden de la
          curva las incluyen, así que no son fiables al pie de la letra.
        </p>
      ) : null}

      {validation ? (
        <section className="card" data-validation>
          <header className="card-header">
            <h3>Veredicto de validación</h3>
            <span
              className={
                validation.verdict === "APROBADA"
                  ? "badge tone-good"
                  : validation.verdict === "RECHAZADA"
                    ? "badge tone-bad"
                    : "badge tone-warn"
              }
            >
              {validation.verdict}
            </span>
          </header>
          {validation.failed.length > 0 ? (
            <p className="tone-bad small">Fallan: {validation.failed.join(", ")}</p>
          ) : null}
          {validation.not_measured.length > 0 ? (
            <p className="muted small">
              No medibles en esta ejecución: {validation.not_measured.join(", ")}
            </p>
          ) : null}
          <ul className="gate-list">
            {validation.outcomes.map((gate) => (
              <li key={gate.id} className={`gate gate-${gate.status}`}>
                <strong>{gate.id}</strong> {gate.description} · {gate.detail}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {funnel && tab === "resumen" ? <FunnelPanel funnel={funnel} /> : null}

      {tab === "resumen" && stats ? <Evidence closed={stats.closed} /> : null}

      {tab === "resumen" ? (
        <section className="card">
          {stats ? (
            <KvPanel
              entries={toEntries(stats.closed)}
              emptyLabel="Sin operaciones cerradas"
            />
          ) : (
            <p className="empty">
              {error ? "No se pudieron cargar las estadísticas." : "Cargando…"}
            </p>
          )}
        </section>
      ) : null}

      {tab === "rendimiento" && stats ? <RDistribution closed={stats.closed} /> : null}
      {tab === "rendimiento" && stats ? <Concentration closed={stats.closed} /> : null}

      {tab === "rendimiento" ? (
        <section className="card">
          {stats ? (
            <>
              <header className="card-header">
                <h3>Curva de equidad</h3>
                <span className="muted small">
                  {stats.equity.length} cierres
                  {initialCapital !== null ? ` · referencia ${formatValue(initialCapital, "price")}` : ""}
                </span>
              </header>
              <EquityChart points={stats.equity} baseline={initialCapital} />
              <header className="card-header underwater-head">
                <h3>Bajo el agua</h3>
                <span className="muted small">
                  {initialCapital !== null
                    ? "distancia al capital inicial · el pico marca 0 %"
                    : "distancia al primer cierre cargado (sin capital inicial) · el pico marca 0 %"}
                </span>
              </header>
              <Underwater points={stats.equity} baseline={initialCapital} />
              <h3>Por día</h3>
              <BreakdownTable rows={stats.by_day ?? {}} />
            </>
          ) : (
            <p className="empty">
              {error ? "No se pudieron cargar las estadísticas." : "Cargando…"}
            </p>
          )}
        </section>
      ) : null}

      {tab === "direccion" ? (
        <section className="card">
          {stats ? (
            <BreakdownTable rows={stats.by_side ?? {}} />
          ) : (
            <p className="empty">
              {error ? "No se pudieron cargar las estadísticas." : "Cargando…"}
            </p>
          )}
        </section>
      ) : null}

      {tab === "hora" ? (
        <section className="card">
          {stats ? (
            <>
              <BreakdownTable rows={stats.by_hour ?? {}} />
              <h3>Por día de la semana</h3>
              <BreakdownTable rows={stats.by_weekday ?? {}} />
            </>
          ) : (
            <p className="empty">
              {error ? "No se pudieron cargar las estadísticas." : "Cargando…"}
            </p>
          )}
        </section>
      ) : null}

      {tab === "mes" ? (
        <section className="card">
          {stats ? (
            <BreakdownTable rows={stats.by_month ?? {}} />
          ) : (
            <p className="empty">
              {error ? "No se pudieron cargar las estadísticas." : "Cargando…"}
            </p>
          )}
        </section>
      ) : null}
    </div>
  );
}
