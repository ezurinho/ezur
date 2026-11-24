import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar, SIMPLE_VIEWS, VIEWS } from "../components/Sidebar";
import { UiModeProvider, useUiMode } from "../mode";
import { ToastProvider } from "../toast";
import { SimpleDashboard } from "../pages/SimpleDashboard";
import { SimpleSettings } from "../pages/SimpleSettings";

function ModeProbe() {
  const { mode, setMode } = useUiMode();
  return (
    <>
      <span data-testid="mode">{mode}</span>
      <button type="button" onClick={() => setMode("advanced")}>
        ir a pro
      </button>
    </>
  );
}

describe("modo de interfaz", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("arranca en fácil la primera vez, sin preguntar nada", () => {
    render(
      <UiModeProvider>
        <ModeProbe />
      </UiModeProvider>,
    );
    expect(screen.getByTestId("mode")).toHaveTextContent("simple");
  });

  it("recuerda la elección: un ajuste de UI no se pierde al recargar", () => {
    window.localStorage.setItem("ezur.ui.mode", "advanced");
    render(
      <UiModeProvider>
        <ModeProbe />
      </UiModeProvider>,
    );
    expect(screen.getByTestId("mode")).toHaveTextContent("advanced");
  });

  it("escribe la preferencia en localStorage al cambiarla", () => {
    render(
      <UiModeProvider>
        <ModeProbe />
      </UiModeProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "ir a pro" }).click();
    });
    expect(window.localStorage.getItem("ezur.ui.mode")).toBe("advanced");
  });

  it("marca el modo en el documento para que el CSS pueda responder", () => {
    render(
      <UiModeProvider>
        <ModeProbe />
      </UiModeProvider>,
    );
    expect(document.documentElement.dataset.uiMode).toBe("simple");
  });

  it("ignora un valor corrupto en lugar de romper la página", () => {
    window.localStorage.setItem("ezur.ui.mode", "ultra");
    render(
      <UiModeProvider>
        <ModeProbe />
      </UiModeProvider>,
    );
    expect(screen.getByTestId("mode")).toHaveTextContent("simple");
  });
});

describe("Sidebar por modo", () => {
  it("fácil enseña cuatro vistas y ninguna de experto", () => {
    const { container } = render(<Sidebar active="home" onSelect={() => undefined} simple />);
    const labels = [...container.querySelectorAll(".nav-label")].map((node) => node.textContent);
    expect(labels).toEqual(["Inicio", "Gráfico", "Historial", "Ajustes"]);
    expect(labels).not.toContain("Consola");
    expect(SIMPLE_VIEWS.length).toBe(4);
  });

  it("avanzado sigue enseñando todas, laboratorio incluido", () => {
    render(<Sidebar active="home" onSelect={() => undefined} />);
    expect(screen.getAllByRole("button").length).toBe(VIEWS.length);
    expect(VIEWS.map((view) => view.id)).toContain("lab");
  });

  it("el modo se anuncia en el DOM, no solo con color", () => {
    const { container } = render(<Sidebar active="home" onSelect={() => undefined} simple />);
    expect(container.querySelector("nav")?.dataset.mode).toBe("simple");
  });
});

describe("vistas de principiante", () => {
  it("el inicio fácil enseña un esqueleto en vez de inventar cifras", async () => {
    // Las cargas de historial y precio quedan pendientes: el test mira el
    // primer render, y una promesa que falla después solo añadiría ruido de act().
    const { api } = await import("../api");
    const tradesSpy = vi.spyOn(api, "trades").mockReturnValue(new Promise(() => {}));
    const chartSpy = vi.spyOn(api, "chart").mockReturnValue(new Promise(() => {}));
    const { container } = render(
      <UiModeProvider>
        <ToastProvider>
          <SimpleDashboard />
        </ToastProvider>
      </UiModeProvider>,
    );
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(2);
    tradesSpy.mockRestore();
    chartSpy.mockRestore();
  });

  it("los ajustes simples no enseñan números hasta leerlos del servidor", async () => {
    const { api } = await import("../api");
    const spy = vi.spyOn(api, "config").mockResolvedValue({
      risk: { risk_per_trade_pct: 1, max_daily_loss_pct: 3, max_trades_per_day: 8 },
    });
    const { container } = render(
      <UiModeProvider>
        <ToastProvider>
          <SimpleSettings />
        </ToastProvider>
      </UiModeProvider>,
    );
    // Un slider con valores de ejemplo se lee como si fueran los reales.
    expect(container.querySelectorAll("input[type='range']").length).toBe(0);
    expect(screen.getByText(/Leyendo la configuración actual/)).toBeInTheDocument();
    await waitFor(() =>
      expect(container.querySelectorAll("input[type='range']").length).toBe(3),
    );
    expect(screen.getByText("Cuánto arriesgar en cada operación")).toBeInTheDocument();
    expect(screen.getByText("Cuánto puedes perder en un día")).toBeInTheDocument();
    expect(screen.getByText("Operaciones máximas al día")).toBeInTheDocument();
    expect(screen.getByText(/8 ops/)).toBeInTheDocument();
    // El control debe poder caer exactamente en el valor del motor: con un paso
    // que no lo alcanza, el slider enseñaba 3,25 % donde el motor tenía 3 %.
    const loss = container.querySelector<HTMLInputElement>("input[name='max_daily_loss_pct']");
    expect(loss?.value).toBe("3");
    spy.mockRestore();
  });
});
