import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  bot: vi.fn(),
  closePosition: vi.fn(),
  cancelOrders: vi.fn(),
  emergency: vi.fn(),
}));

vi.mock("../api", () => ({ api }));

import { DispatchButton } from "../components/Controls";
import { ToastProvider } from "../toast";

function renderButton() {
  render(
    <ToastProvider>
      <DispatchButton action="cancel" label="Cancelar órdenes" />
    </ToastProvider>,
  );
}

beforeEach(() => {
  api.cancelOrders.mockReset();
});

describe("cancelar órdenes dice lo que pasó de verdad", () => {
  it("con la cola vacía no anuncia una cancelación", async () => {
    api.cancelOrders.mockResolvedValue({ cancelled: false, count: 0 });
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar órdenes" }));
    await waitFor(() => {
      expect(screen.getByText("No había órdenes pendientes")).toBeInTheDocument();
    });
    expect(screen.queryByText("Órdenes canceladas")).not.toBeInTheDocument();
  });

  it("con una orden pendiente dice cuántas canceló", async () => {
    api.cancelOrders.mockResolvedValue({ cancelled: true, count: 2 });
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar órdenes" }));
    await waitFor(() => {
      expect(screen.getByText("Órdenes canceladas")).toBeInTheDocument();
    });
    expect(screen.getByText("2 órdenes pendientes.")).toBeInTheDocument();
  });
});
