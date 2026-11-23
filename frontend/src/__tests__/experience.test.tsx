import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { THEMES, ThemeProvider, useTheme } from "../theme";
import { ToastProvider, useToast } from "../toast";
import { CommandPalette, type PaletteItem } from "../components/CommandPalette";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Info } from "../components/Info";
import { ThemePicker } from "../components/ThemePicker";

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

  it("arranca en hud y lo escribe en el documento", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("hud");
    expect(document.documentElement.dataset.theme).toBe("hud");
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
    expect(screen.getByTestId("theme")).toHaveTextContent("hud");
  });

  it("publica cinco temas y todos tienen tres muestras", () => {
    expect(THEMES.map((item) => item.id)).toEqual(["hud", "aurora", "ember", "matrix", "daylight"]);
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

  it("sin objetivo lo dice en vez de dibujar una barra falsa", async () => {
    const { TradeRange } = await import("../components/TradeRange");
    render(<TradeRange side="long" entry={100} stop={95} target={null} price={101} />);
    expect(screen.getByText(/Sin objetivo definido/)).toBeInTheDocument();
  });
});

describe("resumen del día en modo básico", () => {
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
