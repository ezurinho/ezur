import { useState } from "react";
import { api } from "../api";
import { useToast } from "../toast";

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

const SUCCESS: Record<Props["action"], string> = {
  start: "Motor reanudado",
  pause: "Motor en pausa",
  stop: "Motor detenido",
  close: "Posición cerrada",
  cancel: "Órdenes canceladas",
  emergency: "Parada de emergencia activada",
};

export function DispatchButton({ action, label }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { push } = useToast();

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await ENDPOINTS[action]();
      push({ title: SUCCESS[action], tone: action === "emergency" ? "warn" : "good" });
    } catch (cause) {
      const message = (cause as Error).message;
      setError(message);
      push({ title: `${label}: no se pudo`, detail: message, tone: "bad" });
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
