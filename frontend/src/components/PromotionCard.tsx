import type { Promotion, PromotionCheck } from "../types";
import { formatDateTime } from "../utils";

const GATE_LABELS: Record<string, string> = {
  evidencia_de_la_estrategia: "Evidencia de la estrategia",
  evidencia_de_la_configuracion: "Evidencia de la configuración",
  corrida_completa_hasta_el_corte: "Corrida completa hasta el corte",
  pf_fuera_de_muestra: "PF fuera de muestra",
  operaciones_fuera_de_muestra: "Operaciones fuera de muestra",
  coste_por_operacion: "Coste por operación",
  pf_con_coste_duplicado: "PF con coste duplicado",
  pbo_del_ciclo: "PBO del ciclo",
  dsr_del_ciclo: "DSR del ciclo",
};

function gateLabel(name: string): string {
  return GATE_LABELS[name] ?? name.split("_").join(" ");
}

function decimal(value: number | null | undefined, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function percent(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })} %`;
}

function checkValue(value: PromotionCheck["value"]): string {
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return value ?? "—";
}

export function PromotionCard({
  promotion,
  compact = false,
}: {
  promotion: Promotion | null;
  compact?: boolean;
}) {
  if (!promotion) {
    return (
      <section className="card promotion-card" data-promotion="none">
        <header className="card-header">
          <h3>Promoción</h3>
          <span className="badge">sin exigir</span>
        </header>
        <p className="empty">
          Este perfil no declara una puerta de promoción: no hay PBO, DSR ni WFA que
          enseñar.
        </p>
      </section>
    );
  }

  const checks = promotion.checks ?? [];
  const failed = checks.filter((check) => !check.passed);
  const blockingName = promotion.blocking_gate ?? failed[0]?.name ?? null;
  const blocking = failed.find((check) => check.name === blockingName) ?? failed[0] ?? null;
  const blockingDetail = promotion.blocking_detail ?? blocking?.reason ?? null;
  const reduced = !promotion.passed && promotion.mode === "reduce";
  const pboCheck = checks.find((check) => check.name === "pbo_del_ciclo");
  const dsrCheck = checks.find((check) => check.name === "dsr_del_ciclo");
  const status = promotion.passed ? "promovida" : reduced ? "reducida" : "bloqueada";
  const badgeClass = promotion.passed
    ? "badge badge-running"
    : reduced
      ? "badge badge-paused"
      : "badge badge-error";
  const factor =
    typeof promotion.size_factor === "number" ? percent(promotion.size_factor * 100) : null;

  return (
    <section
      className={`card promotion-card${compact ? " compact" : ""}`}
      data-promotion={promotion.passed ? "passed" : "blocked"}
    >
      <header className="card-header">
        <div>
          <h3>Promoción</h3>
          <span className="muted small">PBO · DSR · WFA del ciclo que usa el perfil</span>
        </div>
        <span className={badgeClass}>{status}</span>
      </header>

      <p className={promotion.passed ? "tone-good small" : "tone-warn small"}>
        {promotion.passed
          ? "La puerta está aprobada: el bot puede usar el riesgo completo."
          : reduced
            ? `La puerta no está aprobada: el tamaño queda reducido al ${factor ?? "—"} del riesgo configurado.`
            : "La puerta no está aprobada: el bot no arranca con este ciclo."}
      </p>

      <div className="promotion-metrics">
        <div className="promotion-metric">
          <span className="promotion-metric-label">PBO</span>
          <strong
            className={`promotion-metric-value ${
              pboCheck ? (pboCheck.passed ? "tone-good" : "tone-bad") : ""
            }`}
          >
            {decimal(promotion.pbo, 3)}
          </strong>
          <span className="promotion-metric-foot">
            {promotion.pbo_threshold ?? "sin umbral"}
          </span>
        </div>
        <div className="promotion-metric">
          <span className="promotion-metric-label">DSR</span>
          <strong
            className={`promotion-metric-value ${
              dsrCheck ? (dsrCheck.passed ? "tone-good" : "tone-bad") : ""
            }`}
          >
            {decimal(promotion.dsr, 3)}
          </strong>
          <span className="promotion-metric-foot">
            {promotion.dsr_threshold ?? "sin umbral"}
          </span>
        </div>
        <div className="promotion-metric">
          <span className="promotion-metric-label">WFA · OOS</span>
          <strong className="promotion-metric-value">
            {typeof promotion.wfa_oos_trades === "number"
              ? promotion.wfa_oos_trades.toLocaleString()
              : "—"}
          </strong>
          <span className="promotion-metric-foot">
            {typeof promotion.wfa_folds === "number"
              ? `${promotion.wfa_folds} folds`
              : "sin folds"}
            {typeof promotion.wfa_pf === "number"
              ? ` · PF ${decimal(promotion.wfa_pf, 3)}`
              : ""}
          </span>
        </div>
      </div>

      {failed.length > 0 ? (
        <div className="promotion-gates">
          <span className="promotion-gates-title">Puertas en rojo</span>
          <ul className="promotion-gate-list">
            {failed.map((check) => (
              <li key={check.name} className={check.name === blockingName ? "is-blocking" : ""}>
                <span className="promotion-gate-name">{gateLabel(check.name)}</span>
                <span className="mono">{checkValue(check.value)}</span>
                <span className="muted small">{check.threshold ?? ""}</span>
                {check.name === blockingName ? (
                  <span className="badge badge-error">bloquea</span>
                ) : null}
              </li>
            ))}
          </ul>
          {blockingDetail ? <p className="promotion-gate-detail">{blockingDetail}</p> : null}
        </div>
      ) : null}

      <div className="promotion-size">
        <span className="muted small">Riesgo configurado</span>
        <strong className="mono">{percent(promotion.configured_risk_pct)}</strong>
        <span className="muted small">→ efectivo</span>
        <strong className={`mono ${reduced ? "tone-bad" : "tone-good"}`}>
          {percent(promotion.effective_risk_pct)}
        </strong>
        {factor ? <span className="muted small">· factor {factor}</span> : null}
      </div>

      <span className="promotion-cycle" title={promotion.cycle_path ?? undefined}>
        Ciclo {promotion.cycle_id ?? "sin id"} ·{" "}
        {promotion.cycle_generated_at
          ? formatDateTime(promotion.cycle_generated_at)
          : "sin fecha"}
      </span>
    </section>
  );
}
