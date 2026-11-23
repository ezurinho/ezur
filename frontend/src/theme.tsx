import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Themes are token sets, not stylesheets: the same components, five moods.
 *
 * `hud` is the original cyan mission-control palette and stays the default so an
 * existing operator sees no change. The rest are alternates of the same design
 * language (dark, hairline, single accent) plus one light theme for daylight.
 */
export type ThemeId = "hud" | "aurora" | "ember" | "matrix" | "daylight";

export interface ThemeDefinition {
  id: ThemeId;
  label: string;
  hint: string;
  /** Three swatches for the picker: surface, accent, signal. */
  swatch: [string, string, string];
}

export const THEMES: ThemeDefinition[] = [
  {
    id: "hud",
    label: "HUD",
    hint: "cian · por defecto",
    swatch: ["#070b11", "#37e0d0", "#3ddc84"],
  },
  {
    id: "aurora",
    label: "Aurora",
    hint: "violeta · nocturno",
    swatch: ["#08060f", "#b07bff", "#4ce0a8"],
  },
  {
    id: "ember",
    label: "Ember",
    hint: "ámbar · cálido",
    swatch: ["#0b0806", "#ff9f45", "#8fd66b"],
  },
  {
    id: "matrix",
    label: "Matrix",
    hint: "lima · consola",
    swatch: ["#050a07", "#a3e635", "#22d3ee"],
  },
  {
    id: "daylight",
    label: "Día",
    hint: "claro · oficina",
    swatch: ["#f4f6fa", "#0f9e8f", "#15803d"],
  },
];

const STORAGE_KEY = "ezur.theme";

interface ThemeContextValue {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
  definition: ThemeDefinition;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemeId {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (THEMES.some((item) => item.id === stored)) return stored as ThemeId;
  } catch {
    /* storage blocked: the default is still a valid answer */
  }
  return "hud";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(readStored);

  const setTheme = useCallback((next: ThemeId) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* not worth failing the render over */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme,
      definition: THEMES.find((item) => item.id === theme) ?? THEMES[0],
    }),
    [theme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
