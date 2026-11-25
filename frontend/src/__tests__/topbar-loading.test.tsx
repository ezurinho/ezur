import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SnapshotData } from "../types";

vi.mock("../api", () => ({
  // Nunca resuelve: la comprobación de versión no aporta nada aquí y su
  // `setState` fuera de `act` ensuciaría la salida del test.
  api: { update: () => new Promise(() => undefined) },
}));

import { TopBar } from "../components/TopBar";
import { UiModeProvider } from "../mode";
import { ThemeProvider } from "../theme";

function renderBar(snapshot: SnapshotData | null) {
  return render(
    <ThemeProvider>
      <UiModeProvider>
        <TopBar snapshot={snapshot} connection="connecting" onOpenPalette={() => undefined} />
      </UiModeProvider>
    </ThemeProvider>,
  );
}

function loaded(): SnapshotData {
  return {
    status: "running",
    mode: "paper",
    session: null,
    data: {
      provider: "okx",
      quality: "ok",
      last_bar_ts: null,
      staleness_ms: null,
      bars_available: 500,
    },
    instruments: [],
    quotes: {},
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
    position: null,
    orders: [],
    risk: {
      equity: 25000,
      open_risk: 0,
      daily_pnl: 0,
      daily_trades: 0,
      blocked: false,
      block_reason: null,
      block_count: 0,
      limits: {},
    },
    stats: { equity: [], closed: { trades: 0, wins: 0, losses: 0, profit_factor: null, expectancy_r: null } },
    day_stats: { trades: 0, wins: 0, losses: 0, pnl: 0, consecutive_losses: 0 },
    settings: {},
    ui: { panels: [], theme: "dark", locale: "es" },
  } as unknown as SnapshotData;
}

describe("barra superior sin primer estado", () => {
  it("no afirma «stopped» ni «paper» antes de saberlo", () => {
    renderBar(null);
    expect(screen.queryByText("stopped")).not.toBeInTheDocument();
    expect(screen.queryByText("paper")).not.toBeInTheDocument();
    expect(screen.queryByText("sin sesión")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(5);
  });

  it("con estado recibido enseña el estado real y la ausencia de sesión", () => {
    renderBar(loaded());
    expect(screen.getByText("corriendo")).toBeInTheDocument();
    expect(screen.getByText("paper")).toBeInTheDocument();
    expect(screen.getByText("sin sesión")).toBeInTheDocument();
  });
});
