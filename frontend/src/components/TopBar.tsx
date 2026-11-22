import type { ConnectionState } from "../api";
import type { SnapshotData } from "../types";

interface Props {
  snapshot: SnapshotData | null;
  connection: ConnectionState;
}

export function TopBar({ snapshot, connection }: Props) {
  const status = snapshot?.status ?? "stopped";
  const mode = snapshot?.mode ?? "paper";
  const session = snapshot?.session;
  const quality = snapshot?.data.quality ?? "unknown";
  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <strong>Trading Terminal</strong>
        <span className={`badge badge-${status}`}>{status}</span>
        <span className="badge badge-mode">{mode}</span>
      </div>
      <div className="top-bar-right">
        <span className="muted">
          {session ? `${session.label} · ${session.phase}` : "sin sesión"}
        </span>
        <span className={`badge badge-quality-${quality}`}>{quality}</span>
        <span className={`badge badge-connection-${connection}`}>{connection}</span>
      </div>
    </header>
  );
}
