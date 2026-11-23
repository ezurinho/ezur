import { useEffect, useMemo, useState } from "react";
import { api, type CompareResponse, type BacktestRunResponse, type GateOutcome } from "../api";
import { useToast } from "../toast";
import { formatDateTime, formatValue } from "../utils";

interface StrategyInfo {
  id: string;
  version: string;
}

type Busy = "idle" | "single" | "compare";

const GATE_STATUS_LABEL: Record<string, string> = {
  pass: "pasa",
  fail: "falla",
  not_measured: "sin medir",
  skipped: "no aplica",
};

/** Un veredicto sin el motivo es una opinión: siempre se enseña qué puerta falló. */
export function failedGates(outcomes: GateOutcome[]): GateOutcome[] {
  return outcomes.filter((gate) => gate.status === "fail");
}

export function gateCounts(outcomes: GateOutcome[]) {
  return outcomes.reduce(
    (acc, gate) => {
      if (gate.status === "pass") acc.pass += 1;
      else if (gate.status === "fail") acc.fail += 1;
      else acc.pending += 1;
      return acc;
    },
    { pass: 0, fail: 0, pending: 0 },
  );
}

function toneForVerdict(verdict: string): string {
  if (verdict === "APROBADA") return "tone-good";
  if (verdict === "RECHAZADA") return "tone-bad";
  return "tone-warn";
}

function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "—";
}

/**
 * Laboratorio: probar y comparar estrategias sin tocar el motor que opera.
 *
 * Corre contra datasets guardados (`data/`), no contra el feed vivo. Es la
 * diferencia entre experimentar y cambiarle la estrategia a una posición
 * abierta: aquí nada de lo que se pulse altera la sesión en curso.
 */
