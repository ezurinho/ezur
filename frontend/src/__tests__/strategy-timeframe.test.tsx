import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { StrategyBlock } from "../types";

import { StrategyPanel } from "../components/StrategyPanel";

function strategy(timeframe?: string): StrategyBlock {
  return {
    id: "reference",
    name: "Referencia",
    version: "0.1.0",
    timeframe,
    state: "warmup",
    state_label: "Calentando",
    phases: [],
    metrics: {},
    signal: null,
    rejection: null,
  } as unknown as StrategyBlock;
}

describe("marco de velas de la estrategia", () => {
  it("dice con qué velas piensa cuando no es el minuto", () => {
    render(<StrategyPanel strategy={strategy("15m")} />);
    expect(screen.getByText(/velas de 15m/)).toBeInTheDocument();
  });

  it("también lo dice en 1 m: el gráfico puede estar en otra", () => {
    render(<StrategyPanel strategy={strategy("1m")} />);
    expect(screen.getByText(/velas de 1m/)).toBeInTheDocument();
  });

  it("un snapshot sin marco no rompe el panel", () => {
    render(<StrategyPanel strategy={strategy(undefined)} />);
    expect(screen.queryByText(/velas de/)).toBeNull();
    expect(screen.getByText(/Referencia · v0.1.0/)).toBeInTheDocument();
  });
});
