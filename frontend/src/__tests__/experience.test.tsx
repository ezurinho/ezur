import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { THEMES, ThemeProvider, useTheme } from "../theme";
import { ToastProvider, useToast } from "../toast";
import { CommandPalette, type PaletteItem } from "../components/CommandPalette";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Info } from "../components/Info";
import { ThemePicker } from "../components/ThemePicker";
import { Onboarding } from "../components/Onboarding";

describe("temas", () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  function Probe() {
    const { theme, setTheme } = useTheme();
    return (
      <>
        <span data-testid="theme">{theme}</span>
        <button type="button" onClick={() => setTheme("matrix")}>
          matrix
        </button>
      </>
    );
  }

  it("arranca en wraith y lo escribe en el documento", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("wraith");
    expect(document.documentElement.dataset.theme).toBe("wraith");
  });

  it("recuerda el tema elegido entre recargas", () => {
    window.localStorage.setItem("ezur.theme", "ember");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("ember");
    expect(document.documentElement.dataset.theme).toBe("ember");
  });

  it("ignora un tema inexistente en lugar de quedarse sin colores", () => {
    window.localStorage.setItem("ezur.theme", "neon-pink");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("wraith");
  });

  it("publica seis temas y todos tienen tres muestras", () => {
    expect(THEMES.map((item) => item.id)).toEqual([
      "wraith",
      "hud",
      "aurora",
      "ember",
      "matrix",
      "daylight",
    ]);
    for (const theme of THEMES) expect(theme.swatch).toHaveLength(3);
  });

  it("el selector aplica el tema y cierra el menú", () => {
    render(
      <ThemeProvider>
        <ThemePicker />
      </ThemeProvider>,
    );
    act(() => {
      screen.getByLabelText(/Tema:/).click();
    });
    act(() => {
      screen.getByRole("menuitemradio", { name: /Aurora/ }).click();
    });
    expect(document.documentElement.dataset.theme).toBe("aurora");
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("avisos", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  function Trigger() {
    const { push } = useToast();
    return (
      <button type="button" onClick={() => push({ title: "Motor detenido", tone: "good" })}>
        lanzar
      </button>
    );
  }

  it("muestra el aviso lanzado desde cualquier componente", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "lanzar" }).click();
    });
    expect(screen.getByRole("status")).toHaveTextContent("Motor detenido");
  });

  it("se cierra solo al terminar su tiempo", async () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "lanzar" }).click();
    });
    expect(screen.getAllByRole("status")).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryAllByRole("status")).toHaveLength(0);
    vi.useRealTimers();
  });

  it("el botón de cerrar lo quita antes de tiempo", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "lanzar" }).click();
    });
    act(() => {
      screen.getByRole("button", { name: "Cerrar aviso" }).click();
    });
    expect(screen.queryAllByRole("status")).toHaveLength(0);
  });
});

function mockMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("contadores animados", () => {
  it("con movimiento reducido escribe el valor final sin animación", () => {
    mockMotion(true);
    render(<AnimatedNumber value={1234.5} />);
    expect(screen.getByText("1,234.50")).toBeInTheDocument();
  });

  it("llega al valor exacto cuando termina la animación", async () => {
    mockMotion(false);
    render(<AnimatedNumber value={250} />);
    await waitFor(() => expect(screen.getByText("250.00")).toBeInTheDocument());
  });

  it("arranca en el valor recibido, no en cero", () => {
    mockMotion(false);
    render(<AnimatedNumber value={98.5} />);
    expect(screen.getByText("98.50")).toBeInTheDocument();
  });
});

describe("explicaciones", () => {
  it("enseña el texto de ayuda al pedirlo", () => {
    render(<Info term="R" text="lo que arriesgas por operación" />);
    const dot = screen.getByRole("button", { name: /Qué es R/ });
    act(() => {
      dot.click();
    });
    expect(screen.getByRole("tooltip")).toHaveTextContent("lo que arriesgas por operación");
  });
});

