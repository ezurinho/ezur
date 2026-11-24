import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedNumber } from "../components/AnimatedNumber";

describe("números animados", () => {
  it("un valor no finito se muestra como dato ausente, no como NaN", () => {
    const { rerender } = render(<AnimatedNumber value={Number.NaN} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();

    rerender(<AnimatedNumber value={Number.POSITIVE_INFINITY} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
  });
});
