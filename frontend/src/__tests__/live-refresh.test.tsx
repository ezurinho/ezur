import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SnapshotData } from "../types";

const store = vi.hoisted(() => ({ snapshot: null as unknown }));
const api = vi.hoisted(() => ({
  trades: vi.fn(() => Promise.resolve([])),
  tradesCsvUrl: vi.fn(() => "/trades.csv"),
  stats: vi.fn(() =>
    Promise.resolve({
      closed: { trades: 0, impossible_durations: 0 },
      by_hour: {},
      by_weekday: {},
      by_month: {},
      by_side: {},
      by_day: {},
      equity: [],
    }),
  ),
  validation: vi.fn(() => Promise.resolve(null)),
  funnel: vi.fn(() => Promise.resolve(null)),
}));

vi.mock("../store", () => ({ useStore: () => ({ snapshot: store.snapshot }) }));
vi.mock("../api", () => ({ api }));

import { UiModeProvider } from "../mode";
import { HistoryPage } from "../pages/History";
import { StatsPage } from "../pages/Stats";

function snapshot(total: number, daily: number): SnapshotData {
  return {
    session: {
      id: "2026-11-24:CRYPTO24",
      label: "CRYPTO24",
      is_open: true,
      open_ts: "2026-11-24T00:00:00Z",
      close_ts: "2026-11-24T23:59:00Z",
      phase: "open",
    },
    stats: { closed: { trades: total } },
    risk: { daily_trades: daily, limits: { initial_capital: 25000 } },
  } as unknown as SnapshotData;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  store.snapshot = snapshot(10, 8);
});

describe("refresco al cerrar una operación", () => {
  it("Historial nota el primer cierre del día siguiente aunque daily_trades baje a cero", async () => {
    const view = render(
      <UiModeProvider>
        <HistoryPage />
      </UiModeProvider>,
    );
    await waitFor(() => expect(api.trades).toHaveBeenCalledTimes(1));

    store.snapshot = snapshot(11, 0);
    view.rerender(
      <UiModeProvider>
        <HistoryPage />
      </UiModeProvider>,
    );
    await waitFor(() => expect(api.trades).toHaveBeenCalledTimes(2));
  });

  it("Estadísticas también se refresca con el total, no con el contador diario", async () => {
    const view = render(<StatsPage />);
    await waitFor(() => expect(api.stats).toHaveBeenCalledTimes(1));

    store.snapshot = snapshot(11, 0);
    view.rerender(<StatsPage />);
    await waitFor(() => expect(api.stats).toHaveBeenCalledTimes(2));
  });

  it("un snapshot sin cambios no dispara otra petición", async () => {
    const view = render(
      <UiModeProvider>
        <HistoryPage />
      </UiModeProvider>,
    );
    await waitFor(() => expect(api.trades).toHaveBeenCalledTimes(1));

    store.snapshot = snapshot(10, 7);
    view.rerender(
      <UiModeProvider>
        <HistoryPage />
      </UiModeProvider>,
    );
    expect(api.trades).toHaveBeenCalledTimes(1);
  });
});
