import type { Phase } from "../types";

interface Props {
  phases: Phase[];
  emptyLabel?: string;
}

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
          <span className="phase-label">{phase.label}</span>
          {phase.detail ? <small className="phase-detail">{phase.detail}</small> : null}
        </li>
      ))}
    </ol>
  );
}
