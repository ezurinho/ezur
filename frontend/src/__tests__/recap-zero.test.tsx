import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecapLine, type Recap } from "../pages/SimpleDashboard";

function recap(overrides: Partial<Recap>): Recap {
  return {
    total: 0,
    wins: 0,
    losses: 0,
    unmeasured: 0,
    worst: 0,
    best: 0,
    mainReason: null,
    fees: 0,
    gross: 0,
    ...overrides,
  };
}

function boldOf(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll("b")).filter(
    (node) => node.textContent === text,
  );
}

describe("resumen del día: un cero no lleva tono", () => {
  it("0 a favor no se pinta de verde", () => {
    const { container } = render(
      <RecapLine recap={recap({ total: 2, wins: 0, losses: 2, worst: -4, gross: -8 })} />,
    );
    expect(boldOf(container, "0").map((node) => node.className)).toEqual([""]);
    expect(boldOf(container, "2").map((node) => node.className)).toContain("tone-bad");
  });

  it("0 en contra no se pinta de rojo, y el 1 a favor sigue verde", () => {
    const { container } = render(
      <RecapLine recap={recap({ total: 1, wins: 1, losses: 0, best: 6, gross: 6 })} />,
    );
    expect(boldOf(container, "0").map((node) => node.className)).toEqual([""]);
    expect(boldOf(container, "1").map((node) => node.className)).toContain("tone-good");
  });
});
