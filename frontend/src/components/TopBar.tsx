import type { ConnectionState } from "../api";
import type { SnapshotData } from "../types";
import { useClock } from "./Sparkline";

interface Props {
  snapshot: SnapshotData | null;
  connection: ConnectionState;
}

function money(value: number, signed = false): string {
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function TopBar({ snapshot, connection }: Props) {
  const status = snapshot?.status ?? "stopped";
  const mode = snapshot?.mode ?? "paper";
  const session = snapshot?.session;
  const quality = snapshot?.data.quality ?? "unknown";
  const equity = snapshot?.risk.equity ?? 0;
  const dailyPnl = snapshot?.risk.daily_pnl ?? 0;
  const now = useClock();

  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 17.5 9 9l4.2 5.2L16 8.5l4 9"
                stroke="#37e0d0"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span>
            <span className="brand-name">Trading Terminal</span>
            <span className="brand-sub">mission control</span>
          </span>
        </div>

        <div className="hud-group">
          <span className={`led led-${status}`} aria-hidden="true" />
          <span className="hud-value">{status}</span>
        </div>

        <span className="badge badge-mode">{mode}</span>
        <span className="hud-sep" aria-hidden="true" />
        <div className="hud-group">
          <span className="hud-label">equity</span>
          <span className="hud-value hud-value-lg">{money(equity)}</span>
        </div>
        <div className="hud-group">
          <span className="hud-label">p&amp;l día</span>
          <span
            className={`hud-value hud-value-lg ${dailyPnl > 0 ? "tone-good" : dailyPnl < 0 ? "tone-bad" : ""}`}
          >
            {money(dailyPnl, true)}
          </span>
        </div>
      </div>

      <div className="top-bar-right">
        <div className="hud-group">
          <span className="hud-label">sesión</span>
          <span className="hud-value">
            {session ? `${session.label} · ${session.phase}` : "sin sesión"}
          </span>
        </div>
        <span className={`badge badge-quality-${quality}`}>{quality}</span>
        <span className={`badge badge-connection-${connection}`}>
          <span className={`led led-${connection === "open" ? "running" : "stopped"}`} aria-hidden="true" />
          {connection}
        </span>
        <span className="hud-sep" aria-hidden="true" />
        <span className="hud-clock" aria-label="hora local">
          {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
      </div>
    </header>
  );
}
