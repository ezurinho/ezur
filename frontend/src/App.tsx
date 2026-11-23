import { useState } from "react";
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
import { UiModeProvider, useUiMode } from "./mode";

const PAGES: Record<string, () => JSX.Element> = {
  home: DashboardPage,
  chart: ChartPage,
  operations: OperationsPage,
  history: HistoryPage,
  stats: StatsPage,
  config: ConfigPage,
  console: ConsolePage,
  settings: SimpleSettings,
  simple_home: SimpleDashboard,
};

function Shell() {
  const { snapshot, connection } = useStore();
  const { isSimple } = useUiMode();
  const [view, setView] = useState("home");

  // A view that only exists in one mode must not survive a mode change.
  const available = isSimple ? SIMPLE_VIEWS : VIEWS;
  const current = available.some((item) => item.id === view) ? view : "home";
  const Page = isSimple && current === "home" ? PAGES.simple_home : (PAGES[current] ?? DashboardPage);

  return (
    <div className={`app-shell ${isSimple ? "mode-simple" : "mode-advanced"}`}>
      <TopBar snapshot={snapshot} connection={connection} />
      <div className="app-body">
        <Sidebar active={current} onSelect={setView} simple={isSimple} />
        <main className="app-main">
          <Page />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <UiModeProvider>
        <Shell />
      </UiModeProvider>
    </StoreProvider>
  );
}