describe("paleta de comandos", () => {
  const items: PaletteItem[] = [
    { id: "a", label: "Inicio", group: "Vista", run: vi.fn() },
    { id: "b", label: "Pausar el motor", group: "Motor", hint: "paused", run: vi.fn() },
  ];

  it("filtra por subcadena", () => {
    render(<CommandPalette open items={items} onClose={() => undefined} />);
    const input = screen.getByLabelText("Buscar vista o acción");
    fireEvent.change(input, { target: { value: "pau" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByText("Pausar el motor")).toBeInTheDocument();
  });

  it("ejecuta la opción activa con Enter", () => {
    const run = vi.fn();
    render(
      <CommandPalette open items={[{ id: "x", label: "Detener el motor", group: "Motor", run }]} onClose={() => undefined} />,
    );
    const input = screen.getByLabelText("Buscar vista o acción");
    act(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    expect(run).toHaveBeenCalled();
  });

  it("cerrada no renderiza nada", () => {
    const { container } = render(<CommandPalette open={false} items={items} onClose={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("gráficos que explican", () => {
  it("la curva bajo el agua mide contra el pico, no contra el inicio", async () => {
    const { drawdownCurve } = await import("../components/Underwater");
    const series = drawdownCurve([
      { equity: 100 },
      { equity: 120 },
      { equity: 90 },
      { equity: 130 },
    ]);
    expect(series[0]).toBe(0);
    expect(series[1]).toBe(0);
    expect(series[2]).toBeCloseTo(-25, 5);
    expect(series[3]).toBe(0);
  });

  it("sin puntos no inventa una curva", async () => {
    const { drawdownCurve } = await import("../components/Underwater");
    expect(drawdownCurve([])).toEqual([]);
  });

  it("la barra de la operación marca stop, entrada y objetivo", async () => {
    const { TradeRange } = await import("../components/TradeRange");
    const { container } = render(
      <TradeRange side="short" entry={100} stop={104} target={92} price={96} />,
    );
    const bar = container.querySelector("[data-trade-range]");
    expect(bar).not.toBeNull();
    expect(bar?.textContent).toContain("stop");
    expect(bar?.textContent).toContain("objetivo");
    const dot = container.querySelector(".trade-range-price");
    expect(dot?.className).toContain("up");
  });

  it("en un corto, las etiquetas y las zonas siguen al eje real", async () => {
    const { TradeRange } = await import("../components/TradeRange");
    const { container } = render(
      <TradeRange side="short" entry={100} stop={104} target={92} price={96} />,
    );
    // Eje 92..104: objetivo a la izquierda, stop a la derecha.
    const labels = container.querySelector(".trade-range-labels");
    expect(labels?.firstElementChild?.textContent).toContain("objetivo");
    expect(labels?.lastElementChild?.textContent).toContain("stop");
    const loss = container.querySelector(".trade-range-loss") as HTMLElement;
    const win = container.querySelector(".trade-range-win") as HTMLElement;
    // Pérdida de la entrada (66,7 %) al stop (100 %), no de 0 al objetivo.
    expect(parseFloat(loss.style.left)).toBeCloseTo(66.7, 0);
    expect(parseFloat(loss.style.width)).toBeCloseTo(33.3, 0);
    expect(parseFloat(win.style.left)).toBeCloseTo(0, 0);
    expect(parseFloat(win.style.width)).toBeCloseTo(66.7, 0);
  });

  it("sin objetivo lo dice en vez de dibujar una barra falsa", async () => {
    const { TradeRange } = await import("../components/TradeRange");
    render(<TradeRange side="long" entry={100} stop={95} target={null} price={101} />);
    expect(screen.getByText(/Sin objetivo definido/)).toBeInTheDocument();
  });

  it("sin precio no culpa al objetivo", async () => {
    const { TradeRange } = await import("../components/TradeRange");
    render(<TradeRange side="long" entry={100} stop={95} target={110} price={null} />);
    expect(screen.getByText(/Sin precio actual/)).toBeInTheDocument();
    expect(screen.queryByText(/Sin objetivo definido/)).not.toBeInTheDocument();
  });
});

describe("resumen del día en modo básico", () => {
  it("la línea de histórico del inicio no inventa ceros ni empates", async () => {
    const { historyFoot } = await import("../pages/Dashboard");
    expect(historyFoot({ trades: 0 })).toContain("Sin cierres todavía");
    expect(historyFoot({ trades: 4, wins: 4, losses: 0, profit_factor: 1, expectancy_r: 0.4 })).toBe(
      "Histórico (4 cierres): PF ∞ · 0.40 R",
    );
    expect(historyFoot({ trades: 4, wins: 2, losses: 2, profit_factor: 1.5, expectancy_r: 0.2 })).toBe(
      "Histórico (4 cierres): PF 1.50 · 0.20 R",
    );
    expect(historyFoot({ trades: 2 })).toBe("Histórico (2 cierres): PF — · —");
  });

  it("cuenta ganadoras, perdedoras y el peor resultado", async () => {
    const { summarize } = await import("../pages/SimpleDashboard");
    const recap = summarize([
      { pnl_net: -10, exit_reason: "stop" },
      { pnl_net: 30, exit_reason: "target" },
      { pnl_net: -50, exit_reason: "stop" },
    ]);
    expect(recap.total).toBe(3);
    expect(recap.wins).toBe(1);
    expect(recap.losses).toBe(2);
    expect(recap.worst).toBe(-50);
    expect(recap.best).toBe(30);
    expect(recap.mainReason).toBe("stop");
  });

  it("sin operaciones no inventa un resumen", async () => {
    const { summarize } = await import("../pages/SimpleDashboard");
    const recap = summarize([]);
    expect(recap.total).toBe(0);
    expect(recap.mainReason).toBeNull();
    expect(recap.fees).toBe(0);
    expect(recap.gross).toBe(0);
  });

  it("el «hoy» deja fuera las operaciones de días anteriores", async () => {
    const { tradesSince } = await import("../pages/SimpleDashboard");
    const trades = [
      { id: 1, closed_ts: "2026-11-23T15:00:00Z", pnl_net: -10 },
      { id: 2, closed_ts: "2026-11-24T01:10:00Z", pnl_net: 12 },
      { id: 3, closed_ts: "2026-11-24T04:00:00Z", pnl_net: -3 },
    ];
    const today = tradesSince(trades, "2026-11-24T00:00:00Z");
    expect(today.map((trade) => trade.id)).toEqual([2, 3]);
  });

  it("sin fecha de sesión no afirma «hoy»", async () => {
    const { tradesSince } = await import("../pages/SimpleDashboard");
    const trades = [{ id: 1, closed_ts: "2026-11-24T01:10:00Z", pnl_net: 12 }];
    expect(tradesSince(trades, null)).toEqual([]);
    expect(tradesSince(trades, "no-es-fecha")).toEqual([]);
  });

  it("separa comisiones del resultado bruto", async () => {
    const { summarize } = await import("../pages/SimpleDashboard");
    const recap = summarize([
      { pnl_net: -10, fees: 3.5, exit_reason: "stop" },
      { pnl_net: 5, fees: 2.5, exit_reason: "target" },
    ]);
    expect(recap.fees).toBeCloseTo(6);
    // −10 + 5 + 6 = +1 antes de comisiones: la regla ganaba, el coste no.
    expect(recap.gross).toBeCloseTo(1);
  });
});

describe("por qué no entra", () => {
  it("enseña el motivo más repetido, no el último", async () => {
    const { dominantRejection } = await import("../reasons");
    expect(dominantRejection({ no_price: 2, stop_too_wide: 9 })).toEqual({
      code: "stop_too_wide",
      count: 9,
    });
  });

  it("sin rechazos no inventa un motivo", async () => {
    const { dominantRejection } = await import("../reasons");
    expect(dominantRejection(undefined)).toBeNull();
    expect(dominantRejection({})).toBeNull();
  });

  it("un stop por debajo del mínimo se explica en palabras", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("stop_too_tight")).toContain("más estrecho que el mínimo");
    expect(unblockHint("stop_too_tight")).toContain("mínimo del perfil");
  });

  it("un motivo con cero rechazos no cuenta", async () => {
    const { dominantRejection } = await import("../reasons");
    expect(dominantRejection({ no_price: 0 })).toBeNull();
  });
});

describe("corridas sin operaciones", () => {
  it("separa «el riesgo las descartó» de «la regla no disparó»", async () => {
    const { explainEmptyRun } = await import("../pages/Lab");
    const rolled = explainEmptyRun(0, { stop_too_wide: 9, no_price: 1 });
    expect(rolled).toContain("10 señales");
    expect(rolled).toContain("stop necesario");
    const silent = explainEmptyRun(0, undefined);
    expect(silent).toContain("no se cumplió");
    expect(silent).not.toContain("descartó");
  });

  it("con operaciones no añade explicación", async () => {
    const { explainEmptyRun } = await import("../pages/Lab");
    expect(explainEmptyRun(5, {})).toBeNull();
    expect(explainEmptyRun(1, { stop_too_wide: 3 })).toBeNull();
  });
});

describe("frase de concentración", () => {
  it("con pocas operaciones avisa de que es ruido", async () => {
    const { concentrationNote } = await import("../pages/Stats");
    const note = concentrationNote({ trades: 6, wins: 1, top5_share: 1 });
    expect(note).toContain("ruido");
    expect(note).toContain("una sola operación");
  });

  it("sin dependencia de las cinco mejores lo dice sin alarmar", async () => {
    const { concentrationNote } = await import("../pages/Stats");
    const note = concentrationNote({ trades: 120, wins: 60, top5_share: 0.22 });
    expect(note).toContain("no depende");
    expect(note).not.toContain("ruido");
  });

  it("poca concentración pero signo negativo sin las cinco lo dice", async () => {
    const { concentrationNote } = await import("../pages/Stats");
    const note = concentrationNote({
      trades: 120,
      wins: 60,
      top5_share: 0.3,
      pnl_without_top5: -40,
    });
    expect(note).toContain("signo se da la vuelta");
    expect(note).toContain("-40.00");
  });
});

describe("frescura del gráfico", () => {
  const now = Date.parse("2026-11-23T05:00:00Z");

  it("una vela de hace un minuto está en vivo", async () => {
    const { marketFreshness } = await import("../utils");
    expect(marketFreshness("2026-11-23T04:59:10Z", now).tone).toBe("live");
  });

  it("diez minutos tarde no es en vivo", async () => {
    const { marketFreshness } = await import("../utils");
    const fresh = marketFreshness("2026-11-23T04:50:00Z", now);
    expect(fresh.tone).toBe("lag");
    expect(fresh.label).toContain("10 min");
  });

  it("sin datos lo dice y no finge", async () => {
    const { marketFreshness } = await import("../utils");
    expect(marketFreshness(null, now)).toEqual({ tone: "none", label: "sin datos" });
  });

  it("una hora parado se cuenta en horas", async () => {
    const { marketFreshness } = await import("../utils");
    const fresh = marketFreshness("2026-11-23T03:00:00Z", now);
    expect(fresh.tone).toBe("stale");
    expect(fresh.label).toContain("2 h");
  });
});

describe("avisos de caída y vuelta del feed", () => {
  it("la primera observación no avisa", async () => {
    const { stallNotice } = await import("../utils");
    expect(stallNotice(undefined, "stale", "parado hace 20 min")).toBeNull();
    expect(stallNotice(undefined, "live", "en vivo")).toBeNull();
  });

  it("al pararse avisa una vez, con el detalle del parón", async () => {
    const { stallNotice } = await import("../utils");
    const notice = stallNotice("live", "stale", "parado hace 20 min");
    expect(notice?.tone).toBe("bad");
    expect(notice?.title).toBe("El mercado dejó de llegar");
    expect(notice?.detail).toContain("20 min");
  });

  it("seguir parado no repite el aviso", async () => {
    const { stallNotice } = await import("../utils");
    expect(stallNotice("stale", "stale", "parado hace 40 min")).toBeNull();
  });

  it("al volver avisa en positivo", async () => {
    const { stallNotice } = await import("../utils");
    const notice = stallNotice("stale", "live", "en vivo");
    expect(notice?.tone).toBe("good");
    expect(notice?.title).toBe("El feed ha vuelto");
  });

  it("un retraso corto no es una caída", async () => {
    const { stallNotice } = await import("../utils");
    expect(stallNotice("live", "lag", "retrasado 3 min")).toBeNull();
    expect(stallNotice("lag", "live", "en vivo")).toBeNull();
  });
});

describe("la frase de la racha depende de la pausa configurada", () => {
  it("sin pausa dice que dura hasta la próxima sesión", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("consecutive_losses", { lossStreakCooldownMin: 0 })).toContain("próxima sesión");
    expect(unblockHint("consecutive_losses", { lossStreakCooldownMin: 0 })).toContain("próxima sesión");
  });

  it("con pausa dice cuántos minutos", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    const context = { lossStreakCooldownMin: 45 };
    expect(plainReason("consecutive_losses", context)).toContain("45 minutos");
    expect(unblockHint("consecutive_losses", context)).toContain("45 min");
  });

  it("un feed obsoleto se explica sin jerga técnica", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("stale_data")).toContain("datos obsoletos");
    expect(unblockHint("stale_data")).toContain("velas frescas");
  });

  it("una orden con señal antigua se explica sin jerga técnica", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("stale_order")).toContain("señal antigua");
    expect(unblockHint("stale_order")).toContain("nueva señal");
  });

  it("una señal vencida se explica sin jerga técnica", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("stale_signal")).toContain("señal");
    expect(plainReason("stale_signal")).toContain("venció");
    expect(unblockHint("stale_signal")).toContain("nueva señal");
  });

  it("un rechazo por notional mínimo se explica sin jerga técnica", async () => {
    const { plainReason, unblockHint } = await import("../reasons");
    expect(plainReason("below_min_notional")).toContain("valor mínimo");
    expect(unblockHint("below_min_notional")).toContain("mayor tamaño");
  });

  it("ningún rechazo del motor cae en 'Motivo técnico'", async () => {
    const { plainReason } = await import("../reasons");
    // Los códigos que devuelve server/risk.py: todos deben tener frase humana.
    const codes = [
      "emergency_active",
      "order_pending",
      "position_open",
      "max_trades_reached",
      "consecutive_losses",
      "no_price",
      "stale_data",
      "stale_order",
      "stale_signal",
      "below_min_notional",
      "gap_through_stop",
      "gap_through_target",
      "invalid_stop",
      "invalid_stop_side",
      "invalid_target_side",
      "stop_too_wide",
      "outside_window",
      "excluded_window",
      "daily_loss_limit",
      "daily_profit_limit",
      "cooldown_active",
      "size_below_minimum",
    ];
    for (const code of codes) {
      expect(plainReason(code)).not.toContain("Motivo técnico");
    }
  });
});