export function LabPage() {
  const { push } = useToast();
  const [datasets, setDatasets] = useState<string[]>([]);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [dataset, setDataset] = useState("");
  const [strategy, setStrategy] = useState("");
  const [stress, setStress] = useState(false);
  const [busy, setBusy] = useState<Busy>("idle");
  const [single, setSingle] = useState<BacktestRunResponse | null>(null);
  const [compare, setCompare] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    let alive = true;
    Promise.all([api.datasets(), api.backtestStrategies(), api.backtestRuns()])
      .then(([datasetsPayload, strategiesPayload, runsPayload]) => {
        if (!alive) return;
        setDatasets(datasetsPayload);
        setStrategies(strategiesPayload.items);
        setDataset(datasetsPayload[0] ?? "");
        setStrategy(strategiesPayload.active ?? strategiesPayload.items[0]?.id ?? "");
        setHistory((runsPayload.runs as Record<string, unknown>[]) ?? []);
      })
      .catch((cause: Error) => {
        if (alive) setError(cause.message);
      });
    return () => {
      alive = false;
    };
  }, []);

  const counts = useMemo(
    () => (single ? gateCounts(single.validation.outcomes) : null),
    [single],
  );

  const runSingle = async () => {
    if (!dataset) return;
    setBusy("single");
    setError(null);
    setCompare(null);
    try {
      const result = await api.runBacktest(dataset, { stress, save: true });
      setSingle(result);
      push({
        title: `Backtest ${result.verdict.toLowerCase()}`,
        detail: `${result.trades} operaciones sobre ${shortId(result.dataset_id)} · corrida ${result.run_id}`,
        tone: result.verdict === "APROBADA" ? "good" : result.verdict === "RECHAZADA" ? "bad" : "warn",
      });
      const runs = await api.backtestRuns();
      setHistory((runs.runs as Record<string, unknown>[]) ?? []);
    } catch (cause) {
      const detail = (cause as Error).message;
      setError(detail);
      push({ title: "El backtest no corrió", detail, tone: "bad" });
    } finally {
      setBusy("idle");
    }
  };

  const runCompare = async () => {
    if (!dataset || strategies.length === 0) return;
    setBusy("compare");
    setError(null);
    setSingle(null);
    try {
      const result = await api.compareBacktests(
        dataset,
        strategies.map((item) => item.id),
      );
      setCompare(result);
      push({
        title: `Comparadas ${result.rows.length} estrategias`,
        detail: `Mismo dataset ${shortId(result.dataset_id)} · grupo ${result.run_group}`,
        tone: "info",
      });
    } catch (cause) {
      const detail = (cause as Error).message;
      setError(detail);
      push({ title: "La comparación no corrió", detail, tone: "bad" });
    } finally {
      setBusy("idle");
    }
  };

  return (
    <div className="page lab-page">
      <h2 className="page-title">
        Laboratorio
        <span className="muted small page-sub">datos guardados · no toca la sesión viva</span>
      </h2>

      <section className="card lab-setup">
        <div className="lab-controls">
          <label className="lab-field">
            <span>Dataset</span>
            <select value={dataset} onChange={(event) => setDataset(event.target.value)} data-lab-dataset>
              {datasets.length === 0 ? <option value="">No hay datasets en data/</option> : null}
              {datasets.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="lab-field">
            <span>Estrategia (corrida simple)</span>
            <select value={strategy} onChange={(event) => setStrategy(event.target.value)} data-lab-strategy>
              {strategies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} · v{item.version}
                </option>
              ))}
            </select>
          </label>

          <label className="lab-check">
            <input type="checkbox" checked={stress} onChange={(event) => setStress(event.target.checked)} />
            <span>
              Medir G8 y G2
              <small>costes ×2 y determinismo: tres corridas en vez de una</small>
            </span>
          </label>
        </div>

        <div className="button-row">
          <button
            type="button"
            className="btn btn-start"
            onClick={runSingle}
            disabled={!dataset || busy !== "idle"}
            data-lab-run
          >
            {busy === "single" ? "Corriendo…" : "Ejecutar backtest"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={runCompare}
            disabled={!dataset || strategies.length === 0 || busy !== "idle"}
            data-lab-compare
          >
            {busy === "compare" ? "Comparando…" : `Comparar ${strategies.length} estrategias`}
          </button>
          {error ? <span className="tone-bad small">{error}</span> : null}
        </div>
      </section>

      {busy !== "idle" ? (
        <div className="card lab-running" aria-live="polite">
          <span className="lab-spinner" aria-hidden="true" />
          <div>
            <b>{busy === "single" ? "Corriendo el backtest…" : "Comparando estrategias…"}</b>
            <p className="muted small">
              {stress && busy === "single"
                ? "Incluye la corrida de costes ×2 y la de determinismo: tarda el triple."
                : "Se ejecuta sobre el dataset elegido, no sobre el mercado en vivo."}
            </p>
          </div>
        </div>
      ) : null}

      {single ? (
        <section className="card lab-result" data-lab-result>
          <header className="card-header">
            <h3>Resultado</h3>
            <span className={`badge ${toneForVerdict(single.verdict)}`}>{single.verdict}</span>
          </header>

          <div className="lab-ids">
            <span>
              corrida <b className="mono">{single.run_id}</b>
            </span>
            <span>
              dataset <b className="mono">{shortId(single.dataset_id)}</b>
            </span>
            <span>
              config <b className="mono">{single.config_hash}</b>
            </span>
          </div>

          <div className="lab-metrics">
            <LabMetric label="Operaciones" value={String(single.trades)} />
            <LabMetric
              label="Acierto"
              value={`${((single.metrics.win_rate ?? 0) * 100).toFixed(1)} %`}
            />
            <LabMetric label="Profit factor" value={(single.metrics.profit_factor ?? 0).toFixed(2)} />
            <LabMetric
              label="Esperanza"
              value={`${(single.metrics.expectancy_r ?? 0).toFixed(2)} R`}
              tone={(single.metrics.expectancy_r ?? 0) > 0 ? "good" : "bad"}
            />
            <LabMetric
              label="Drawdown máx."
              value={formatValue(single.metrics.max_drawdown ?? 0, "price")}
              tone="bad"
            />
          </div>

          {counts ? (
            <p className="lab-gate-summary">
              <b className="tone-good">{counts.pass}</b> puertas pasan ·{" "}
              <b className="tone-bad">{counts.fail}</b> fallan ·{" "}
              <b className="tone-warn">{counts.pending}</b> sin medir
              {single.validation.not_measured.length > 0 ? (
                <span className="muted">
                  {" "}
                  ({single.validation.not_measured.join(", ")} requieren otra corrida)
                </span>
              ) : null}
            </p>
          ) : null}

          <ul className="gate-list">
            {single.validation.outcomes.map((gate) => (
              <li key={gate.id} className={`gate gate-${gate.status}`}>
                <span className="gate-id">{gate.id}</span>
                <span className="gate-status">{GATE_STATUS_LABEL[gate.status] ?? gate.status}</span>
                <span className="gate-desc">{gate.description}</span>
                <span className="gate-detail muted">{gate.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {compare ? (
        <section className="card lab-compare" data-lab-compare>
          <header className="card-header">
            <h3>Comparación</h3>
            <span className="badge">{compare.run_group}</span>
          </header>
          <p className="muted small">
            Mismo dataset ({shortId(compare.dataset_id)}), mismas velas, mismos costes. Ordenado por
            esperanza en R. La primera fila no es una recomendación: mira qué puertas falla.
          </p>
          <div className="lab-table-wrap">
            <table className="lab-table">
              <thead>
                <tr>
                  <th>Estrategia</th>
                  <th>Ops</th>
                  <th>Acierto</th>
                  <th>PF</th>
                  <th>Esperanza</th>
                  <th>DD</th>
                  <th>Puertas</th>
                  <th>Veredicto</th>
                </tr>
              </thead>
              <tbody>
                {compare.rows.map((row, index) => {
                  const rowCounts = gateCounts(row.gates.outcomes);
                  const failed = failedGates(row.gates.outcomes).map((gate) => gate.id);
                  return (
                    <tr key={row.run_id} className={index === 0 ? "best" : undefined}>
                      <td>
                        <b>{row.strategy_id}</b>
                        <span className="muted small"> · v{row.strategy_version}</span>
                      </td>
                      <td className="mono">{row.trades}</td>
                      <td className="mono">{((row.metrics.win_rate ?? 0) * 100).toFixed(0)} %</td>
                      <td className="mono">{(row.metrics.profit_factor ?? 0).toFixed(2)}</td>
                      <td
                        className={`mono ${(row.metrics.expectancy_r ?? 0) > 0 ? "tone-good" : "tone-bad"}`}
                      >
                        {(row.metrics.expectancy_r ?? 0).toFixed(2)} R
                      </td>
                      <td className="mono">{formatValue(row.metrics.max_drawdown ?? 0, "price")}</td>
                      <td>
                        <span className="gate-pills">
                          <span className="pill pill-good">{rowCounts.pass}</span>
                          <span className="pill pill-bad">{rowCounts.fail}</span>
                          {failed.length > 0 ? (
                            <span className="muted small">{failed.join(" ")}</span>
                          ) : null}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${toneForVerdict(row.verdict)}`}>{row.verdict}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="card">
        <header className="card-header">
          <h3>Corridas guardadas</h3>
          <span className="badge">{history.length}</span>
        </header>
        {history.length === 0 ? (
          <p className="empty">Todavía no hay backtests guardados.</p>
        ) : (
          <ul className="lab-history">
            {history.slice(0, 8).map((run) => {
              const payload = (run.payload ?? {}) as Record<string, unknown>;
              return (
                <li key={String(run.run_id)}>
                  <span className="mono small">{shortId(String(run.run_id))}</span>
                  <span>{formatDateTime(String(run.ts))}</span>
                  <span>{String(payload.strategy_id ?? "—")}</span>
                  <span className="muted small">{String(payload.run_group ?? "")}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function LabMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="lab-metric">
      <span className="lab-metric-label">{label}</span>
      <b className={tone ? `tone-${tone}` : undefined}>{value}</b>
    </div>
  );
}
