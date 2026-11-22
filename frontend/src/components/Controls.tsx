import { useState } from "react";
import { api } from "../api";

interface Props {
  action: "start" | "pause" | "stop" | "close" | "cancel" | "emergency";
  label: string;
}

const ENDPOINTS: Record<Props["action"], () => Promise<unknown>> = {
  start: () => api.bot("start"),
  pause: () => api.bot("pause"),
  stop: () => api.bot("stop"),
  close: () => api.closePosition(),
  cancel: () => api.cancelOrders(),
  emergency: () => api.emergency(true),
};

export function DispatchButton({ action, label }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await ENDPOINTS[action]();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="dispatch">
      <button
        type="button"
        className={`btn btn-${action}`}
        onClick={run}
        disabled={busy}
        data-action={action}
      >
        {busy ? "…" : label}
      </button>
      {error ? <span className="tone-bad small">{error}</span> : null}
    </span>
  );
}