describe("las tasas del servidor se muestran en tanto por ciento, no como fracción", () => {
  it("win_rate 0.333 se pinta como 33.3 %, no como 0.33 %", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entries = toEntries({ win_rate: 0.3333, pnl_net: -512.23 });
    expect(entries.win_rate.format).toBe("pct");
    expect(entries.win_rate.value).toBeCloseTo(33.33, 2);
    expect(entries.pnl_net.value).toBeCloseTo(-512.23, 2);
    expect(entries.pnl_net.format).toBe("price");
  });

  it("los recuentos son enteros y el reparto de las 5 mejores es un porcentaje", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entries = toEntries({ trades: 9, wins: 3, top5_share: 1 });
    expect(entries.trades.format).toBe("text");
    expect(entries.trades.value).toBe(9);
    expect(entries.wins.format).toBe("text");
    expect(entries.top5_share.format).toBe("pct");
    expect(entries.top5_share.value).toBe(100);
  });
});

describe("los tramos del servidor no se pintan con claves internas", () => {
  it("el lado y el día abreviado se dicen en español", async () => {
    const { bucketLabel } = await import("../pages/Stats");
    expect(bucketLabel("long")).toBe("compra");
    expect(bucketLabel("short")).toBe("venta");
    expect(bucketLabel("Mon")).toBe("lunes");
    expect(bucketLabel("mié")).toBe("miércoles");
  });

  it("horas, meses y días ISO se dejan tal cual", async () => {
    const { bucketLabel } = await import("../pages/Stats");
    expect(bucketLabel("01:00")).toBe("01:00");
    expect(bucketLabel("2026-11")).toBe("2026-11");
    expect(bucketLabel("2026-11-24")).toBe("2026-11-24");
  });
});

