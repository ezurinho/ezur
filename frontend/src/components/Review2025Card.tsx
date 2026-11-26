import { useEffect, useState } from "react";

import { api } from "../api";
import type { Review2025, ReviewOpenPosition, ReviewRow } from "../types";

function money(value: number | null, signed = true): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} $`;
}

function percent(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${(value * 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} %`;
}

function ratio(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
}

function integer(value: number | null): string {
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

export function Review2025Card({ compact = false }: { compact?: boolean }) {
  const [review, setReview] = useState<Review2025 | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (!review) {
    return (
      <section className={`card review-card${compact ? " compact" : ""}`} data-review="loading">
        <header className="card-header">
          <h3>Review 2025 · perfil 15m</h3>
          <span className="badge">solo lectura</span>
        </header>
        {error ? (
          <p className="empty tone-warn">No se pudo cargar la review 2025: {error}</p>
        ) : (
          <p className="empty">Cargando la comparación de los artefactos…</p>
        )}
      </section>
    );
  }

  return (
    <section className={`card review-card${compact ? " compact" : ""}`} data-review="ready">
      <header className="card-header">
        <div>
          <h3>Review 2025 · perfil 15m</h3>
          <span className="muted small">
            {review.window.from} → {review.window.to} · artefactos de la review
          </span>
        </div>
        <span className="badge">solo lectura</span>
      </header>

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
        BTC: {review.benchmark.method} · {review.benchmark.daily_closes} cierres diarios · dataset{" "}
        <span className="mono">{review.dataset}</span>.
      </p>
    </section>
  );
}
