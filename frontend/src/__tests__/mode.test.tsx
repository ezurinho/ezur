import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { Sidebar, SIMPLE_VIEWS, VIEWS } from "../components/Sidebar";
import { UiModeProvider, useUiMode } from "../mode";
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
    render(<Sidebar active="home" onSelect={() => undefined} simple />);
    const labels = screen.getAllByRole("button").map((node) => node.textContent);
    expect(labels).toEqual(["Inicio", "Gráfico", "Historial", "Ajustes"]);
    expect(labels).not.toContain("Consola");
    expect(SIMPLE_VIEWS.length).toBe(4);
  });

  it("pro sigue enseñando las siete", () => {
    render(<Sidebar active="home" onSelect={() => undefined} />);
    expect(screen.getAllByRole("button").length).toBe(VIEWS.length);
    expect(VIEWS.length).toBe(7);
  });

  it("el modo se anuncia en el DOM, no solo con color", () => {
    const { container } = render(<Sidebar active="home" onSelect={() => undefined} simple />);
    expect(container.querySelector("nav")?.dataset.mode).toBe("simple");
  });
});

describe("vistas de principiante", () => {
  it("el inicio fácil dice que está conectando en vez de inventar cifras", () => {
    render(
      <UiModeProvider>
        <SimpleDashboard />
      </UiModeProvider>,
    );
    expect(screen.getByText("Conectando con el motor…")).toBeInTheDocument();
  });

  it("los ajustes simples piden solo tres números", () => {
    const { container } = render(
      <UiModeProvider>
        <SimpleSettings />
      </UiModeProvider>,
    );
    expect(container.querySelectorAll("input[type='range']").length).toBe(3);
    expect(screen.getByText("Cuánto arriesgar en cada operación")).toBeInTheDocument();
    expect(screen.getByText("Cuánto puedes perder en un día")).toBeInTheDocument();
    expect(screen.getByText("Operaciones máximas al día")).toBeInTheDocument();
  });
});
