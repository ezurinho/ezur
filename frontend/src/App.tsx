import { useCallback, useEffect, useMemo, useState } from "react";
import { Sidebar, SIMPLE_VIEWS, VIEWS } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { StoreProvider, useStore } from "./store";
import { DashboardPage } from "./pages/Dashboard";
import { ChartPage } from "./pages/Chart";
import { OperationsPage } from "./pages/Operations";
import { HistoryPage } from "./pages/History";
import { StatsPage } from "./pages/Stats";
import { ConfigPage } from "./pages/Config";
import { ConsolePage } from "./pages/Console";
import { SimpleDashboard } from "./pages/SimpleDashboard";
import { SimpleSettings } from "./pages/SimpleSettings";
import { LabPage } from "./pages/Lab";
import { UiModeProvider, useUiMode } from "./mode";
import { ThemeProvider, THEMES, useTheme } from "./theme";
import { ToastProvider, useToast } from "./toast";
import { CommandPalette, type PaletteItem } from "./components/CommandPalette";
import { Shortcuts } from "./components/Shortcuts";
import { api } from "./api";

const PAGES: Record<string, () => JSX.Element> = {
  home: DashboardPage,
  chart: ChartPage,
  operations: OperationsPage,
  history: HistoryPage,
  stats: StatsPage,
  lab: LabPage,
  config: ConfigPage,
  console: ConsolePage,
  settings: SimpleSettings,
  simple_home: SimpleDashboard,
};

function Shell() {
  const { snapshot, connection } = useStore();
  const { isSimple, setMode } = useUiMode();
  const { setTheme } = useTheme();
  const { push } = useToast();
  const [view, setView] = useState("home");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  // A view that only exists in one mode must not survive a mode change.
  const available = isSimple ? SIMPLE_VIEWS : VIEWS;
  const current = available.some((item) => item.id === view) ? view : "home";
  const Page = isSimple && current === "home" ? PAGES.simple_home : (PAGES[current] ?? DashboardPage);

  const control = useCallback(
    async (action: "start" | "pause" | "stop", label: string) => {
      try {
        await api.bot(action);
        push({ title: label, tone: "good", detail: "El motor ha aceptado la orden." });
      } catch (cause) {
        push({ title: `${label}: no se pudo`, tone: "bad", detail: (cause as Error).message });
      }
    },
    [push],
  );

  const paletteItems = useMemo<PaletteItem[]>(() => {
    const views: PaletteItem[] = available.map((item) => ({
      id: `view-${item.id}`,
      label: item.label,
      hint: item.hint,
      group: "Vista",
      keywords: item.id,
      run: () => setView(item.id),
    }));
    const controls: PaletteItem[] = [
      { id: "act-start", label: "Reanudar el motor", group: "Motor", hint: "running", run: () => void control("start", "Motor reanudado") },
      { id: "act-pause", label: "Pausar el motor", group: "Motor", hint: "paused", run: () => void control("pause", "Motor en pausa") },
      { id: "act-stop", label: "Detener el motor", group: "Motor", hint: "stopped", run: () => void control("stop", "Motor detenido") },
      {
        id: "act-mode",
        label: isSimple ? "Cambiar a modo avanzado" : "Cambiar a modo básico",
        group: "Interfaz",
        run: () => setMode(isSimple ? "advanced" : "simple"),
      },
      {
        id: "act-alert-test",
        label: "Enviar alerta de prueba",
        hint: "webhook",
        group: "Alerta",
        keywords: "test webhook notificacion",
        run: () => {
          void api
            .alertsTest()
            .then((result) =>
              push(
                result.sent
                  ? { title: "Alerta de prueba entregada", tone: "good" }
                  : {
                      title: "La alerta no salió",
                      detail: result.reason ?? "sin motivo informado",
                      tone: "warn",
                    },
              ),
            )
            .catch((cause: Error) =>
              push({ title: "La alerta no salió", detail: cause.message, tone: "bad" }),
            );
        },
      },
      {
        id: "act-reset-stats",
        label: "Reiniciar estadísticas…",
        hint: "borra operaciones",
        group: "Datos",
        keywords: "borrar limpiar reset",
        run: () => {
          void api
            .statsResetPreview()
            .then((preview) => {
              const ok = window.confirm(
                `¿Borrar ${preview.trades} operación(es) y el historial de pruebas?
` +
                  "Esto no se puede deshacer. El motor sigue corriendo.",
              );
              if (!ok) return;
              return api
                .resetStats(false)
                .then(() =>
                  push({ title: "Estadísticas reiniciadas", detail: "El motor no se ha tocado.", tone: "good" }),
                );
            })
            .catch((cause: Error) =>
              push({ title: "No se pudo reiniciar", detail: cause.message, tone: "bad" }),
            );
        },
      },
      ...THEMES.map((theme) => ({
        id: `theme-${theme.id}`,
        label: `Tema ${theme.label}`,
        hint: theme.hint,
        group: "Tema",
        keywords: "color apariencia",
        run: () => setTheme(theme.id),
      })),
    ];
    return [...views, ...controls];
  }, [available, control, isSimple, setMode, setTheme]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target?.isContentEditable;

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setShortcutsOpen(false);
        return;
      }
      if (event.key === "?" && !typing && !paletteOpen) {
        event.preventDefault();
        setShortcutsOpen((open) => !open);
        return;
      }
      if (typing || paletteOpen || shortcutsOpen || event.metaKey || event.ctrlKey || event.altKey) return;
      // 1..7 jump between the views the current mode shows.
      const index = Number(event.key) - 1;
      if (Number.isInteger(index) && index >= 0 && index < available.length) {
        setView(available[index].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [available, paletteOpen, shortcutsOpen]);

  return (
    <div className={`app-shell ${isSimple ? "mode-simple" : "mode-advanced"}`}>
      <TopBar snapshot={snapshot} connection={connection} onOpenPalette={() => setPaletteOpen(true)} />
      <div className="app-body">
        <Sidebar active={current} onSelect={setView} simple={isSimple} />
        <main className="app-main">
          <div className="page-swap" key={current}>
            <Page />
          </div>
        </main>
      </div>
      <CommandPalette open={paletteOpen} items={paletteItems} onClose={() => setPaletteOpen(false)} />
      <Shortcuts open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} views={available} />
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <ThemeProvider>
        <ToastProvider>
          <UiModeProvider>
            <Shell />
          </UiModeProvider>
        </ToastProvider>
      </ThemeProvider>
    </StoreProvider>
  );
}
