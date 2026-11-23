import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Gauge } from "../components/Gauge";
import { Sparkline } from "../components/Sparkline";

describe("Sparkline", () => {
  it("draws a path for a real series", () => {
    const { container } = render(<Sparkline values={[1, 3, 2, 5, 4]} />);
    expect(container.querySelectorAll("path").length).toBeGreaterThanOrEqual(2);
  });

  it("renders an empty placeholder instead of inventing data", () => {
    const { container } = render(<Sparkline values={[7]} />);
    expect(container.querySelector("path")).toBeNull();
    expect(container.querySelector(".kpi-spark")).not.toBeNull();
  });

  it("exposes a trend label for screen readers", () => {
    render(<Sparkline values={[1, 2, 3]} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "tendencia alcista");
  });
});

describe("Gauge", () => {
  it("shows the usage percentage and the raw numbers", () => {
    render(<Gauge value={3} max={6} label="operaciones" unit="ops" />);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("3 / 6 ops")).toBeInTheDocument();
  });

  it("clamps above 100 % without breaking the arc", () => {
    render(<Gauge value={9} max={3} label="operaciones" unit="ops" />);
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("9 / 3 ops")).toBeInTheDocument();
  });

  it("survives a zero limit", () => {
    render(<Gauge value={1} max={0} label="límite" />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
