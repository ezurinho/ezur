import { describe, expect, it } from "vitest";
import { buildReasoning } from "../reasoning";
import type { SnapshotData } from "../types";

/**
 * Fixtures, no datos de mercado: aquí se prueba qué frase sale de qué campo.
 * Ningún test afirma nada sobre el rendimiento de una estrategia.
 */
function snap(patch: Record<string, unknown> = {}): SnapshotData {
  const base = {
    status: "running",
    mode: "paper",
    session: { id: "s", label: "RTH", is_open: true, open_ts: null, close_ts: null, phase: "open" },
    data: {
      provider: "synthetic",
      quality: "ok",
      last_bar_ts: "2026-11-23T12:00:00Z",
      staleness_ms: 4200,
      bars_available: 400,
    },
    instruments: [],
    quotes: {},
    chart: { primary: "BTC", timeframe: "5m", timeframes: [], candles: [], series: [], zones: [], markers: [] },
    strategy: {
      id: "donchian",
      name: "Donchian",
      version: "1.0.0",
      state: "scanning",
      state_label: "Esperando ruptura",
      phases: [],
      metrics: {},
      signal: null,
      rejection: null,
    },
    position: null,
    orders: [],
    risk: {
      equity: 25000,
      open_risk: 0,
      daily_pnl: 0,
      daily_trades: 0,
      blocked: false,
      block_reason: null,
      block_count: 0,
      limits: { max_trades_per_day: 3, max_daily_loss_pct: 3, loss_streak_cooldown_min: 0 },
    },
    stats: {},
    day_stats: {},
    settings: {},
    ui: { panels: [], theme: "dark", locale: "es" },
  };
  const merged = { ...base, ...patch } as Record<string, unknown>;
  if (patch.risk) merged.risk = { ...base.risk, ...(patch.risk as object) };
  if (patch.strategy) merged.strategy = { ...base.strategy, ...(patch.strategy as object) };
  if (patch.data) merged.data = { ...base.data, ...(patch.data as object) };
  return merged as unknown as SnapshotData;
}

