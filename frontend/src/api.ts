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

export interface TradeQuery {
  limit?: number;
  offset?: number;
  mode?: string;
  side?: string;
  start?: string;
  end?: string;
}

function tradeQuery(params: TradeQuery, withLimit = false): string {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  else if (withLimit) query.set("limit", "200");
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  if (params.mode) query.set("mode", params.mode);
  if (params.side) query.set("side", params.side);
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  return query.toString();
}

export const api = {
  status: () => request<SnapshotMessage>("/api/status"),
  funnel: () =>
    request<{
      stages: Record<string, number>;
      verdicts: Record<string, number>;
      survival_rate: number;
      by_strategy: Record<string, { experiments: number; verdicts: Record<string, number> }>;
    }>("/api/funnel"),
  health: () => request<{ status: string; version: string }>("/api/health"),
  alerts: () =>
    request<{
      enabled: boolean;
      reason?: string;
      config_enabled?: boolean;
      min_level?: string;
      url_configured?: boolean;
      dedupe_window_s?: number;
      queued?: number;
      sent?: number;
      failed?: number;
      dropped?: number;
      deduped?: number;
      filtered?: number;
    }>("/api/alerts"),
  config: () => request<Record<string, unknown>>("/api/config"),
  patchConfig: (patch: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/config", {
      method: "PUT",
      body: JSON.stringify({ patch }),
    }),
  statsResetPreview: () =>
    request<{ trades: number; backtests: number; events: number }>("/api/stats/reset/preview"),
  resetStats: (includeBacktests = false) =>
    request<{ deleted: Record<string, number> }>("/api/stats/reset", {
      method: "POST",
      body: JSON.stringify({ include_backtests: includeBacktests }),
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
  trades: (params: TradeQuery = {}) =>
    request<Record<string, unknown>[]>(`/api/trades?${tradeQuery(params, true)}`),
  tradesCsvUrl: (params: TradeQuery = {}) => {
    const query = tradeQuery(params);
    return `/api/trades/export.csv${query ? `?${query}` : ""}`;
  },
  events: (limit = 200) =>
    request<Record<string, unknown>[]>(`/api/events?limit=${limit}`),
  stats: () => request<Record<string, unknown>>("/api/stats"),
  validation: () =>
    request<{
      verdict: string;
      failed: string[];
      not_measured: string[];
      outcomes: {
        id: string;
        description: string;
        status: string;
        measured: number | null;
        threshold: string;
        detail: string;
      }[];
    }>("/api/validation"),
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
  runBacktest: (datasetPath: string, options: { stress?: boolean; save?: boolean } = {}) =>
    request<BacktestRunResponse>("/api/backtest/run", {
      method: "POST",
      body: JSON.stringify({
        dataset_path: datasetPath,
        stress: options.stress ?? true,
        save: options.save ?? true,
      }),
    }),
  backtestStrategies: () =>
    request<{ active: string; items: { id: string; version: string; params: Record<string, unknown> }[] }>(
      "/api/backtest/strategies",
    ),
  compareBacktests: (datasetPath: string, strategies: string[]) =>
    request<CompareResponse>("/api/backtest/compare", {
      method: "POST",
      body: JSON.stringify({ dataset_path: datasetPath, strategies }),
    }),
  backtestRuns: () => request<Record<string, unknown>>("/api/backtest/runs"),
  alertsTest: () =>
    request<{ sent: boolean; reason: string | null; config_enabled?: boolean }>("/api/alerts/test", {
      method: "POST",
    }),
};

export interface GateOutcome {
  id: string;
  description: string;
  status: string;
  measured: number | null;
  threshold: string;
  detail: string;
}

export interface ValidationReport {
  verdict: string;
  failed: string[];
  not_measured: string[];
  outcomes: GateOutcome[];
}

export interface CompareRow {
  run_id: string;
  strategy_id: string;
  strategy_version: string;
  dataset_id: string;
  run_group: string;
  verdict: string;
  trades: number;
  gates: ValidationReport;
  metrics: Record<string, number | null>;
}

export interface CompareResponse {
  dataset_id: string;
  run_group: string;
  rows: CompareRow[];
}

export interface BacktestRunResponse {
  run_id: string;
  dataset_id: string;
  config_hash: string;
  run_group: string | null;
  trades: number;
  metrics: Record<string, number>;
  verdict: string;
  validation: ValidationReport;
  experiment_id: string;
}

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
