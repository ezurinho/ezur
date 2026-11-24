import { describe, expect, it } from "vitest";

import {
  instrumentsFromConfig,
  numericError,
  paramsForm,
  paramsPayload,
  scheduleError,
  withContextInstrument,
} from "../pages/Config";

const PROPERTIES = {
  fast: { type: "integer", title: "Fast", default: 9 },
  stop_atr: { type: "number", title: "Stop Atr", default: 1.5 },
};

describe("formulario de parámetros de estrategia", () => {
  it("se abre con lo que el motor usa, no con los defaults del esquema", () => {
    const form = paramsForm(PROPERTIES, { fast: 7, stop_atr: 6 });
    expect(form).toEqual({ fast: "7", stop_atr: "6" });
  });

  it("sin valores guardados cae al default del esquema", () => {
    expect(paramsForm(PROPERTIES, undefined)).toEqual({ fast: "9", stop_atr: "1.5" });
  });

  it("convierte a número lo numérico y respeta la coma decimal", () => {
    const payload = paramsPayload(PROPERTIES, { fast: "7", stop_atr: "1,25" }, {});
    expect(payload).toEqual({ fast: 7, stop_atr: 1.25 });
  });

  it("un campo vacío conserva el valor actual en vez de mandar el default", () => {
    const payload = paramsPayload(PROPERTIES, { fast: "", stop_atr: "2" }, {
      fast: 7,
      stop_atr: 6,
    });
    expect(payload).toEqual({ fast: 7, stop_atr: 2 });
  });

  it("no inventa parámetros que el esquema no declara", () => {
    const payload = paramsPayload(PROPERTIES, { fast: "7", ghost: "1" }, {});
    expect(Object.keys(payload)).toEqual(["fast"]);
  });
});

const PRIMARY = {
  symbol: "BTC",
  role: "primary" as const,
  venue_symbol: "BTC-USDT",
  enabled: true,
  tick_size: 0.01,
  tick_value: 0.00001,
  point_value: null,
  currency: "USDT",
  decimals: 2,
  session_template: "CRYPTO24",
};

describe("lista de instrumentos", () => {
  it("lee la ficha completa de la configuración, no del snapshot", () => {
    const items = instrumentsFromConfig({ instruments: { items: [PRIMARY], primary: "BTC" } });
    expect(items).toEqual([PRIMARY]);
    expect(instrumentsFromConfig(null)).toBeNull();
    expect(instrumentsFromConfig({ instruments: {} })).toBeNull();
  });

  it("el instrumento nuevo copia el contrato del primario y queda de contexto", () => {
    const result = withContextInstrument([PRIMARY], "ETH-USDT", "");
    expect("items" in result).toBe(true);
    if (!("items" in result)) return;
    expect(result.items).toHaveLength(2);
    expect(result.items[1]).toMatchObject({
      symbol: "ETH-USDT",
      role: "context",
      venue_symbol: null,
      enabled: true,
      tick_size: PRIMARY.tick_size,
      tick_value: PRIMARY.tick_value,
      session_template: "CRYPTO24",
    });
    expect(result.items[0]).toEqual(PRIMARY);
  });

  it("la plaza escrita se guarda tal cual", () => {
    const result = withContextInstrument([PRIMARY], "ETH", " ETH-USDT ");
    if (!("items" in result)) throw new Error("esperaba lista");
    expect(result.items[1].venue_symbol).toBe("ETH-USDT");
  });

  it("rechaza símbolos vacíos o repetidos en vez de guardarlos", () => {
    const blank = withContextInstrument([PRIMARY], "  ", "");
    expect(blank).toEqual({ error: "Escribe el símbolo del instrumento." });
    const duplicate = withContextInstrument([PRIMARY], "btc", "");
    expect("error" in duplicate).toBe(true);
    if ("error" in duplicate) expect(duplicate.error).toContain("btc");
  });
});

const RISK_LABELS = { risk_per_trade_pct: "Riesgo por operación (%)" };

describe("guardas de los formularios avanzados", () => {
  it("un campo vacío no se guarda como cero", () => {
    expect(numericError({ risk_per_trade_pct: "" }, RISK_LABELS)).toContain(
      "Riesgo por operación",
    );
  });

  it("rechaza texto y negativos", () => {
    expect(numericError({ risk_per_trade_pct: "dos" }, RISK_LABELS)).toContain("no es un número");
    expect(numericError({ risk_per_trade_pct: "-1" }, RISK_LABELS)).toContain("negativo");
  });

  it("acepta la coma decimal", () => {
    expect(numericError({ risk_per_trade_pct: "0,25" }, RISK_LABELS)).toBeNull();
  });

  it("una hora sin formato o imposible se para antes de guardar", () => {
    const labels = { session_close_time: "Cierre de sesión" };
    expect(scheduleError({ session_close_time: "9" }, labels)).toContain("HH:MM");
    expect(scheduleError({ session_close_time: "25:00" }, labels)).toContain("hora válida");
    expect(scheduleError({ session_close_time: "23:59" }, labels)).toBeNull();
  });
});
