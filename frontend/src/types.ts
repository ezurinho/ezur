/** Mirror of server/schemas.py. Keep field names and literals identical. */

export const SNAPSHOT_VERSION = 1;

export type PhaseStatus = "pending" | "active" | "done" | "failed" | "skipped";
export type MetricFormat =
  | "number"
  | "price"
  | "pct"
  | "ratio"
  | "text"
  | "duration"
  | "boolean";
export type MetricTone = "neutral" | "good" | "bad" | "warn";
export type ZoneKind = "band" | "line" | "box" | "region";
export type MarkerKind = "entry" | "exit" | "phase" | "note" | "warning";
export type SeriesMode = "raw" | "normalized" | "percent";
export type SeriesAxis = "overlay" | "secondary";
export type EngineStatus = "stopped" | "running" | "paused" | "error";
export type RunMode = "backtest" | "dry_run" | "paper" | "live";
export type Side = "long" | "short";

export interface Quote {
  last: number | null;
  bid: number | null;
  ask: number | null;
  change: number | null;
  change_pct: number | null;
  ts: string | null;
}

export interface Instrument {
  symbol: string;
  role: "primary" | "context";
  enabled: boolean;
  tick_size: number;
  tick_value: number;
  point_value: number | null;
  currency: string;
  decimals: number;
}

export interface Phase {
  key: string;
  label: string;
  status: PhaseStatus;
  ts: string | null;
  detail: string | null;
}

export interface KvEntry {
  label: string;
  value: number | string | boolean | null;
  format: MetricFormat;
  unit: string | null;
  tone: MetricTone;
  group: string | null;
}

export interface Signal {
  key: string;
  side: Side;
  strength: number | null;
  reason: string | null;
  ts: string;
  valid_until: string | null;
  stop_price: number;
  target_price: number | null;
}

export interface Zone {
  id: string;
  kind: ZoneKind | string;
  from_ts: string;
  price_low: number;
  price_high: number;
  label: string | null;
  to_ts: string | null;
  style: Record<string, unknown>;
  active: boolean;
  source: "strategy" | "engine" | "user";
  meta: Record<string, unknown>;
}

export interface Marker {
  id: string;
  ts: string;
  price: number;
  kind: MarkerKind | string;
  side: Side | "none";
  label: string | null;
  source: "strategy" | "engine" | "user";
  meta: Record<string, unknown>;
}

export interface Candle {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface SeriesValue {
  t: string;
  v: number;
}

export interface Series {
  symbol: string;
  label: string | null;
  mode: SeriesMode;
  axis: SeriesAxis;
  visible: boolean;
  values: SeriesValue[];
}

export interface Chart {
  primary: string;
  timeframe: string;
  timeframes: string[];
  candles: Candle[];
  series: Series[];
  zones: Zone[];
  markers: Marker[];
}

export interface StrategyBlock {
  id: string;
  name: string;
  version: string;
  /** Marco de velas que consume la estrategia (no el del gráfico). */
  timeframe?: string;
  state: string;
  state_label: string;
  phases: Phase[];
  metrics: Record<string, KvEntry>;
  signal: Signal | null;
  rejection: Record<string, string> | null;
  rejections?: Record<string, number>;
}

export interface Position {
  symbol: string;
  side: Side;
  units: number;
  entry_price: number;
  stop_price: number;
  target_price: number | null;
  opened_ts: string;
  unrealized: number | null;
  r_open: number | null;
}

export interface Order {
  id: string;
  symbol: string;
  side: Side;
  units: number;
  kind: "market" | "limit";
  price: number;
  status: "pending" | "filled" | "cancelled" | "rejected";
  created_ts: string;
  stop_price: number | null;
  target_price: number | null;
  signal_key: string;
  /** Presupuesto de riesgo de la señal; el fill real puede reducirlo. */
  risk_budget?: number;
}

export interface EdgeMeasure {
  expectancy_r: number | null;
  cost_r: number | null;
  timeframe: string | null;
  scope: string;
  passes: boolean | null;
  reason: string | null;
  detail: string;
}

export interface Risk {
  equity: number;
  open_risk: number;
  daily_pnl: number;
  daily_trades: number;
  blocked: boolean;
  block_reason: string | null;
  block_count: number;
  block_detail?: string | null;
  edge?: EdgeMeasure | null;
  limits: Record<string, number>;
}

export interface Session {
  id: string;
  label: string;
  is_open: boolean;
  open_ts: string | null;
  close_ts: string | null;
  phase: "pre" | "open" | "close" | "closed";
}

export interface DataInfo {
  provider: string;
  quality: "ok" | "degraded" | "stale" | "unknown";
  last_bar_ts: string | null;
  staleness_ms: number;
  bars_available: number;
}

export interface UiHints {
  panels: string[];
  theme: "dark" | "light";
  locale: string;
}

export interface PromotionCheck {
  name: string;
  passed: boolean;
  value: number | string | null;
  threshold: string | null;
  reason: string | null;
}

export interface Promotion {
  required: boolean;
  passed: boolean;
  reason: string | null;
  mode: string;
  size_factor: number | null;
  configured_risk_pct: number | null;
  effective_risk_pct: number | null;
  pbo: number | null;
  pbo_threshold: string | null;
  dsr: number | null;
  dsr_threshold: string | null;
  wfa_oos_trades: number | null;
  wfa_folds: number | null;
  wfa_pf: number | null;
  stress_pf: number | null;
  blocking_gate: string | null;
  blocking_detail: string | null;
  blocking_value: number | string | null;
  blocking_threshold: string | null;
  checks: PromotionCheck[];
  cycle_path: string | null;
  cycle_generated_at: string | null;
  cycle_id: string | null;
}

export interface SnapshotData {
  status: EngineStatus;
  mode: RunMode;
  session: Session;
  data: DataInfo;
  instruments: Instrument[];
  quotes: Record<string, Quote>;
  chart: Chart;
  strategy: StrategyBlock;
  position: Position | null;
  orders: Order[];
  risk: Risk;
  /** Veredicto de la puerta del perfil; null si no exige promoción. */
  promotion?: Promotion | null;
  stats: Record<string, unknown>;
  day_stats: Record<string, unknown>;
  rejections: Record<string, number>;
  settings: Record<string, unknown>;
  ui: UiHints;
}

export interface SnapshotMessage {
  type: "snapshot";
  v: number;
  ts: string;
  data: SnapshotData;
}

export const PHASE_STATUSES: PhaseStatus[] = [
  "pending",
  "active",
  "done",
  "failed",
  "skipped",
];

export const ZONE_KINDS: ZoneKind[] = ["band", "line", "box", "region"];

export const MARKER_KINDS: MarkerKind[] = [
  "entry",
  "exit",
  "phase",
  "note",
  "warning",
];
