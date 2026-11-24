import { buildReasoning } from "../reasoning";
import type { StepStatus } from "../reasoning";
import type { SnapshotData } from "../types";

const ICON: Record<StepStatus, string> = {
  pass: "✓",
  fail: "✗",
  warn: "!",
  idle: "·",
};

const STATUS_WORD: Record<StepStatus, string> = {
  pass: "cumple",
  fail: "no cumple",
  warn: "a medias",
  idle: "sin dato",
};

interface Props {
  snapshot: SnapshotData;
}

/**
 * La tarjeta de razonamiento: la decisión, el porqué y lo que no se hizo.
 *
 * Es el patrón que usan los agentes que publican su traza —decisión, puerta de
 * riesgo con PASS/FAIL, veto explícito— con una diferencia deliberada: aquí no
 * hay ninguna frase generada. Cada línea se puede rastrear hasta un campo del
 * snapshot, y por eso el sello dice «determinista» en vez de fingir un modelo.
 */
export function Reasoning({ snapshot }: Props) {
  const reasoning = buildReasoning(snapshot);
  const { tone, headline, verdict, conviction, steps, veto } = reasoning;

  return (
    <section className={`card reasoning tone-border-${tone}`} data-reasoning data-tone={tone}>
      <header className="card-header">
        <h3>Razonamiento</h3>
        <span className="reasoning-tags">
          <span className={`badge badge-reasoning-${tone}`}>{headline}</span>
          <span className="badge badge-quiet" title="Sin modelo de lenguaje: cada frase sale de un campo del snapshot">
            determinista
          </span>
        </span>
      </header>

      <p className="reasoning-verdict" data-reasoning-verdict>
        {verdict}
      </p>

      {conviction ? (
        <div className="conviction" data-conviction={conviction.label}>
          <span className="hud-label">convicción de la señal</span>
          <span className="conviction-track" aria-hidden="true">
            <span
              className="conviction-fill"
              style={{ width: `${Math.max(4, Math.min(100, conviction.value * 100))}%` }}
            />
          </span>
          <span className="conviction-word">
            {conviction.label} · {(conviction.value * 100).toFixed(0)} %
          </span>
        </div>
      ) : null}

      <ol className="reasoning-steps" data-reasoning-steps>
        {steps.map((step) => (
          <li key={step.key} className={`reasoning-step step-${step.status}`} data-step={step.key}>
            <span className="reasoning-icon" aria-hidden="true">
              {ICON[step.status]}
            </span>
            <span className="reasoning-label">
              {step.label}
              <span className="sr-only">: {STATUS_WORD[step.status]}</span>
            </span>
            <span className="reasoning-detail">{step.detail}</span>
          </li>
        ))}
      </ol>

      {veto ? (
        <p className="reasoning-veto" data-reasoning-veto>
          {veto}
        </p>
      ) : null}
    </section>
  );
}
