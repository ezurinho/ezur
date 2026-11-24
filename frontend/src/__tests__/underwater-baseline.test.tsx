import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Underwater, drawdownCurve } from "../components/Underwater";

describe("bajo el agua contra el capital inicial", () => {
  it("cuenta la caída de la primera operación aunque el primer cierre ya venga por debajo", () => {
    const series = drawdownCurve(
      [{ equity: 990 }, { equity: 960 }, { equity: 980 }],
      1000,
    );
    expect(series[0]).toBeCloseTo(-1, 6);
    expect(series[1]).toBeCloseTo(-4, 6);
    expect(series[2]).toBeCloseTo(-2, 6);
  });

  it("sin capital no inventa un pico: el primer cierre es la referencia", () => {
    const series = drawdownCurve([{ equity: 100 }, { equity: 90 }], null);
    expect(series[0]).toBeCloseTo(0, 6);
    expect(series[1]).toBeCloseTo(-10, 6);
  });

  it("la vista enseña la peor caída desde el capital, no desde el primer cierre", () => {
    const { container } = render(
      <Underwater
        points={[{ equity: 990 }, { equity: 960 }, { equity: 980 }]}
        baseline={1000}
      />,
    );
    expect(container.textContent).toContain("peor caída");
    expect(container.textContent).toContain("-4.00 %");
    expect(container.textContent).not.toContain("-3.03 %");
  });
});
