import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import { ThemeProvider, useTheme } from "../theme";

function Probe() {
  const { theme, choice, setTheme, accent, setAccent } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="choice">{choice}</span>
      <span data-testid="accent">{accent ?? "ninguno"}</span>
      <button type="button" onClick={() => setAccent("#4c8dff")}>
        azul
      </button>
      <button type="button" onClick={() => setAccent("rojo; background:url(x)")}>
        roto
      </button>
      <button type="button" onClick={() => setAccent(null)}>
        limpio
      </button>
      <button type="button" onClick={() => setTheme("auto")}>
        auto
      </button>
    </div>
  );
}

function mockSystem(dark: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("dark") ? dark : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function renderProbe() {
  return render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );
}

describe("acento del operador", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.removeProperty("--accent");
    document.documentElement.style.removeProperty("--glow-accent");
    mockSystem(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("escribe el acento como variable CSS y lo recuerda", () => {
    renderProbe();
    act(() => screen.getByText("azul").click());

    expect(document.documentElement.style.getPropertyValue("--accent")).toBe("#4c8dff");
    expect(window.localStorage.getItem("ezur.accent")).toBe("#4c8dff");
    expect(screen.getByTestId("accent")).toHaveTextContent("#4c8dff");
  });

  it("ignora lo que no es un color", () => {
    renderProbe();
    act(() => screen.getByText("roto").click());

    expect(document.documentElement.style.getPropertyValue("--accent")).toBe("");
    expect(window.localStorage.getItem("ezur.accent")).toBeNull();
    expect(screen.getByTestId("accent")).toHaveTextContent("ninguno");
  });

  it("restablecer quita la variable en línea en vez de adivinar el color del tema", () => {
    window.localStorage.setItem("ezur.accent", "#ff5c9a");
    renderProbe();
    expect(document.documentElement.style.getPropertyValue("--accent")).toBe("#ff5c9a");

    act(() => screen.getByText("limpio").click());

    expect(document.documentElement.style.getPropertyValue("--accent")).toBe("");
    expect(window.localStorage.getItem("ezur.accent")).toBeNull();
  });
});

describe("modo automático", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("con el sistema en oscuro usa el tema oscuro por defecto", () => {
    mockSystem(true);
    renderProbe();
    act(() => screen.getByText("auto").click());

    expect(screen.getByTestId("choice")).toHaveTextContent("auto");
    expect(screen.getByTestId("theme")).toHaveTextContent("wraith");
    expect(document.documentElement.dataset.theme).toBe("wraith");
  });

  it("con el sistema en claro usa el tema de día", () => {
    mockSystem(false);
    renderProbe();
    act(() => screen.getByText("auto").click());

    expect(screen.getByTestId("theme")).toHaveTextContent("daylight");
    expect(document.documentElement.dataset.theme).toBe("daylight");
    expect(window.localStorage.getItem("ezur.theme")).toBe("auto");
  });
});
