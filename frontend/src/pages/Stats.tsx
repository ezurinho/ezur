import { useEffect, useState } from "react";
import { EquityChart } from "../components/EquityChart";
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
  closed: Record<string, number>;
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

export function StatsPage() {
  const [tab, setTab] = useState<Tab>("resumen");
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [validation, setValidation] = useState<ValidationPayload | null>(null);
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

      {tab === "rendimiento" ? (
        <section className="card">
          <header className="card-header">
            <h3>Curva de equidad</h3>
            <span className="muted small">{stats?.equity.length ?? 0} cierres</span>
          </header>
          <EquityChart points={stats?.equity ?? []} />
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