describe("la tarjeta de ventaja no convierte una media en una conclusión", () => {
  it("con muestra corta y media negativa dice que no hay ventaja demostrada", async () => {
    const { evidenceNote } = await import("../pages/Stats");
    const note = evidenceNote({ trades: 9, expectancy_r: -0.59, expectancy_ci80_low: -1.08 });
    expect(note).toContain("9 operaciones");
    expect(note).toContain("no hay ventaja demostrada");
  });

  it("una media positiva con el intervalo tocando cero sigue sin demostrar nada", async () => {
    const { evidenceNote } = await import("../pages/Stats");
    const note = evidenceNote({ trades: 60, expectancy_r: 0.2, expectancy_ci80_low: -0.05 });
    expect(note).toContain("toca cero");
    expect(note).toContain("no está demostrada");
  });

  it("solo canta ventaja si el suelo del IC80 supera cero", async () => {
    const { evidenceNote } = await import("../pages/Stats");
    const note = evidenceNote({ trades: 120, expectancy_r: 0.3, expectancy_ci80_low: 0.05 });
    expect(note).toContain("señales de ventaja");
    expect(note).not.toContain("muestra es corta");
  });
});

describe("el «hoy» del historial usa el día de la sesión (UTC)", () => {
  it("corta a medianoche UTC aunque el navegador esté en otro huso", async () => {
    const { periodStart } = await import("../pages/History");
    const now = new Date("2026-11-24T05:00:00Z");
    expect(periodStart("today", now)).toBe("2026-11-24T00:00:00.000Z");
  });

  it("si el motor abre a otra hora, «hoy» empieza en la apertura de su sesión", async () => {
    const { periodStart } = await import("../pages/History");
    const now = new Date("2026-11-24T15:00:00Z");
    expect(periodStart("today", now, "2026-11-24T14:30:00+00:00")).toBe(
      "2026-11-24T14:30:00.000Z",
    );
  });

  it("«todo» no impone fecha", async () => {
    const { periodStart } = await import("../pages/History");
    expect(periodStart("all")).toBeUndefined();
  });

  it("«mes en curso» empieza el día 1 y no son los últimos 30 días", async () => {
    const { periodStart } = await import("../pages/History");
    const now = new Date("2026-11-24T05:00:00Z");
    expect(periodStart("month", now)).toBe("2026-11-01T00:00:00.000Z");
    expect(periodStart("30d", now)).toBe("2026-10-25T05:00:00.000Z");
  });
});

