import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KvPanel } from "../components/KvPanel";
import { PhaseTimeline } from "../components/PhaseTimeline";
import { SymbolsTable } from "../components/SymbolsTable";
import { ZoneLayer } from "../components/ZoneLayer";
import { MarkerLayer } from "../components/MarkerLayer";
import type { Instrument, Marker, Phase, Zone } from "../types";

function makePhases(count: number): Phase[] {
  return Array.from({ length: count }, (_, index) => ({
    key: `phase-${index}`,
    label: `Fase ${index}`,
    status: "pending" as const,
    ts: null,
    detail: null,
  }));
}

function makeZone(overrides: Partial<Zone> = {}): Zone {
  return {
    id: "zone-1",
    kind: "band",
    from_ts: "2026-01-15T14:30:00Z",
    price_low: 99.5,
    price_high: 101,
    label: "Zona",
    to_ts: null,
    style: {},
    active: true,
    source: "strategy",
    meta: {},
    ...overrides,
  };
}

function makeInstrument(symbol: string): Instrument {
  return {
    symbol,
    role: "context",
    enabled: true,
    tick_size: 0.25,
    tick_value: 0.5,
    point_value: 2,
    currency: "USD",
    decimals: 2,
  };
}

function makeMarker(overrides: Partial<Marker> = {}): Marker {
  return {
    id: "marker-1",
    ts: "2026-01-15T15:00:00Z",
    price: 100,
    kind: "entry",
    side: "long",
    label: "Entrada",
    source: "strategy",
    meta: {},
    ...overrides,
  };
}

describe("PhaseTimeline", () => {
  it("renders 0, 3 and 12 phases without assuming a fixed count", () => {
    for (const count of [0, 3, 12]) {
      const { container, unmount } = render(<PhaseTimeline phases={makePhases(count)} />);
      expect(container.querySelectorAll("[data-phase]").length).toBe(count);
      unmount();
    }
  });

  it("falls back to an empty label when there are no phases", () => {
    render(<PhaseTimeline phases={[]} emptyLabel="Sin fases definidas" />);
    expect(screen.getByText("Sin fases definidas")).toBeInTheDocument();
  });

  it("reflects the status sent by the backend", () => {
    const phases = makePhases(1).map((phase) => ({ ...phase, status: "active" as const }));
    const { container } = render(<PhaseTimeline phases={phases} />);
    expect(container.querySelector("[data-phase]")?.getAttribute("data-status")).toBe("active");
  });

  it("el estado de una fase no vive solo en el color", () => {
    const statuses = ["done", "active", "pending"] as const;
    const phases = makePhases(3).map((phase, index) => ({
      ...phase,
      status: statuses[index],
    }));
    const { container } = render(<PhaseTimeline phases={phases} />);
    const marks = [...container.querySelectorAll(".phase-mark")].map((el) => el.textContent);
    expect(marks).toEqual(["✓", "▸", "·"]);
    expect(container.textContent).toContain(": hecha");
    expect(container.textContent).toContain(": en curso");
    expect(container.textContent).toContain(": pendiente");
  });
});

describe("KvPanel", () => {
  it("renders entries without knowing their names", () => {
    render(
      <KvPanel
        entries={{
          arbitrary_key: {
            label: "Etiqueta libre",
            value: 12.5,
            format: "price",
            unit: "pts",
            tone: "neutral",
            group: null,
          },
        }}
      />,
    );
    expect(screen.getByText("Etiqueta libre")).toBeInTheDocument();
    expect(screen.getByText("12.50 pts")).toBeInTheDocument();
  });

  it("honours the format hint instead of a global decimal setting", () => {
    const { container } = render(
      <KvPanel
        entries={{
          pct: { label: "Pct", value: 3.14159, format: "pct", unit: null, tone: "good", group: null },
          text: { label: "Texto", value: "neutral", format: "text", unit: null, tone: "warn", group: null },
          flag: { label: "Bandera", value: true, format: "boolean", unit: null, tone: "neutral", group: null },
        }}
      />,
    );
    const rows = Array.from(container.querySelectorAll("[data-kv]")).map((row) =>
      row.getAttribute("data-format"),
    );
    expect(rows).toEqual(["pct", "text", "boolean"]);
    expect(screen.getByText("3.14%")).toBeInTheDocument();
    expect(screen.getByText("sí")).toBeInTheDocument();
  });

  it("shows the empty label when there is nothing to render", () => {
    render(<KvPanel entries={{}} emptyLabel="Sin métricas" />);
    expect(screen.getByText("Sin métricas")).toBeInTheDocument();
  });
});

describe("ZoneLayer", () => {
  it("renders known kinds", () => {
    const { container } = render(<ZoneLayer zones={[makeZone(), makeZone({ id: "z2", kind: "line" })]} />);
    expect(container.querySelectorAll("[data-zone]").length).toBe(2);
  });

  it("skips an unsupported kind without crashing", () => {
    const { container } = render(<ZoneLayer zones={[makeZone({ kind: "hexagon" })]} />);
    expect(container.querySelectorAll("[data-zone]").length).toBe(0);
  });

  it("marks inactive zones", () => {
    const { container } = render(<ZoneLayer zones={[makeZone({ active: false })]} />);
    expect(container.querySelector("[data-zone]")?.getAttribute("data-active")).toBe("false");
  });

  it("does not hide a zone just because the server omitted its label", () => {
    render(<ZoneLayer zones={[makeZone({ label: null })]} />);
    expect(screen.getByText("rango")).toBeInTheDocument();
  });
});

describe("MarkerLayer", () => {
  it("skips an unsupported marker kind", () => {
    const { container } = render(
      <MarkerLayer markers={[makeMarker(), makeMarker({ id: "m2", kind: "arrow" })]} />,
    );
    expect(container.querySelectorAll("[data-marker]").length).toBe(1);
  });

  it("names an unlabeled marker instead of leaving only a dot", () => {
    render(<MarkerLayer markers={[makeMarker({ label: null, kind: "warning" })]} />);
    expect(screen.getByText("aviso")).toBeInTheDocument();
  });
});

describe("SymbolsTable", () => {
  it("renders one row per configured instrument", () => {
    const { container } = render(
      <SymbolsTable
        instruments={[makeInstrument("AAA"), makeInstrument("BBB")]}
        quotes={{
          AAA: { last: 100.25, bid: 100.25, ask: 100.5, change: 0.5, change_pct: 0.5, ts: null },
        }}
      />,
    );
    expect(container.querySelectorAll("[data-symbol]").length).toBe(2);
    expect(screen.getByText("AAA")).toBeInTheDocument();
    expect(screen.getByText("BBB")).toBeInTheDocument();
    expect(screen.getByText("0.50%")).toBeInTheDocument();
  });

  it("renders a placeholder when no instrument is configured", () => {
    render(<SymbolsTable instruments={[]} quotes={{}} />);
    expect(screen.getByText("Sin instrumentos configurados")).toBeInTheDocument();
  });
});
