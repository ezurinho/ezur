import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SnapshotData } from "../types";

const store = vi.hoisted(() => ({ snapshot: null as unknown }));

vi.mock("../store", () => ({
  useStore: () => ({
    snapshot: store.snapshot,
    connection: "open",
    error: null,
    refresh: () => undefined,
  }),
}));

import { ToastProvider } from "../toast";
import { DashboardPage, equityFoot } from "../pages/Dashboard";

function snapshot(withPosition: boolean): SnapshotData {
  return {
    status: "running",
    mode: "paper",
    rejections: {},
    session: {
      id: "2026-11-24:CRYPTO24",
      label: "CRYPTO24",
      is_open: true,
      open_ts: "2026-11-24T00:00:00Z",
      close_ts: "2026-11-24T23:59:59Z",
      phase: "open",
    },
    data: {
      provider: "okx",
      quality: "ok",
      last_bar_ts: "2026-11-24T12:00:00Z",
      staleness_ms: 0,
      bars_available: 500,
    },
    instruments: [
      {
        symbol: "BTC",
        role: "primary",
        enabled: true,
        tick_size: 10,
        tick_value: 0.1,
        point_value: 1,
        currency: "USD",
        decimals: 2,
      },
    ],
    quotes: {
      BTC: { last: 60517.5, bid: 60517, ask: 60518, change: 10, change_pct: 0.02, ts: null },
    },
    chart: {
      primary: "BTC",
      timeframe: "5m",
      timeframes: ["5m"],
      candles: [],
      series: [],
      zones: [],
      markers: [],
    },
    strategy: {
      id: "donchian",
      name: "Donchian",
      version: "1.0.0",
      state: "scanning",
      state_label: "Esperando",
      phases: [],
      metrics: {},
      signal: null,
      rejection: null,
    },
    position: withPosition
      ? {
          symbol: "BTC",
          side: "short",
          units: 231,
          entry_price: 60657.09,
          stop_price: 60921.3143,
          target_price: 60340.0429,
          opened_ts: "2026-11-24T11:00:00Z",
          unrealized: null,
          r_open: null,
        }
      : null,
    orders: [],
    risk: {
      equity: 24510.3,
      open_risk: 61.04,
      daily_pnl: 153.9,
      daily_trades: 3,
      blocked: false,
      block_reason: null,
      block_count: 0,
      limits: {
        risk_per_trade_pct: 0.25,
        max_daily_loss_pct: 3,
        daily_loss_limit: 750,
        initial_capital: 25000,
        max_trades_per_day: 8,
        loss_streak_cooldown_min: 45,
        no_trade_after_consecutive_losses: 3,
        soft_brake_at: 600,
      },
    },
    stats: {
      equity: [
        { ts: "2026-11-24T10:00:00Z", equity: 24356.4 },
        { ts: "2026-11-24T11:30:00Z", equity: 24510.3 },
      ],
      closed: { trades: 2, wins: 1, losses: 1, profit_factor: 1.5, expectancy_r: 0.2 },
    },
    day_stats: { trades: 3, wins: 3, losses: 0, pnl: 153.9, consecutive_losses: 0 },
    settings: {},
    ui: { panels: [], theme: "dark", locale: "es" },
  };
}

function equityTooltip(): HTMLElement {
  const button = screen.getByRole("button", { name: "Qué es Equidad" });
  const id = button.getAttribute("aria-describedby");
  const tooltip = id ? document.getElementById(id) : null;
  if (!tooltip) throw new Error("La equidad no tiene explicación");
  return tooltip;
}

beforeEach(() => {
  store.snapshot = snapshot(true);
});

describe("equidad realizada", () => {
  it("el pie dice que una posición abierta queda fuera de la cifra", () => {
    expect(equityFoot(0, false)).toBe("0 cierres · solo cerradas");
    expect(equityFoot(1, true)).toBe("1 cierre · sin la abierta");
  });

  it("la explicación no promete incluir el resultado flotante", () => {
    render(
      <ToastProvider>
        <DashboardPage />
      </ToastProvider>,
    );
    const tooltip = equityTooltip();
    expect(tooltip).toHaveTextContent("operaciones cerradas");
    expect(tooltip).toHaveTextContent("no calcula su resultado flotante");
    expect(tooltip).not.toHaveTextContent("incluido lo que está en operaciones abiertas");
    expect(screen.getByText("2 cierres · sin la abierta")).toBeInTheDocument();
  });

  it("sin posición abierta el pie no sugiere que falte algo por sumar", () => {
    store.snapshot = snapshot(false);
    render(
      <ToastProvider>
        <DashboardPage />
      </ToastProvider>,
    );
    expect(screen.getByText("2 cierres · solo cerradas")).toBeInTheDocument();
    expect(screen.queryByText(/sin la abierta/)).not.toBeInTheDocument();
  });
});