describe("el onboarding describe el motor real", () => {
  beforeEach(() => window.localStorage.clear());

  it("al llegar al límite deja de abrir, no apaga el bot", () => {
    render(<Onboarding />);
    expect(screen.getByText(/deja de abrir operaciones/)).toBeInTheDocument();
    expect(screen.queryByText(/se para/)).toBeNull();
    expect(screen.getByText(/no está validada/)).toBeInTheDocument();
    expect(screen.getByText(/Estadísticas/)).toBeInTheDocument();
  });
});

describe("avisos de conexión con el servidor", () => {
  it("no avisa en el arranque", async () => {
    const { connectionNotice } = await import("../utils");
    expect(connectionNotice(false, "connecting").notice).toBeNull();
    expect(connectionNotice(false, "open").notice).toBeNull();
  });

  it("al caer la conexión avisa una sola vez, sin repetir en cada reintento", async () => {
    const { connectionNotice } = await import("../utils");
    const first = connectionNotice(false, "closed");
    expect(first.notice?.tone).toBe("bad");
    expect(first.notice?.title).toContain("Sin conexión");
    expect(first.down).toBe(true);

    const retry = connectionNotice(first.down, "closed");
    expect(retry.notice).toBeNull();
    const beat = connectionNotice(retry.down, "connecting");
    expect(beat.notice).toBeNull();
    expect(beat.down).toBe(true);
  });

  it("al volver avisa en positivo y rearma el pestillo", async () => {
    const { connectionNotice } = await import("../utils");
    const back = connectionNotice(true, "open");
    expect(back.notice?.title).toBe("Conexión restaurada con ezur");
    expect(back.notice?.tone).toBe("good");
    expect(back.down).toBe(false);
    expect(connectionNotice(back.down, "open").notice).toBeNull();
  });
});

