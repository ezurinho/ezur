import { describe, expect, it } from "vitest";

import { pnlByClose } from "../pages/Dashboard";

describe("serie del KPI de P&L diario", () => {
  it("son las diferencias de la curva de equidad, no la equidad", () => {
    expect(pnlByClose([25000, 25010, 25000, 25025])).toEqual([10, -10, 25]);
  });

  it("con un solo punto no hay resultado que dibujar", () => {
    expect(pnlByClose([25000])).toBeUndefined();
    expect(pnlByClose([])).toBeUndefined();
  });
});
