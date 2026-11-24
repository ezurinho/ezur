import { useEffect, useMemo, useState } from "react";
import { api, type CompareResponse, type BacktestRunResponse, type GateOutcome } from "../api";
import { dominantRejection, plainReason } from "../reasons";
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

/** El contador enseña todo lo guardado; la lista, solo ocho. Se dice.
 *
 * Con `more`, el número de corridas no es el total sino la última página que
 * devolvió el servidor: se dice «al menos» en vez de inventar una cifra exacta.
 */
export function historyNote(total: number, shown = 8, more = false): string | null {
  if (total <= shown && !more) return null;
  if (more) {
    return `Se muestran las ${shown} más recientes; hay al menos ${total} corridas guardadas.`;
  }
  return `Se muestran las ${shown} más recientes; hay ${total} corridas guardadas en total.`;
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
 * El profit factor sin pérdidas no tiene denominador.
 *
 * El servidor pone 1,0 como centinela cuando solo hay ganancias; pintarlo como
 * «1,00» lee como empate técnico. Se dice infinito, igual que en Estadísticas.
 */
export function pfText(metrics: Record<string, number | null | undefined>): string {
  const value = metrics.profit_factor;
  if (value === null || value === undefined) return "—";
  if ((metrics.losses ?? 0) === 0 && (metrics.wins ?? 0) > 0) return "∞";
  return value.toFixed(2);
}

export function pfTitle(metrics: Record<string, number | null | undefined>): string | undefined {
  return (metrics.losses ?? 0) === 0 && (metrics.wins ?? 0) > 0
    ? "Sin pérdidas todavía: el profit factor no tiene denominador"
    : undefined;
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
  // Si el servidor recortó la página, el largo de la lista no es el total.
  const [historyMore, setHistoryMore] = useState(false);
  const [loaded, setLoaded] = useState(false);
  // Separado del error de una corrida: un backtest fallido no significa que la
  // lista de corridas guardadas no se haya podido leer.
  const [loadError, setLoadError] = useState<string | null>(null);

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
        setHistoryMore(Boolean(runsPayload.has_more));
      })
      .catch((cause: Error) => {
        if (alive) setLoadError(cause.message);
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const counts = useMemo(
    () => (single ? gateCounts(single.validation.outcomes) : null),
    [single],
  );

  const emptyReason = useMemo(
    () => (single ? explainEmptyRun(single.trades, single.diagnostics?.rejections) : null),
    [single],
  );
  const exposureNote = useMemo(
    () => (single ? endExposureNote(single.diagnostics) : null),
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
      setHistoryMore(Boolean(runs.has_more));
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
              {!loaded ? <option value="">Leyendo datasets…</option> : null}
              {loaded && datasets.length === 0 ? (
                <option value="">
                  {loadError ? "No se pudo leer data/" : "No hay datasets en data/"}
                </option>
              ) : null}
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
              {!loaded && strategies.length === 0 ? (
                <option value="">Leyendo estrategias…</option>
              ) : null}
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
              value={
                single.metrics.win_rate == null
                  ? "—"
                  : `${(single.metrics.win_rate * 100).toFixed(1)} %`
              }
            />
            <LabMetric
              label="Profit factor"
              value={pfText(single.metrics)}
              title={pfTitle(single.metrics)}
            />
            <LabMetric
              label="Esperanza"
              value={
                single.metrics.expectancy_r == null
                  ? "—"
                  : `${single.metrics.expectancy_r.toFixed(2)} R`
              }
              tone={
                single.metrics.expectancy_r == null || single.metrics.expectancy_r === 0
                  ? undefined
                  : single.metrics.expectancy_r > 0
                    ? "good"
                    : "bad"
              }
            />
            <LabMetric
              label="Mínimo esperable (IC80)"
              value={
                single.metrics.expectancy_ci80_low == null
                  ? "—"
                  : `${single.metrics.expectancy_ci80_low.toFixed(2)} R`
              }
              tone={
                single.metrics.expectancy_ci80_low == null || single.metrics.expectancy_ci80_low === 0
                  ? undefined
                  : single.metrics.expectancy_ci80_low > 0
                    ? "good"
                    : "bad"
              }
            />
            <LabMetric
              label="Drawdown máx."
              value={
                single.metrics.max_drawdown == null
                  ? "—"
                  : formatValue(single.metrics.max_drawdown, "price")
              }
              tone={
                single.metrics.max_drawdown == null || single.metrics.max_drawdown === 0
                  ? undefined
                  : "bad"
              }
            />
          </div>

          {typeof single.metrics.fees === "number" ? (
            <p className="lab-cost muted small" data-lab-cost>
              Comisiones:{" "}
              <b className="tone-cost">{formatValue(single.metrics.fees, "price")}</b>
              {single.trades > 0 ? (
                <>
                  {" "}
                  ({(single.metrics.fees / single.trades).toFixed(2)} por operación)
                </>
              ) : null}
              {single.trades > 0 ? (
                <>
                  {typeof single.metrics.pnl_gross === "number" ? (
                    <>
                      {" · "}sin ellas el resultado iría en{" "}
                      <b
                        className={
                          single.metrics.pnl_gross > 0
                            ? "tone-good"
                            : single.metrics.pnl_gross < 0
                              ? "tone-bad"
                              : undefined
                        }
                      >
                        {formatValue(single.metrics.pnl_gross, "price")}
                      </b>
                      .
                    </>
                  ) : null}{" "}
                  El IC80 dice cuánto se puede esperar si la suerte va en contra; si cruza el cero,
                  la ventaja aún no está demostrada.
                </>
              ) : (
                <> · sin operaciones no hay coste que separar.</>
              )}
            </p>
          ) : null}

          {emptyReason ? (
            <p className="lab-empty-reason" data-lab-empty-reason>
              {emptyReason}
            </p>
          ) : null}
          {exposureNote ? (
            <p className="tone-warn small" data-lab-exposure>
              {exposureNote}
            </p>
          ) : null}

          {counts ? (
            <p className="lab-gate-summary">
              <b className={counts.pass > 0 ? "tone-good" : undefined}>{counts.pass}</b> puertas pasan ·{" "}
              <b className={counts.fail > 0 ? "tone-bad" : undefined}>{counts.fail}</b> fallan ·{" "}
              <b className={counts.pending > 0 ? "tone-warn" : undefined}>{counts.pending}</b> sin medir
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
                  <th title="Extremo bajo del intervalo de confianza al 80 % de la esperanza">
                    IC80
                  </th>
                  <th title="Comisiones pagadas y su peso por operación">Coste</th>
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
                    <tr
                      key={row.run_id}
                      className={
                        // «Mejor» solo si gana algo: resaltar la primera de
                        // cuatro perdedoras es decorar el desastre.
                        index === 0 && row.trades > 0 && (row.metrics.expectancy_r ?? 0) > 0
                          ? "best"
                          : undefined
                      }
                    >
                      <td>
                        <b>{row.strategy_id}</b>
                        <span className="muted small"> · v{row.strategy_version}</span>
                      </td>
                      <td className="mono">{row.trades}</td>
                      <td className="mono">
                        {row.metrics.win_rate == null
                          ? "—"
                          : `${(row.metrics.win_rate * 100).toFixed(0)} %`}
                      </td>
                      <td className="mono" title={pfTitle(row.metrics)}>
                        {pfText(row.metrics)}
                      </td>
                      <td
                        className={
                          // Una esperanza de 0.00 R en rojo se lee como pérdida:
                          // el empate neto de comisiones no es bueno ni malo.
                          row.trades === 0 || row.metrics.expectancy_r == null
                            ? "mono muted"
                            : row.metrics.expectancy_r > 0
                              ? "mono tone-good"
                              : row.metrics.expectancy_r < 0
                                ? "mono tone-bad"
                                : "mono"
                        }
                      >
                        {row.trades === 0
                          ? "sin operaciones"
                          : row.metrics.expectancy_r == null
                            ? "—"
                            : `${row.metrics.expectancy_r.toFixed(2)} R`}
                      </td>
                      <td
                        className={`mono ${
                          row.metrics.expectancy_ci80_low == null
                            ? "muted"
                            : (row.metrics.expectancy_ci80_low ?? 0) > 0
                              ? "tone-good"
                              : (row.metrics.expectancy_ci80_low ?? 0) < 0
                                ? "tone-bad"
                                : ""
                        }`}
                      >
                        {row.metrics.expectancy_ci80_low == null
                          ? "—"
                          : `${row.metrics.expectancy_ci80_low.toFixed(2)} R`}
                      </td>
                      <td className="mono">
                        {row.metrics.fees == null ? (
                          "—"
                        ) : (
                          <>
                            {formatValue(row.metrics.fees, "price")}
                            {row.trades > 0 ? (
                              <span className="muted small">
                                {" "}
                                · {(row.metrics.fees / row.trades).toFixed(2)}/op
                              </span>
                            ) : null}
                          </>
                        )}
                      </td>
                      <td className="mono">
                        {row.metrics.max_drawdown == null
                          ? "—"
                          : formatValue(row.metrics.max_drawdown, "price")}
                      </td>
                      <td>
                        <span className="gate-pills">
                          {/* Un 0 en verde y un 0 en rojo son la misma mentira:
                              el tono solo aparece cuando hay puertas de ese tipo. */}
                          <span className={rowCounts.pass > 0 ? "pill pill-good" : "pill"}>
                            {rowCounts.pass}
                          </span>
                          <span className={rowCounts.fail > 0 ? "pill pill-bad" : "pill"}>
                            {rowCounts.fail}
                          </span>
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
          {compare.rows.some((row) => row.trades === 0) ? (
            <div className="lab-zero-notes" data-lab-zero-notes>
              {compare.rows
                .filter((row) => row.trades === 0)
                .map((row) => (
                  <p key={row.run_id} className="muted small">
                    <b>{row.strategy_id}</b>: {explainEmptyRun(0, row.rejections)}
                  </p>
                ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="card">
        <header className="card-header">
          <h3>Corridas guardadas</h3>
          <span className="badge">{historyMore ? `${history.length}+` : history.length}</span>
        </header>
        {!loaded ? (
          <p className="empty">Leyendo las corridas guardadas…</p>
        ) : loadError ? (
          <p className="empty">No se pudieron leer las corridas guardadas: {loadError}</p>
        ) : history.length === 0 ? (
          <p className="empty">Todavía no hay backtests guardados.</p>
        ) : (
          <ul className="lab-history">
            {history.slice(0, 8).map((run) => (
              <li key={String(run.run_id)}>
                <span className="mono small">{shortId(String(run.run_id))}</span>
                <span>{formatDateTime(String(run.ts))}</span>
                <span>
                  {String(run.strategy_id ?? "—")}
                  <span className="muted small">
                    {run.trades == null ? " · — ops" : ` · ${String(run.trades)} ops`}
                  </span>
                </span>
                <span className="muted small">{String(run.run_group ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
        {history.length > 0 && historyNote(history.length, 8, historyMore) ? (
          <p className="muted small">{historyNote(history.length, 8, historyMore)}</p>
        ) : null}
      </section>
    </div>
  );
}

/**
 * Por qué una corrida terminó sin operaciones. Exportado para probarlo.
 *
 * «0 operaciones» puede significar dos cosas opuestas: la regla nunca se
 * cumplió (no hay nada que corregir en el riesgo) o el riesgo descartó todas
 * las señales (hay un tope mal puesto). Confundirlas lleva a tocar lo que no es.
 */
export function explainEmptyRun(
  trades: number,
  rejections: Record<string, number> | undefined,
): string | null {
  if (trades > 0) return null;
  const total = Object.values(rejections ?? {}).reduce(
    (sum, count) => sum + (Number.isFinite(count) ? count : 0),
    0,
  );
  const top = dominantRejection(rejections);
  if (!top) {
    return "Sin operaciones: la regla de entrada no se cumplió en ninguna vela del dataset.";
  }
  return `Sin operaciones: el riesgo descartó ${total} ${total === 1 ? "señal" : "señales"}. La que más: ${plainReason(top.code)} (${top.count} ${top.count === 1 ? "vez" : "veces"}).`;
}

export function endExposureNote(
  diagnostics: BacktestRunResponse["diagnostics"],
): string | null {
  const position = diagnostics?.open_position;
  const pending = diagnostics?.pending_orders ?? 0;
  if (!position && pending <= 0) return null;
  const parts: string[] = [];
  if (position) {
    parts.push(`una posición abierta en ${String(position.symbol ?? "un instrumento")}`);
  }
  if (pending > 0) {
    parts.push(`${pending} ${pending === 1 ? "orden pendiente" : "órdenes pendientes"}`);
  }
  return `La corrida terminó con ${parts.join(" y ")}: ese resultado no está incluido en la curva ni en las métricas.`;
}

function LabMetric({
  label,
  value,
  tone,
  title,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad";
  title?: string;
}) {
  return (
    <div className="lab-metric" title={title}>
      <span className="lab-metric-label">{label}</span>
      <b className={tone ? `tone-${tone}` : undefined}>{value}</b>
    </div>
  );
}
