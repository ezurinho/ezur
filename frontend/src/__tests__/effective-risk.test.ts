import { describe, expect, it } from "vitest";

import { effectiveRiskNote } from "../effectiveRisk";

describe("nota de riesgo efectivo", () => {
  it("explica las dos cifras cuando la promoción reduce el riesgo", () => {
    const note = effectiveRiskNote(1, 0.25) ?? "";
    expect(note).toMatch(/0[.,]25 % efectivo/);
    expect(note).toMatch(/1 % configurado/);
  });

  it("acepta la coma decimal que escribe el formulario", () => {
    expect(effectiveRiskNote("1,0", 0.25)).toContain("configurado");
  });

  it("no pinta nada cuando coinciden o el dato no es válido", () => {
    expect(effectiveRiskNote(1, 1)).toBeNull();
    expect(effectiveRiskNote(1, 1.0005)).toBeNull();
    expect(effectiveRiskNote("", 0.25)).toBeNull();
    expect(effectiveRiskNote(1, undefined)).toBeNull();
  });
});
