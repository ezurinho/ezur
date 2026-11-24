import type { Phase } from "../types";

interface Props {
  phases: Phase[];
  emptyLabel?: string;
}

// El color no puede ser el único portador del estado: quien no distingue el
// verde del gris necesita una marca, y el lector de pantalla, la palabra.
const MARK: Record<string, string> = {
  done: "✓",
  active: "▸",
  failed: "✕",
  skipped: "–",
  pending: "·",
};

const STATUS_WORD: Record<string, string> = {
  done: "hecha",
  active: "en curso",
  failed: "fallida",
  skipped: "saltada",
  pending: "pendiente",
};

export function PhaseTimeline({ phases, emptyLabel = "Sin fases" }: Props) {
  if (phases.length === 0) {
    return <p className="empty" data-phases-empty>{emptyLabel}</p>;
  }
  return (
    <ol className="phase-timeline">
      {phases.map((phase) => (
        <li
          key={phase.key}
          className={`phase phase-${phase.status}`}
          data-phase
          data-status={phase.status}
          data-key={phase.key}
        >
          <span className="phase-mark" aria-hidden="true">
            {MARK[phase.status] ?? "·"}
          </span>
          <span className="phase-label">
            {phase.label}
            <span className="sr-only">: {STATUS_WORD[phase.status] ?? phase.status}</span>
          </span>
          {phase.detail ? <small className="phase-detail">{phase.detail}</small> : null}
        </li>
      ))}
    </ol>
  );
}
