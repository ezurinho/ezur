import { describe, expect, it } from "vitest";

import { summarizeHistory, summaryEntries } from "../pages/History";

describe("resumen del historial", () => {
  it("separa ganado, perdido y resultado total", () => {
    const summary = summarizeHistory([
      { pnl_net: 100, fees: 1, r_multiple: 1 },
      { pnl_net: -40, fees: 1.5, r_multiple: -0.5 },
      { pnl_net: 10, fees: 0.5, r_multiple: 0.2 },
      { pnl_net: 0, fees: 0.1, r_multiple: 0 },
    ]);

    expect(summary.rows).toBe(4);
    expect(summary.wins).toBe(2);
    expect(summary.losses).toBe(1);
    expect(summary.flats).toBe(1);
    expect(summary.grossWin).toBe(110);
    expect(summary.grossLoss).toBe(-40);
    expect(summary.net).toBe(70);
    expect(summary.winRate).toBeCloseTo(0.5);
    expect(summary.profitFactor).toBeCloseTo(2.75);
    expect(summary.fees).toBeCloseTo(3.1);
    expect(summary.rTotal).toBeCloseTo(0.7);
    expect(summary.avgWin).toBe(55);
    expect(summary.avgLoss).toBe(-40);
    expect(summary.best).toBe(100);
    expect(summary.worst).toBe(-40);
  });

  it("no cuenta un P&L ausente como cero ni un PF sin pérdidas como 1", () => {
    const summary = summarizeHistory([
      { pnl_net: null, fees: null },
      { pnl_net: 5, fees: 0.2 },
    ]);

    expect(summary.rows).toBe(2);
    expect(summary.priced).toBe(1);
    expect(summary.missing).toBe(1);
    expect(summary.net).toBe(5);
    expect(summary.grossLoss).toBe(0);
    expect(summary.profitFactor).toBeNull();
    expect(summary.fees).toBe(0.2);
    expect(summary.winRate).toBe(1);

    expect(summaryEntries(summary).pf?.value).toBe("∞ (sin pérdidas)");
  });
});
