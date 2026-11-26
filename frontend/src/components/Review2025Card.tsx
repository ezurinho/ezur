import { useEffect, useState } from "react";

import { api, type BacktestRunResponse } from "../api";
import type { Review2025, ReviewOpenPosition, ReviewRow } from "../types";

const FALLBACK_DATASET = "data/BTC_15m_2025.csv";
const FALLBACK_WINDOW = { from: "2025-01-01", to: "2026-01-01" };

function money(value: number | null | undefined, signed = true): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} $`;
}

function percent(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${(value * 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} %`;
}

function ratio(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
}

function integer(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function price(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function utc(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const day = date.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });
  const time = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${day} ${time} UTC`;
}

function sourceName(source: string): string {
  const [path, ...suffix] = source.split("·");
  const name = path.trim().split("/").pop() ?? source;
  return suffix.length > 0 ? `${name} · ${suffix.join("·").trim()}` : name;
}

function tone(value: number | null): string {
  if (typeof value !== "number" || value === 0) return "";
  return value > 0 ? "tone-good" : "tone-bad";
}

function verdictTone(verdict: string): string {
  if (verdict === "APROBADA") return "tone-good";
  if (verdict === "RECHAZADA") return "tone-bad";
  return "tone-warn";
}

function signedR(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)} R`;
}

function RunMetric({
  label,
  value,
  tone: metricTone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="lab-metric">
      <span className="lab-metric-label">{label}</span>
      <b className={metricTone ? `tone-${metricTone}` : undefined}>{value}</b>
    </div>
  );
}

function PositionCell({ position }: { position: ReviewOpenPosition | null }) {
  if (!position) return <span className="review-position muted">ninguna</span>;

  if (position.kind === "spot") {
    return (
      <span className="review-position">
        <strong>BTC spot mantenido</strong>
        <span>entrada {price(position.entry_price)} · abierta {utc(position.opened_ts)}</span>
        <span>sin stop ni objetivo · hasta el corte</span>
      </span>
    );
  }

  const side =
    position.side === "long" ? "Long" : position.side === "short" ? "Short" : position.side;
  return (
    <span className="review-position">
      <strong>
        {side} {integer(position.units)} u
      </strong>
      <span>
        entrada {price(position.entry_price)} · abierta {utc(position.opened_ts)}
      </span>
      <span>
        stop {price(position.stop_price)} · objetivo {price(position.target_price)}
      </span>
      {position.entry_fees !== null ? (
        <span>fees de entrada {money(position.entry_fees, false)}</span>
      ) : null}
    </span>
  );
}

function ReviewRowView({ row }: { row: ReviewRow }) {
  const pnlText = row.pnl_usd !== null ? money(row.pnl_usd) : percent(row.return_pct);
  const pnlFoot = row.pnl_usd !== null ? percent(row.return_pct) : row.note;
  return (
    <tr>
      <td>
        <span className="review-run">{row.label}</span>
        <span className="review-source" title={row.source}>
          {sourceName(row.source)}
        </span>
      </td>
      <td className="num">{integer(row.trades)}</td>
      <td className="num">
        <span className={`review-value ${tone(row.return_pct)}`}>{pnlText}</span>
        {pnlFoot ? <span className="review-foot">{pnlFoot}</span> : null}
      </td>
      <td className="num">
        <span className="review-value">{ratio(row.profit_factor)}</span>
        {row.fees !== null ? <span className="review-foot">fees {money(row.fees, false)}</span> : null}
      </td>
      <td className="num">
        <span className={`review-value ${row.drawdown_pct ? "tone-bad" : ""}`}>
          {percent(row.drawdown_pct)}
        </span>
        {row.drawdown_usd !== null ? (
          <span className="review-foot">{money(row.drawdown_usd, false)}</span>
        ) : null}
      </td>
      <td>
        <PositionCell position={row.open_position} />
      </td>
    </tr>
  );
}

