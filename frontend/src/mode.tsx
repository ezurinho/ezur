import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Two ways to look at the same engine.
 *
 * ``simple`` is for someone who has never traded: four views, three numbers and
 * a sentence that says what the bot is doing. ``advanced`` is everything the
 * terminal knows: phases, metrics, gates, funnel, console.
 *
 * The choice lives in localStorage because a UI preference is not engine state
 * and must survive a reload without a round trip to the server.
 */
export type UiMode = "simple" | "advanced";

const STORAGE_KEY = "ezur.ui.mode";

interface ModeContextValue {
  mode: UiMode;
  setMode: (mode: UiMode) => void;
  toggle: () => void;
  isSimple: boolean;
}

const ModeContext = createContext<ModeContextValue | null>(null);

function readStored(): UiMode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "simple" || stored === "advanced") return stored;
  } catch {
    /* private mode or blocked storage: fall through to the default */
  }
  // First visit: start simple. A beginner should not have to hide a console.
  return "simple";
}

export function UiModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<UiMode>(readStored);

  const setMode = useCallback((next: UiMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* the preference is a nicety, not a requirement */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.uiMode = mode;
  }, [mode]);

  const value = useMemo<ModeContextValue>(
    () => ({
      mode,
      setMode,
      toggle: () => setMode(mode === "simple" ? "advanced" : "simple"),
      isSimple: mode === "simple",
    }),
    [mode, setMode],
  );

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useUiMode(): ModeContextValue {
  const context = useContext(ModeContext);
  if (!context) {
    throw new Error("useUiMode must be used inside UiModeProvider");
  }
  return context;
}