describe("límites de riesgo legibles", () => {
  it("traduce las claves del servidor y les pone unidad", async () => {
    const { limitEntries } = await import("../utils");
    const rows = limitEntries({
      daily_loss_limit: -22.5,
      max_daily_loss_pct: 3,
      loss_streak_cooldown_min: 30,
      max_trades_per_day: 3,
    });
    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.daily_loss_limit.label).toBe("Muro de pérdida diaria");
    expect(byKey.daily_loss_limit.value).toBe("-22.50");
    expect(byKey.max_daily_loss_pct.value).toBe("3.00%");
    expect(byKey.loss_streak_cooldown_min.value).toBe("30 min");
    // Los topes son recuentos enteros: «3.00 operaciones» no existe.
    expect(byKey.max_trades_per_day.value).toBe("3");
  });

  it("con frenos suaves la racha se describe como freno, no como pausa", async () => {
    const { limitEntries } = await import("../utils");
    const rows = limitEntries({
      soft_brake_at: 600,
      loss_streak_cooldown_min: 45,
      no_trade_after_consecutive_losses: 3,
    });
    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.loss_streak_cooldown_min.label).toBe("Duración del freno por racha");
    expect(byKey.no_trade_after_consecutive_losses.label).toBe("Freno tras N pérdidas");
  });

  it("una clave nueva se muestra legible en vez de desaparecer", async () => {
    const { limitEntries } = await import("../utils");
    const rows = limitEntries({ max_position_units: 12 });
    expect(rows[0].label).toBe("max position units");
    expect(rows[0].value).toBe("12.00");
  });
});

