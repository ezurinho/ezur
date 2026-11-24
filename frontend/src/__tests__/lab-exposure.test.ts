import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: {} }));

import { endExposureNote } from "../pages/Lab";

describe("exposición al final de un backtest", () => {
  it("no dice nada si la corrida terminó plana", () => {
    expect(endExposureNote({ open_position: null, pending_orders: 0 })).toBeNull();
  });

  it("aclara que una posición abierta no entra en las métricas", () => {
    const note = endExposureNote({ open_position: { symbol: "BTC" }, pending_orders: 0 });
    expect(note).toContain("BTC");
    expect(note).toContain("no está incluido");
  });

  it("también enumera órdenes que nunca llegaron a ejecutarse", () => {
    const note = endExposureNote({ open_position: null, pending_orders: 2 });
    expect(note).toContain("2 órdenes pendientes");
  });
});
