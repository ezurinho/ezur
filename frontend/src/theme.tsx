import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Themes are token sets, not stylesheets: the same components, six moods.
 *
 * `wraith` is the default: carbon-black glass with an emerald signal, the same
 * language as the Nitro and Chess Wraith panels. `hud` keeps the original cyan
 * mission-control palette for operators who prefer it.
 *
 * Two things are the operator's, not the theme's: whether the choice follows the
 * system (`auto`) and the accent colour. Both live in localStorage because they
 * are reading preferences, not engine state.
 */
export type ThemeId = "wraith" | "hud" | "aurora" | "ember" | "matrix" | "daylight";
export type ThemeChoice = ThemeId | "auto";

export interface ThemeDefinition {
  id: ThemeId;
  label: string;
  hint: string;
  /** Three swatches for the picker: surface, accent, signal. */
  swatch: [string, string, string];
}

export const THEMES: ThemeDefinition[] = [
  {
    id: "wraith",
    label: "Wraith",
    hint: "esmeralda · por defecto",
    swatch: ["#050806", "#35ea86", "#9bf7c5"],
  },
  {
    id: "hud",
    label: "HUD",
    hint: "cian · clásico",
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

/** Accents that already work on both the dark and the light surfaces. */
export const ACCENT_PRESETS: { label: string; value: string }[] = [
  { label: "esmeralda", value: "#35ea86" },
  { label: "cian", value: "#37e0d0" },
  { label: "violeta", value: "#b07bff" },
  { label: "ámbar", value: "#ff9f45" },
  { label: "lima", value: "#a3e635" },
  { label: "azul", value: "#4c8dff" },
  { label: "rosa", value: "#ff5c9a" },
  { label: "rojo", value: "#ff5c6c" },
  { label: "blanco", value: "#e6edf7" },
];

const THEME_KEY = "ezur.theme";
const ACCENT_KEY = "ezur.accent";
/** Only `#rrggbb`: a colour picker value, never a style injection. */
const ACCENT_PATTERN = /^#[0-9a-fA-F]{6}$/;

interface ThemeContextValue {
  /** Resolved theme: `auto` never reaches the DOM. */
  theme: ThemeId;
  /** What the operator picked, including `auto`. */
  choice: ThemeChoice;
  setTheme: (choice: ThemeChoice) => void;
  /** Operator accent, or null to use the theme's own. */
  accent: string | null;
  setAccent: (value: string | null) => void;
  definition: ThemeDefinition;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function prefersDark(): boolean {
  try {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    return query ? query.matches : true;
  } catch {
    return true;
  }
}

function readChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === "auto") return "auto";
    if (THEMES.some((item) => item.id === stored)) return stored as ThemeId;
  } catch {
    /* storage blocked: the default is still a valid answer */
  }
  return "wraith";
}

function readAccent(): string | null {
  try {
    const stored = window.localStorage.getItem(ACCENT_KEY);
    if (stored && ACCENT_PATTERN.test(stored)) return stored;
  } catch {
    /* same */
  }
  return null;
}

/**
 * Writes the accent as an inline custom property, which wins over every theme
 * block. Clearing it removes the override instead of guessing the theme's colour.
 */
export function applyAccent(accent: string | null): void {
  const root = document.documentElement;
  if (!accent) {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--glow-accent");
    return;
  }
  root.style.setProperty("--accent", accent);
  root.style.setProperty("--glow-accent", `0 0 0 1px ${accent}33, 0 0 24px -6px ${accent}88`);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readChoice);
  const [accent, setAccentState] = useState<string | null>(readAccent);
  const [systemDark, setSystemDark] = useState<boolean>(prefersDark);

  const theme: ThemeId = choice === "auto" ? (systemDark ? "wraith" : "daylight") : choice;

  const setTheme = useCallback((next: ThemeChoice) => {
    setChoiceState(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      /* not worth failing the render over */
    }
  }, []);

  const setAccent = useCallback((next: string | null) => {
    if (next !== null && !ACCENT_PATTERN.test(next)) return;
    setAccentState(next);
    try {
      if (next) window.localStorage.setItem(ACCENT_KEY, next);
      else window.localStorage.removeItem(ACCENT_KEY);
    } catch {
      /* same */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    applyAccent(accent);
  }, [accent]);

  // `auto` has to react while the app is open, not only on reload.
  useEffect(() => {
    if (choice !== "auto") return;
    let query: MediaQueryList | null = null;
    try {
      query = window.matchMedia?.("(prefers-color-scheme: dark)") ?? null;
    } catch {
      return;
    }
    if (!query) return;
    setSystemDark(query.matches);
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, [choice]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      choice,
      setTheme,
      accent,
      setAccent,
      definition: THEMES.find((item) => item.id === theme) ?? THEMES[0],
    }),
    [theme, choice, setTheme, accent, setAccent],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
