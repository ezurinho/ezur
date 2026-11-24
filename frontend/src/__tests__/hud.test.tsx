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

  it("gives each instance its own gradient id", () => {
    const { container } = render(
      <>
        <Sparkline values={[1, 2, 3]} />
        <Sparkline values={[2, 4, 6]} />
      </>,
    );
    const ids = [...container.querySelectorAll("linearGradient")].map(
      (node) => node.getAttribute("id"),
    );
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    for (const node of container.querySelectorAll("path.area")) {
      const href = node.getAttribute("fill") ?? "";
      expect(ids).toContain(href.replace(/^url\(#|\)$/g, ""));
    }
  });
});

describe("Gauge", () => {
  it("shows the usage percentage and the raw numbers", () => {
    render(<Gauge value={3} max={6} label="operaciones" unit="ops" />);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("3 / 6 ops")).toBeInTheDocument();
  });

  it("clamps the arc at 100 % but still reports the real overrun", () => {
    render(<Gauge value={9} max={3} label="operaciones" unit="ops" />);
    expect(screen.getByText("300%")).toBeInTheDocument();
    expect(screen.getByText("9 / 3 ops")).toBeInTheDocument();
  });

  it("survives a zero limit", () => {
    render(<Gauge value={1} max={0} label="límite" />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
