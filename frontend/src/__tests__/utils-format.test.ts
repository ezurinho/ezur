import { describe, expect, it } from "vitest";

import { formatValue, phaseLabel, qualityLabel, sideLabel, toFinite } from "../utils";

describe("formatValue", () => {
  it("un número roto no se pinta como si fuera medido", () => {
    expect(formatValue(Number.NaN, "price")).toBe("—");
    expect(formatValue(Number.POSITIVE_INFINITY, "pct")).toBe("—");
    expect(formatValue(Number.NEGATIVE_INFINITY, "ratio")).toBe("—");
  });

  it("el cero se pinta: es un dato, no una ausencia", () => {
    expect(formatValue(0, "ratio")).toBe("0.00");
  });

  it("el porcentaje usa el mismo separador decimal que el precio", () => {
    // Con punto fijo, «0.43 %» convive con «60.371,20» en la misma tabla.
    expect(formatValue(0.43, "pct")).toBe(`${formatValue(0.43, "price")}%`);
  });

  it("toFinite distingue ausente de cero", () => {
    // `Number(null)` es 0, y un pnl_net nulo acabaría pintado como empate.
    expect(toFinite(null)).toBeNull();
    expect(toFinite(undefined)).toBeNull();
    expect(toFinite("")).toBeNull();
    expect(toFinite("n/a")).toBeNull();
    expect(toFinite(0)).toBe(0);
    expect(toFinite("3.5")).toBe(3.5);
  });

  it("el lado se dice cómo actuó el motor, no con su clave interna", () => {
    expect(sideLabel("long")).toBe("compra");
    expect(sideLabel("short")).toBe("venta");
    expect(sideLabel("lateral")).toBe("lateral");
  });

  it("la calidad del feed se dice en palabras y lo desconocido se conserva", () => {
    expect(qualityLabel("ok")).toBe("ok");
    expect(qualityLabel("degraded")).toBe("con retraso");
    expect(qualityLabel("stale")).toBe("obsoleta");
    expect(qualityLabel("unknown")).toBe("sin dato");
    expect(qualityLabel("raro")).toBe("raro");
  });

  it("la fase de sesión se dice en español, y lo desconocido se conserva", () => {
    expect(phaseLabel("open")).toBe("abierta");
    expect(phaseLabel("closed")).toBe("cerrada");
    expect(phaseLabel("pre")).toBe("antes de abrir");
    expect(phaseLabel("close")).toBe("cerrando");
    expect(phaseLabel("overnight")).toBe("overnight");
  });
});
