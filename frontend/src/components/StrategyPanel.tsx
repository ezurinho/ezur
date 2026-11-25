import type { StrategyBlock } from "../types";
import { sideLabel } from "../utils";
import { KvPanel } from "./KvPanel";
import { PhaseTimeline } from "./PhaseTimeline";

interface Props {
  strategy: StrategyBlock;
}

export function StrategyPanel({ strategy }: Props) {
  return (
    <section className="card strategy-panel" data-strategy-panel>
      <header className="card-header">
        <h3>Estado de Estrategia</h3>
        <span className="badge badge-state">
          {strategy.state_label || strategy.state}
        </span>
      </header>
      <p className="muted small">
        {strategy.name} · v{strategy.version} · {strategy.id}
        {strategy.timeframe ? " · velas de " + strategy.timeframe : ""}
      </p>
      <PhaseTimeline phases={strategy.phases} emptyLabel="Sin fases definidas" />
      <KvPanel entries={strategy.metrics} emptyLabel="Sin métricas" />
      {strategy.signal ? (
        <p className="signal" data-signal>
          {sideLabel(strategy.signal.side)} · {strategy.signal.reason ?? ""}
        </p>
      ) : null}
      {strategy.rejection ? (
        <p className="rejection" data-rejection>
          {strategy.rejection.code}: {strategy.rejection.message}
        </p>
      ) : null}
    </section>
  );
}
