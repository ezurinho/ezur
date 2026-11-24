import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SnapshotData } from "../types";

const store = vi.hoisted(() => ({ snapshot: null as unknown }));
const api = vi.hoisted(() => ({ config: vi.fn() }));

vi.mock("../store", () => ({ useStore: () => ({ snapshot: store.snapshot }) }));
vi.mock("../api", () => ({ api }));

import { UiModeProvider } from "../mode";
import { ToastProvider } from "../toast";
import { SimpleSettings } from "../pages/SimpleSettings";

function snapshot(effectiveRisk: number): SnapshotData {
  return {
    risk: {
      equity: 25000,
      limits: { risk_per_trade_pct: effectiveRisk },
    },
  } as unknown as SnapshotData;
}

function renderSettings() {
  return render(
    <UiModeProvider>
      <ToastProvider>
        <SimpleSettings />
      </ToastProvider>
    </UiModeProvider>,
  );
}

describe("Ajustes simples: riesgo efectivo", () => {
  beforeEach(() => {
    window.localStorage.clear();
    api.config.mockReset();
    api.config.mockResolvedValue({
      risk: { risk_per_trade_pct: 1, max_daily_loss_pct: 3, max_trades_per_day: 8 },
    });
  });

  it("explica que el motor usa menos riesgo que el configurado", async () => {
    store.snapshot = snapshot(0.25);
    const { container } = renderSettings();

    await waitFor(() =>
      expect(container.querySelector("[data-effective-risk]")).not.toBeNull(),
    );
    const note = container.querySelector("[data-effective-risk]")?.textContent ?? "";
    expect(note).toMatch(/0[.,]25 % efectivo/);
    expect(note).toMatch(/1 % configurado/);
  });

  it("no pinta la nota cuando el efectivo coincide con el configurado", async () => {
    store.snapshot = snapshot(1);
    const { container } = renderSettings();

    await waitFor(() =>
      expect(container.querySelectorAll("input[type='range']").length).toBe(3),
    );
    expect(container.querySelector("[data-effective-risk]")).toBeNull();
  });
});
