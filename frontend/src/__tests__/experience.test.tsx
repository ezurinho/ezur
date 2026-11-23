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