describe("pronóstico de la operación abierta", () => {
  it("dice las dos cifras en dinero y avisa de que son brutas", async () => {
    const { positionOutlook } = await import("../pages/SimpleDashboard");
    const text = positionOutlook(61.04, 2.5);
    expect(text).toContain("Si toca el stop pierde 61.04");
    expect(text).toContain("gana 152.60");
    expect(text).toContain("a 2.5 R");
    expect(text).toContain("antes de comisiones");
  });

  it("sin objetivo no inventa una cifra de premio", async () => {
    const { positionOutlook } = await import("../pages/SimpleDashboard");
    const text = positionOutlook(40, null);
    expect(text).toContain("pierde 40.00");
    expect(text).not.toContain("objetivo");
  });
});

describe("historial recortado", () => {
  it("no dice nada mientras la lista cabe entera", async () => {
    const { rowsNote } = await import("../pages/History");
    expect(rowsNote(0)).toBeNull();
    expect(rowsNote(199)).toBeNull();
  });

  it("al llegar al límite avisa de que puede haber más y cómo verlo", async () => {
    const { rowsNote } = await import("../pages/History");
    const note = rowsNote(200);
    expect(note).toContain("200");
    expect(note).toContain("puede haber");
    expect(note).toContain("CSV");
  });
});

describe("historial de laboratorio recortado", () => {
  it("no dice nada mientras la lista cabe entera", async () => {
    const { historyNote } = await import("../pages/Lab");
    expect(historyNote(0)).toBeNull();
    expect(historyNote(8)).toBeNull();
  });

  it("con más corridas que huecos, dice cuántas hay en total", async () => {
    const { historyNote } = await import("../pages/Lab");
    const note = historyNote(12);
    expect(note).toContain("8");
    expect(note).toContain("12");
  });

  it("con la página recortada, no presenta el recorte como total", async () => {
    const { historyNote } = await import("../pages/Lab");
    const note = historyNote(25, 8, true);
    expect(note).toContain("al menos");
    expect(note).toContain("25");
    expect(note).not.toContain("en total");
  });
});