function RunSummary({
  run,
  dataset,
  window,
  artifactHash,
}: {
  run: BacktestRunResponse;
  dataset: string;
  window: { from: string; to: string };
  artifactHash: string | null;
}) {
  const metrics = run.metrics;
  // G6 y el informe del CLI miden el DD sobre operaciones cerradas. El
  // endpoint devuelve esa vista aparte porque `metrics` es pico-valle marked
  // to market y no es el número que usa la puerta.
  const drawdown = run.metrics_closed?.max_drawdown ?? metrics.max_drawdown;
  const failed = run.validation.outcomes.filter((gate) => gate.status === "fail");
  const notMeasured = run.validation.outcomes.filter(
    (gate) => gate.status === "not_measured",
  );
  const sameProfile = artifactHash !== null && run.config_hash === artifactHash;
  const expectancyTone =
    typeof metrics.expectancy_r !== "number" || metrics.expectancy_r === 0
      ? undefined
      : metrics.expectancy_r > 0
        ? "good"
        : "bad";

  return (
    <section className="review-run-panel" data-review-run-result>
      <header className="review-run-head">
        <div>
          <b>Corrida actual · perfil activo</b>
          <span className="muted small">
            {window.from} → {window.to} · <span className="mono">{dataset}</span>
          </span>
        </div>
        <span className={`badge ${verdictTone(run.verdict)}`}>{run.verdict}</span>
      </header>

      <div className="lab-metrics">
        <RunMetric label="Operaciones" value={integer(run.trades)} />
        <RunMetric
          label="Acierto"
          value={
            typeof metrics.win_rate === "number"
              ? `${(metrics.win_rate * 100).toFixed(1)} %`
              : "—"
          }
        />
        <RunMetric label="Profit factor" value={ratio(metrics.profit_factor)} />
        <RunMetric
          label="Esperanza"
          value={signedR(metrics.expectancy_r)}
          tone={expectancyTone}
        />
        <RunMetric label="IC80 inferior" value={signedR(metrics.expectancy_ci80_low)} />
        <RunMetric label="P&L neto" value={money(metrics.pnl_net)} />
        <RunMetric label="Fees" value={money(metrics.fees, false)} />
        <RunMetric label="Drawdown cerradas" value={money(drawdown, false)} />
      </div>

      <p className="review-run-gates">
        {failed.length > 0 ? (
          <>
            <b className="tone-bad">Fallan {failed.length} puertas:</b>{" "}
            <span className="mono">{failed.map((gate) => gate.id).join(" ")}</span>
          </>
        ) : (
          <b className="tone-good">Pasan todas las puertas medidas.</b>
        )}
        {notMeasured.length > 0 ? (
          <span className="muted">
            {" "}
            · sin medir: <span className="mono">{notMeasured.map((gate) => gate.id).join(" ")}</span>
          </span>
        ) : null}
      </p>

      {failed.length > 0 ? (
        <ul className="review-failed-gates">
          {failed.map((gate) => (
            <li key={gate.id}>
              <b>{gate.id}</b> <span>{gate.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="review-meta">
        config <span className="mono">{run.config_hash}</span> ·{" "}
        {sameProfile ? (
          <span className="tone-good">mismo perfil que el artefacto</span>
        ) : (
          <span className="tone-warn">perfil actual distinto del artefacto</span>
        )}{" "}
        · corrida <span className="mono">{run.run_id}</span> guardada en Laboratorio.
      </p>
    </section>
  );
}

export function Review2025Card({ compact = false }: { compact?: boolean }) {
  const [review, setReview] = useState<Review2025 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<BacktestRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .review2025()
      .then((payload) => {
        if (!alive) return;
        setReview(payload);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (alive) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      alive = false;
    };
  }, []);

  const dataset = review?.dataset ?? FALLBACK_DATASET;
  const window = review?.window ?? FALLBACK_WINDOW;
  const artifactHash = review?.config_hash ?? null;

  const rerun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const result = await api.runBacktest(dataset, {
        stress: true,
        save: true,
        start: window.from,
        end: window.to,
      });
      setRun(result);
    } catch (reason) {
      setRunError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  };

  return (
    <section
      className={`card review-card${compact ? " compact" : ""}`}
      data-review={review ? "ready" : error ? "error" : "loading"}
    >
      <header className="card-header">
        <div>
          <h3>Backtest 2025 · perfil 15m</h3>
          <span className="muted small">
            {window.from} → {window.to} · perfil y puertas actuales
          </span>
        </div>
        <span className="badge">2025</span>
      </header>

      <div className="review-actions">
        <button
          type="button"
          className="btn btn-start"
          onClick={rerun}
          disabled={running}
          data-review-run
        >
          {running ? "Ejecutando 2025…" : "Reejecutar 2025"}
        </button>
        <span className="muted small">
          {running
            ? "Cuatro pasadas: resultado, coste ×2 y determinismo. Puede tardar."
            : "Incluye G8 y G2: cuatro pasadas en total."}
        </span>
      </div>

      {runError ? (
        <p className="empty tone-bad" data-review-run-error>
          El backtest de 2025 no corrió: {runError}
        </p>
      ) : null}

      {run ? (
        <RunSummary run={run} dataset={dataset} window={window} artifactHash={artifactHash} />
      ) : null}

      {!review ? (
        error ? (
          <p className="empty tone-warn">
            No se pudo cargar la comparación guardada: {error}. Aun así puedes reejecutar el
            backtest con la ventana y el dataset por defecto.
          </p>
        ) : (
          <p className="empty">Cargando la comparación de los artefactos…</p>
        )
      ) : (
        <>
          <div className="review-table-wrap">
            <table className="review-table">
              <thead>
                <tr>
                  <th scope="col">Corrida</th>
                  <th scope="col">Ops</th>
                  <th scope="col">P&amp;L</th>
                  <th scope="col">PF</th>
                  <th scope="col">Drawdown</th>
                  <th scope="col">Posición abierta</th>
                </tr>
              </thead>
              <tbody>
                {review.rows.map((row) => (
                  <ReviewRowView key={row.id} row={row} />
                ))}
              </tbody>
            </table>
          </div>

          <p className="review-meta">
            {review.note} Porcentajes sobre {review.capital_source}.
          </p>
          <p className="review-meta">
            BTC: {review.benchmark.method} · {review.benchmark.daily_closes} cierres diarios ·
            dataset <span className="mono">{review.dataset}</span>.
          </p>
        </>
      )}
    </section>
  );
}
