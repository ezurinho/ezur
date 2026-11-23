import { useEffect, useState } from "react";
import { EquityChart } from "../components/EquityChart";
import { Underwater } from "../components/Underwater";
import { KvPanel } from "../components/KvPanel";
import { api } from "../api";
import { formatValue } from "../utils";
import type { KvEntry } from "../types";

const TABS = ["resumen", "rendimiento", "direccion", "hora", "mes"] as const;
type Tab = (typeof TABS)[number];

interface BucketStats {
  trades: number;
  win_rate: number;
  profit_factor: number;
  expectancy_r: number;
  pnl_net: number;
  max_drawdown: number;
}

interface StatsPayload {
  closed: Record<string, number> & {
    r_median?: number;
    r_distribution?: Record<string, number>;
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
]);

function toEntries(values: Record<string, number>): Record<string, KvEntry> {
  const entries: Record<string, KvEntry> = {};
  for (const [key, value] of Object.entries(values)) {
    if (typeof value !== "number") continue;
    const money = MONEY_KEYS.has(key);
    entries[key] = {
      label: key,
      value,
      format: money ? "price" : key.includes("rate") ? "pct" : "number",
      unit: null,
      tone: money && value < 0 ? "bad" : "neutral",
      group: null,
    };
  }
  return entries;
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
            <td>{bucket}</td>
            <td>{stats.trades}</td>
            <td>{formatValue(stats.win_rate, "pct")}</td>
            <td>{formatValue(stats.profit_factor, "ratio")}</td>
            <td className={stats.expectancy_r < 0 ? "tone-bad" : "tone-good"}>
              {formatValue(stats.expectancy_r, "ratio")}
            </td>
            <td className={stats.pnl_net < 0 ? "tone-bad" : "tone-good"}>
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
  const rows = Object.keys(FUNNEL_LABELS).map((key) => ({
    key,
    label: FUNNEL_LABELS[key],
    value: funnel.stages[key] ?? 0,
  }));
  const strategies = Object.entries(funnel.by_strategy);
  return (
    <section className="card" data-funnel>
      <header className="card-header">
        <h3>Embudo de evaluación</h3>
        <span className="badge">{(funnel.survival_rate * 100).toFixed(1)} % supervivencia</span>
      </header>
      {funnel.stages.experiments === 0 ? (
        <p className="empty">Sin experimentos registrados todavía</p>
      ) : (
        <>
          <dl className="kv">
            {rows.map((row) => (
              <div key={row.key} className="kv-row">
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
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
  const fragile = share > 0.5;
  const sample =
    trades < 10
      ? `Con ${trades} operación${trades === 1 ? "" : "es"} esto todavía es ruido: sirve para ver el mecanismo, no para concluir. `
      : "";
  if (!fragile) {
    return `${sample}El resultado no depende de unas pocas operaciones: quitar las cinco mejores no lo cambia de signo.`;
  }
  if (wins <= 1) {
    return `${sample}Todo el beneficio bruto sale de ${wins === 0 ? "ninguna operación" : "una sola operación"}: no es una estrategia, es un acierto. Quítalo y la cuenta queda en pérdidas.`;
  }
  return `${sample}Más de la mitad de lo ganado viene de cinco operaciones: sin ellas, el sistema no se sostiene. Es la puerta G9/G10 y suele ser la que separa una estrategia de una racha.`;
}

function Concentration({ closed }: { closed: StatsPayload["closed"] }) {
  const trades = closed.trades ?? 0;
  if (trades < 5) {
    return null;
  }
  const share = Math.max(0, Math.min(1, closed.top5_share ?? 0));
  const without = closed.pnl_without_top5 ?? 0;
  const fragile = share > 0.5;
  return (
    <section className="card" data-concentration>
      <header className="card-header">
        <h3>Concentración del resultado</h3>
        <span className={`badge ${fragile ? "tone-bad" : "tone-good"}`}>
          {(share * 100).toFixed(0)} % en las 5 mejores
        </span>
      </header>
      <div className="concentration-track" aria-hidden="true">
        <span style={{ width: `${share * 100}%` }} />
      </div>
      <dl className="kv">
        <div className="kv-row">
          <dt>P&L total</dt>
          <dd className="mono">{formatSigned(closed.pnl_net ?? 0)}</dd>
        </div>
        <div className="kv-row">
          <dt>P&L sin las 5 mejores</dt>
          <dd className={`mono ${without >= 0 ? "tone-good" : "tone-bad"}`}>
            {formatSigned(without)}
          </dd>
        </div>
      </dl>
      <p className={fragile ? "tone-warn small" : "muted small"}>
        {concentrationNote({
          trades: closed.trades,
          wins: closed.wins,
          top5_share: closed.top5_share,
          pnl_without_top5: closed.pnl_without_top5,
        })}
      </p>
    </section>
  );
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
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
          mediana {(closed.r_median ?? 0).toFixed(2)} R · media{" "}
          {(closed.expectancy_r ?? 0).toFixed(2)} R
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
                style={{ width: `${Math.max(2, (count / peak) * 100)}%` }}
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
  const [tab, setTab] = useState<Tab>("resumen");
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [validation, setValidation] = useState<ValidationPayload | null>(null);
  const [funnel, setFunnel] = useState<FunnelPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .stats()
      .then((payload) => {
        if (!cancelled) setStats(payload as unknown as StatsPayload);
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
  }, []);

  return (
    <div className="page">
      <h2>Estadísticas</h2>
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
      {error ? <p className="tone-bad">{error}</p> : null}

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

      {tab === "resumen" ? (
        <section className="card">
          {stats ? (
            <KvPanel
              entries={toEntries(stats.closed)}
              emptyLabel="Sin operaciones cerradas"
            />
          ) : (
            <p className="empty">Cargando…</p>
          )}
        </section>
      ) : null}

      {tab === "rendimiento" && stats ? <RDistribution closed={stats.closed} /> : null}
      {tab === "rendimiento" && stats ? <Concentration closed={stats.closed} /> : null}

      {tab === "rendimiento" ? (
        <section className="card">
          <header className="card-header">
            <h3>Curva de equidad</h3>
            <span className="muted small">{stats?.equity.length ?? 0} cierres</span>
          </header>
          <EquityChart points={stats?.equity ?? []} />
          <header className="card-header underwater-head">
            <h3>Bajo el agua</h3>
            <span className="muted small">
              distancia al máximo de la cuenta · el pico siempre es 0 %
            </span>
          </header>
          <Underwater points={stats?.equity ?? []} />
          <h3>Por día</h3>
          <BreakdownTable rows={stats?.by_day ?? {}} />
        </section>
      ) : null}

      {tab === "direccion" ? (
        <section className="card">
          <BreakdownTable rows={stats?.by_side ?? {}} />
        </section>
      ) : null}

      {tab === "hora" ? (
        <section className="card">
          <BreakdownTable rows={stats?.by_hour ?? {}} />
          <h3>Por día de la semana</h3>
          <BreakdownTable rows={stats?.by_weekday ?? {}} />
        </section>
      ) : null}

      {tab === "mes" ? (
        <section className="card">
          <BreakdownTable rows={stats?.by_month ?? {}} />
        </section>
      ) : null}
    </div>
  );
}
