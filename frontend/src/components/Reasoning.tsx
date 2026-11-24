import { buildReasoning } from "../reasoning";
import type { Reasoning as ReasoningModel, StepStatus } from "../reasoning";
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

/** El badge base ya trae borde, fondo y tipografía; solo se le pone el tono. */
const TONE_BADGE: Record<ReasoningModel["tone"], string> = {
  good: "badge tone-good",
  warn: "badge tone-warn",
  bad: "badge tone-bad",
  neutral: "badge",
};

/**
 * La tarjeta de razonamiento: la decisión, el porqué y lo que no se hizo.
 *
 * Es el patrón que usan los agentes que publican su traza —decisión, puerta de
 * riesgo con PASS/FAIL, veto explícito— con una diferencia deliberada: aquí no
 * hay ninguna frase generada. Cada línea se puede rastrear hasta un campo del
 * snapshot, y por eso el sello dice «determinista» en vez de fingir un modelo.
 *
 * El texto del bloqueo vive aquí y no en el aviso de arriba: dos frases iguales
 * seguidas se leen como un fallo. El aviso se queda con lo que solo él sabe
 * —cuándo fue el último rechazo y qué desbloquea— y esta tarjeta con el motivo.
 */
export function Reasoning({ snapshot }: { snapshot: SnapshotData }) {
  const { tone, headline, verdict, conviction, steps, veto } = buildReasoning(snapshot);

  return (
    <section className={`card reasoning tone-border-${tone}`} data-reasoning data-tone={tone}>
      <header className="card-header">
        <h3>Razonamiento</h3>
        <span className="reasoning-tags">
          <span className={TONE_BADGE[tone]}>{headline}</span>
          <span
            className="badge"
            title="Sin modelo de lenguaje: cada frase sale de un campo del snapshot"
          >
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