describe("horario de sesión con dos husos", () => {
  it("da la ventana en UTC además de la hora del navegador", async () => {
    const { sessionWindow } = await import("../utils");
    const window = sessionWindow("2026-11-24T00:00:00Z", "2026-11-24T23:59:00Z");
    expect(window?.utc).toBe("00:00 → 23:59");
    expect(window?.local).toContain("→");
  });

  it("sin fechas válidas no inventa un horario", async () => {
    const { sessionWindow } = await import("../utils");
    expect(sessionWindow("", "x")).toBeNull();
  });
});

describe("referencia de la curva de equidad", () => {
  it("usa el capital inicial real, no el primer cierre cargado", async () => {
    const { baselineLine } = await import("../components/EquityChart");
    const line = baselineLine([{ equity: 24400 }, { equity: 24500 }], 25000);
    expect(line).toEqual({ price: 25000, title: "capital inicial" });
  });

  it("sin capital inicial dice qué es la línea", async () => {
    const { baselineLine } = await import("../components/EquityChart");
    expect(baselineLine([{ equity: 24400 }], null)).toEqual({
      price: 24400,
      title: "primer cierre cargado",
    });
    expect(baselineLine([], null)).toBeNull();
  });
});

describe("ayuda del riesgo con capital real", () => {
  it("calcula el importe sobre el capital que llega, no sobre uno fijo", async () => {
    const { riskHelp } = await import("../pages/SimpleSettings");
    expect(riskHelp(1, 25000)).toContain("250.00");
    expect(riskHelp(0.5, 24510.3)).toContain("122.55");
  });

  it("sin capital no enseña un número inventado", async () => {
    const { riskHelp } = await import("../pages/SimpleSettings");
    const text = riskHelp(1, null);
    expect(text).not.toMatch(/\d{2,}[.,]\d{2}/);
  });
});

describe("etiquetas del resumen", () => {
  it("traduce las claves y deja legible una nueva", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entries = toEntries({ profit_factor: 0.35, new_metric: 1 });
    expect(entries.profit_factor.label).toBe("Profit factor");
    expect(entries.new_metric.label).toBe("new metric");
  });
});

describe("unidades del resumen desplegado", () => {
  it("el P&L sin las 5 mejores es dinero y la duración va en minutos", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entries = toEntries({ pnl_without_top5: -702.3, avg_duration_minutes: 128, r_total: -4.98 });
    expect(entries.pnl_without_top5.format).toBe("price");
    expect(entries.avg_duration_minutes.format).toBe("duration");
    expect(entries.r_total.label).toBe("R acumulado");
  });

  it("los cierres imposibles se cuentan como enteros y con su nombre", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entry = toEntries({ impossible_durations: 2 }).impossible_durations;
    expect(entry.label).toBe("Cierres imposibles");
    expect(entry.format).toBe("text");
  });

  it("un profit factor sin pérdidas se dice infinito, no 1,00", async () => {
    const { toEntries } = await import("../pages/Stats");
    const entry = toEntries({ trades: 3, wins: 3, losses: 0, profit_factor: 1 }).profit_factor;
    expect(entry.value).toBe("∞ (sin pérdidas)");
    expect(entry.format).toBe("text");
    // Con pérdidas reales el número del servidor manda tal cual.
    const normal = toEntries({ trades: 4, wins: 2, losses: 2, profit_factor: 1.5 }).profit_factor;
    expect(normal.value).toBe(1.5);
    expect(normal.format).toBe("number");
  });

  it("el laboratorio aplica la misma regla que Estadísticas", async () => {
    const { pfText, pfTitle } = await import("../pages/Lab");
    expect(pfText({ wins: 5, losses: 0, profit_factor: 1 })).toBe("∞");
    expect(pfTitle({ wins: 5, losses: 0, profit_factor: 1 })).toContain("denominador");
    expect(pfText({ wins: 3, losses: 2, profit_factor: 1.37 })).toBe("1.37");
    expect(pfText({ wins: 0, losses: 0, profit_factor: 0 })).toBe("0.00");
    expect(pfTitle({ wins: 3, losses: 2, profit_factor: 1.37 })).toBeUndefined();
  });
});
