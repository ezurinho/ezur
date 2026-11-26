import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BacktestRunResponse } from "../api";
import type { Review2025 } from "../types";

const api = vi.hoisted(() => ({
  review2025: vi.fn(),
  runBacktest: vi.fn(),
}));

vi.mock("../api", () => ({ api }));

import { Review2025Card } from "../components/Review2025Card";

const review = {
  window: { from: "2025-01-01", to: "2026-01-01" },
  dataset: "data/BTC_15m_2025.csv",
  config_hash: "6a599496fbf3a324",
  rows: [],
  note: "solo cerradas",
  capital_source: "25.000 $",
  benchmark: { method: "apertura a cierre", daily_closes: 365 },
} as unknown as Review2025;

const result = {
  run_id: "abc123",
  dataset_id: "d".repeat(64),
  config_hash: "6a599496fbf3a324",
  run_group: null,
  trades: 132,
  metrics: {
    win_rate: 0.523,
    profit_factor: 1.03,
    expectancy_r: 0.028,
    expectancy_ci80_low: -0.086,
    pnl_net: 107.61,
    fees: 254.22,
    max_drawdown: 947.26,
  },
  metrics_closed: {
    max_drawdown: 947.26,
  },
  verdict: "RECHAZADA",
  validation: {
    verdict: "RECHAZADA",
    failed: ["G5", "G6"],
    not_measured: [],
    outcomes: [
      {
        id: "G5",
        description: "Esperanza",
        status: "fail",
        measured: 0.028,
        threshold: "> 0",
        detail: "esperanza +0.028 R",
      },
      {
        id: "G6",
        description: "Drawdown",
        status: "fail",
        measured: 947.26,
        threshold: "< 3 %",
        detail: "DD 3.79 %",
      },
    ],
  },
  experiment_id: "exp-1",
} as unknown as BacktestRunResponse;

beforeEach(() => {
  api.review2025.mockReset();
  api.runBacktest.mockReset();
  api.review2025.mockResolvedValue(review);
});

describe("backtest 2025 desde el panel", () => {
  it("usa el dataset, la ventana, el perfil y las puertas actuales", async () => {
    api.runBacktest.mockResolvedValue(result);
    const { container } = render(<Review2025Card />);

    await waitFor(() => {
      expect(container.querySelector('[data-review="ready"]')).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Reejecutar 2025" }));

    await waitFor(() => {
      expect(api.runBacktest).toHaveBeenCalledWith("data/BTC_15m_2025.csv", {
        stress: true,
        save: true,
        start: "2025-01-01",
        end: "2026-01-01",
      });
    });
    expect(await screen.findByText("Corrida actual · perfil activo")).toBeInTheDocument();
    expect(screen.getByText("RECHAZADA")).toBeInTheDocument();
    expect(screen.getByText(/Fallan 2 puertas/)).toBeInTheDocument();
    expect(screen.getByText("G5 G6")).toBeInTheDocument();
    expect(screen.getByText("947.26 $")).toBeInTheDocument();
    expect(screen.getByText("mismo perfil que el artefacto")).toBeInTheDocument();
  });

  it("si la corrida falla, lo dice y no inventa un veredicto", async () => {
    api.runBacktest.mockRejectedValue(new Error("422: dataset inválido"));
    const { container } = render(<Review2025Card />);

    await waitFor(() => {
      expect(container.querySelector('[data-review="ready"]')).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Reejecutar 2025" }));

    expect(await screen.findByText(/no corrió: 422: dataset inválido/)).toBeInTheDocument();
    expect(screen.queryByText("Corrida actual · perfil activo")).not.toBeInTheDocument();
  });
});