describe("buildReasoning", () => {
  it("con el motor parado no dice que vigila: dice que no evalúa", () => {
    const result = buildReasoning(snap({ status: "stopped" }));
    expect(result.headline).toBe("Parado");
    expect(result.tone).toBe("neutral");
    expect(result.verdict).toContain("No evalúa el mercado");
    expect(result.steps).toHaveLength(6);
  });

  it("sin estrategia cargada lo dice como falta de regla, no como bloqueo", () => {
    const result = buildReasoning(
      snap({ strategy: { state: "disabled", state_label: "Sin estrategia", name: "Estrategia pendiente" } }),
    );
    expect(result.headline).toBe("Sin estrategia");
    expect(result.tone).toBe("warn");
    expect(result.steps.find((step) => step.key === "strategy")?.status).toBe("fail");
    expect(result.verdict).toContain("no tiene regla que aplicar");
  });

  it("un bloqueo de riesgo usa la misma frase que el resto de la app, una sola vez", () => {
    const result = buildReasoning(
      snap({
        risk: { blocked: true, block_reason: "daily_loss_limit", block_count: 4 },
      }),
    );
    expect(result.headline).toBe("Bloqueado");
    expect(result.tone).toBe("warn");
    expect(result.verdict).toBe("Hoy ya perdió el máximo permitido. El bot se protege y para.");
    expect(result.steps.find((step) => step.key === "risk")?.status).toBe("fail");
    // El recuento de rechazos lo da el aviso fechado: repetirlo aquí era ruido.
    expect(result.veto).toBeNull();
    // El motivo vive en el veredicto, no también en la fila del paso.
    expect(result.steps.find((step) => step.key === "risk")?.detail).not.toContain("máximo permitido");
  });

  it("sin bloqueo activo sí nombra los rechazos del día", () => {
    const result = buildReasoning(snap({ risk: { block_count: 2 } }));
    expect(result.veto).toContain("2 señales");
  });

  it("en pausa no dice «parado»: es otro estado y se reanuda distinto", () => {
    const result = buildReasoning(snap({ status: "paused" }));
    expect(result.headline).toBe("En pausa");
    expect(result.verdict).toContain("hasta que se reanude");
  });

  it("con bloqueo y posición abierta avisa de que la posición sigue viva", () => {
    const result = buildReasoning(
      snap({
        risk: { blocked: true, block_reason: "daily_loss_limit", block_count: 1 },
        position: {
          symbol: "BTC",
          side: "long",
          units: 1,
          entry_price: 100,
          stop_price: 95,
          target_price: 110,
          opened_ts: "2026-11-23T11:00:00Z",
          unrealized: null,
          r_open: null,
        },
      }),
    );
    expect(result.headline).toBe("Bloqueado");
    expect(result.verdict).toContain("Hoy ya perdió el máximo permitido");
    expect(result.verdict).toContain("sigue gestionándose con su stop");
  });

  it("con una orden en camino la decisión es esperar, no «vigilando»", () => {
    const result = buildReasoning(
      snap({
        orders: [
          {
            id: "o1",
            symbol: "BTC",
            side: "long",
            units: 1,
            kind: "limit",
            price: 100,
            status: "pending",
            created_ts: "2026-11-23T11:00:00Z",
            stop_price: 95,
            target_price: 110,
            signal_key: "k1",
          },
        ],
      }),
    );
    expect(result.headline).toBe("Orden en curso");
    expect(result.verdict).toContain("Una orden");
    expect(result.steps.find((step) => step.key === "execution")?.status).toBe("pass");
  });

  it("una fuerza que no es un número no inventa convicción", () => {
    const result = buildReasoning(
      snap({
        strategy: {
          state: "armed",
          signal: {
            key: "k1",
            side: "long",
            strength: Number.NaN,
            reason: "ruptura canal 20",
            ts: "2026-11-23T12:00:00Z",
            valid_until: null,
            stop_price: 100,
            target_price: 110,
          },
        },
      }),
    );
    expect(result.conviction).toBeNull();
  });

  it("con señal publica lado, stop y la convicción que da la estrategia", () => {
    const result = buildReasoning(
      snap({
        strategy: {
          state: "armed",
          state_label: "Ruptura detectada",
          signal: {
            key: "k1",
            side: "long",
            strength: 0.82,
            reason: "ruptura canal 20",
            ts: "2026-11-23T12:00:00Z",
            valid_until: null,
            stop_price: 100,
            target_price: 110,
          },
        },
      }),
    );
    expect(result.headline).toBe("Señal");
    expect(result.tone).toBe("good");
    expect(result.conviction).toEqual({ label: "alta", value: 0.82 });
    expect(result.verdict).toContain("compra");
    expect(result.verdict).toContain("110.00");
    expect(result.steps.find((step) => step.key === "signal")?.status).toBe("pass");
  });

  it("con posición abierta la decisión activa es la salida, no la entrada", () => {
    const result = buildReasoning(
      snap({
        position: {
          symbol: "BTC",
          side: "short",
          units: 2,
          entry_price: 100,
          stop_price: 105,
          target_price: 90,
          opened_ts: "2026-11-23T11:00:00Z",
          unrealized: null,
          r_open: null,
        },
      }),
    );
    expect(result.headline).toBe("En posición");
    expect(result.verdict).toContain("gestionar la venta abierta");
    expect(result.steps.find((step) => step.key === "execution")?.status).toBe("pass");
  });

  it("sin velas el primer paso falla: no hay nada que evaluar", () => {
    const result = buildReasoning(snap({ data: { bars_available: 0 } }));
    const data = result.steps.find((step) => step.key === "data");
    expect(data?.status).toBe("fail");
    expect(data?.detail).toContain("sin velas");
  });

  it("sin bloqueo no inventa un veto", () => {
    expect(buildReasoning(snap()).veto).toBeNull();
  });

  it("el presupuesto de pérdida usa el capital del día, no la equidad actual", () => {
    const result = buildReasoning(snap({ risk: { equity: 26000, daily_pnl: 1000 } }));
    const detail = result.steps.find((step) => step.key === "risk")?.detail ?? "";
    // capital = 26.000 − 1.000 = 25.000 · 3 % = 750, no 26.000 · 3 % = 780
    expect(detail).toContain("750.00");
    expect(detail).not.toContain("780.00");
  });

  it("sin límite de pérdida configurado dice «sin límite», no «de 0.00»", () => {
    const result = buildReasoning(snap({ risk: { limits: { max_trades_per_day: 3 } } }));
    const detail = result.steps.find((step) => step.key === "risk")?.detail ?? "";
    expect(detail).toContain("sin límite");
    expect(detail).not.toContain("de 0.00");
  });
});
