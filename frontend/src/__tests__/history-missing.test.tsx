import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DynamicTable } from "../components/DynamicTable";
import { SIMPLE_COLUMNS } from "../pages/History";

describe("historial básico con campos ausentes", () => {
  it("no convierte null en una dirección o un motivo inventados", () => {
    render(
      <DynamicTable
        rows={[{ closed_ts: null, side: null, pnl_net: null, exit_reason: null }]}
        columns={SIMPLE_COLUMNS}
      />,
    );
    expect(screen.queryByText("null")).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("sigue traduciendo un motivo conocido", () => {
    render(
      <DynamicTable
        rows={[{ closed_ts: "2026-11-24T08:00:00Z", side: "short", pnl_net: 1, exit_reason: "stop" }]}
        columns={SIMPLE_COLUMNS}
      />,
    );
    expect(screen.getByText("saltó el stop")).toBeInTheDocument();
    expect(screen.getByText("venta")).toBeInTheDocument();
  });
});
