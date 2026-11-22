import { useState } from "react";
import { Sidebar, VIEWS } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { StoreProvider, useStore } from "./store";
import { DashboardPage } from "./pages/Dashboard";
import { ChartPage } from "./pages/Chart";
import { OperationsPage } from "./pages/Operations";
import { HistoryPage } from "./pages/History";
import { StatsPage } from "./pages/Stats";
import { ConfigPage } from "./pages/Config";
import { ConsolePage } from "./pages/Console";

const PAGES: Record<string, () => JSX.Element> = {
  home: DashboardPage,
  chart: ChartPage,
  operations: OperationsPage,
  history: HistoryPage,
  stats: StatsPage,
  config: ConfigPage,
  console: ConsolePage,
};

function Shell() {
  const { snapshot, connection } = useStore();
  const [view, setView] = useState(VIEWS[0].id);
  const Page = PAGES[view] ?? DashboardPage;

  return (
    <div className="app-shell">
      <TopBar snapshot={snapshot} connection={connection} />
      <div className="app-body">
        <Sidebar active={view} onSelect={setView} />
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
      <Shell />
    </StoreProvider>
  );
}
