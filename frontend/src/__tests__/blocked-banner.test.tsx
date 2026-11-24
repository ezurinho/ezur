import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SnapshotData } from "../types";

vi.mock("../api", () => ({
  api: { events: () => Promise.resolve([]) },
}));

import { BlockedBanner } from "../components/BlockedBanner";

function snapshot(blocked: boolean, reason: string | null): SnapshotData {
  return {
    risk: {
      equity: 25000,
      open_risk: 55,
      daily_pnl: 0,
      daily_trades: 2,
      blocked,
      block_reason: reason,
      block_count: blocked ? 1 : 0,
      limits: { loss_streak_cooldown_min: 45 },
    },
    position: blocked ? { symbol: "BTC" } : null,
  } as unknown as SnapshotData;
}

describe("aviso de por qué no opera", () => {
  it("tener una posición abierta no se pinta como bloqueo de riesgo", () => {
    render(<BlockedBanner snapshot={snapshot(true, "position_open")} />);
    expect(screen.getByText("Sin entradas nuevas por ahora")).toBeInTheDocument();
    expect(screen.queryByText("Bloqueo de riesgo activo")).not.toBeInTheDocument();
    expect(screen.getByText(/operación abierta se cierre/)).toBeInTheDocument();
    expect(document.querySelector('[data-why="hold"]')).not.toBeNull();
  });

  it("un freno de verdad sí se anuncia como bloqueo de riesgo", () => {
    render(<BlockedBanner snapshot={snapshot(true, "daily_loss_limit")} />);
    expect(screen.getByText("Bloqueo de riesgo activo")).toBeInTheDocument();
    expect(document.querySelector('[data-why="blocked"]')).not.toBeNull();
  });

  it("sin bloqueo dice que puede operar", () => {
    render(<BlockedBanner snapshot={snapshot(false, null)} />);
    expect(screen.getByText("Puede operar.")).toBeInTheDocument();
  });
});
