import type { SnapshotData, SnapshotMessage } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${detail}`);
  }
  return (await response.json()) as T;
}

export const api = {
  status: () => request<SnapshotMessage>("/api/status"),
  health: () => request<{ status: string; version: string }>("/api/health"),
  config: () => request<Record<string, unknown>>("/api/config"),
  patchConfig: (patch: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/config", {
      method: "PUT",
      body: JSON.stringify({ patch }),
    }),
  resetConfig: () =>
    request<Record<string, unknown>>("/api/config/reset", { method: "POST" }),
  strategySchema: (id?: string) =>
    request<{
      available: string[];
      active: string;
      id: string;
      params_schema: Record<string, unknown>;
    }>(`/api/strategy/schema${id ? `?strategy_id=${encodeURIComponent(id)}` : ""}`),
  bot: (action: string) =>
    request<{ status: string }>(`/api/bot/${action}`, { method: "POST" }),
  closePosition: () =>
    request<{ closed: boolean }>("/api/position/close", { method: "POST" }),
  cancelOrders: () =>
    request<{ cancelled: boolean }>("/api/orders/cancel", { method: "POST" }),
  emergency: (on: boolean) =>
    request<{ emergency: boolean }>("/api/emergency", {
      method: on ? "POST" : "DELETE",
    }),
  trades: (limit = 100) => request<Record<string, unknown>[]>(`/api/trades?limit=${limit}`),
  events: (limit = 200) =>
    request<Record<string, unknown>[]>(`/api/events?limit=${limit}`),
  stats: () => request<{ closed: Record<string, number>; equity: { ts: string; equity: number }[] }>("/api/stats"),
  chart: (tf: string, limit = 500) =>
    request<{ primary: string; timeframe: string; candles: SnapshotData["chart"]["candles"] }>(
      `/api/chart/history?tf=${tf}&limit=${limit}`,
    ),
  validate: (path: string) =>
    request<Record<string, unknown>>("/api/data/validate", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  datasets: () => request<string[]>("/api/datasets"),
  runBacktest: (datasetPath: string) =>
    request<Record<string, unknown>>("/api/backtest/run", {
      method: "POST",
      body: JSON.stringify({ dataset_path: datasetPath }),
    }),
  backtestRuns: () => request<Record<string, unknown>>("/api/backtest/runs"),
};

export type ConnectionState = "connecting" | "open" | "closed";

export function connectSnapshotStream(
  onSnapshot: (data: SnapshotData) => void,
  onState: (state: ConnectionState) => void,
): () => void {
  let socket: WebSocket | null = null;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    onState("connecting");
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/api/ws`);
    socket.onopen = () => onState("open");
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as SnapshotMessage;
      if (message.type === "snapshot") onSnapshot(message.data);
    };
    socket.onclose = () => {
      onState("closed");
      if (!closed) retry = setTimeout(open, 2000);
    };
    socket.onerror = () => socket?.close();
  };

  open();
  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    socket?.close();
  };
}
