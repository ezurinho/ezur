import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../theme";

const chart = vi.hoisted(() => {
  const areaData = vi.fn();
  const markData = vi.fn();
  const addAreaSeries = vi.fn(() => ({
    setData: areaData,
    createPriceLine: vi.fn(),
  }));
  const addLineSeries = vi.fn(() => ({
    setData: markData,
  }));
  const createChart = vi.fn(() => ({
    addAreaSeries,
    addLineSeries,
    timeScale: () => ({ fitContent: vi.fn() }),
    remove: vi.fn(),
  }));
  return { areaData, markData, addAreaSeries, addLineSeries, createChart };
});

vi.mock("lightweight-charts", () => ({ createChart: chart.createChart }));

import { EquityChart } from "../components/EquityChart";

describe("curva de equidad", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("manda las marcas intradía a su propia serie, no a la auditada", () => {
    const points = [
      { ts: "2026-11-26T17:00:00+00:00", equity: 25000 },
      { ts: "2026-11-26T17:30:00+00:00", equity: 25010 },
    ];
    const marks = [{ ts: "2026-11-26T17:15:00+00:00", equity: 24990 }];

    render(
      <ThemeProvider>
        <EquityChart points={points} marks={marks} baseline={25000} />
      </ThemeProvider>,
    );

    expect(chart.addAreaSeries).toHaveBeenCalledTimes(1);
    expect(chart.addLineSeries).toHaveBeenCalledTimes(1);

    const area = chart.areaData.mock.calls[0][0] as { time: number; value: number }[];
    const line = chart.markData.mock.calls[0][0] as { time: number; value: number }[];

    expect(area.map((point) => point.value)).toEqual([25000, 25010]);
    expect(line.map((point) => point.value)).toEqual([24990]);
    expect(area.map((point) => point.time)).not.toContain(
      Date.parse(marks[0].ts) / 1000,
    );
  });
});
