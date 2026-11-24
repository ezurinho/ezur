import { describe, expect, it } from "vitest";

import { summarize } from "../pages/SimpleDashboard";

describe("resumen del día con una operación sin resultado", () => {
  it("no la cuenta como empate: la separa y no suma un cero", () => {
    const recap = summarize([
      { pnl_net: 10, exit_reason: "target" },
      { exit_reason: "stop" },
    ]);
    expect(recap.total).toBe(2);
    expect(recap.wins + recap.losses).toBe(1);
    expect(recap.unmeasured).toBe(1);
    expect(recap.best).toBe(10);
    expect(recap.worst).toBe(10);
    expect(recap.gross).toBe(10);
  });

  it("sin ningún resultado medido no inventa peor ni mejor", () => {
    const recap = summarize([{ exit_reason: "manual" }]);
    expect(recap.unmeasured).toBe(1);
    expect(recap.wins).toBe(0);
    expect(recap.losses).toBe(0);
    expect(recap.best).toBe(0);
    expect(recap.worst).toBe(0);
    expect(recap.mainReason).toBe("manual");
  });

  it("un pnl_net nulo tampoco es un empate", () => {
    // Number(null) es 0: sin filtrarlo, la operación se contaba como medida.
    const recap = summarize([
      { pnl_net: null, exit_reason: "stop" },
      { pnl_net: -4, exit_reason: "stop" },
    ]);
    expect(recap.unmeasured).toBe(1);
    expect(recap.losses).toBe(1);
    expect(recap.wins).toBe(0);
    expect(recap.worst).toBe(-4);
    expect(recap.gross).toBe(-4);
  });
});
