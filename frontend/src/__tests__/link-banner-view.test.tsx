import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LinkBanner } from "../components/LinkBanner";
import { linkBanner } from "../utils";

const NOW = 1_800_000_000_000;

describe("cartel de enlace caído en pantalla", () => {
  it("se anuncia como estado, no solo con color", () => {
    const info = linkBanner("closed", NOW - 10_000, NOW);
    if (!info) throw new Error("el cartel debería existir");
    render(<LinkBanner info={info} onRetry={() => undefined} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Sin conexión con ezur");
    expect(status).toHaveTextContent("hace 10 s");
    expect(status).toHaveAttribute("data-link-tone", "bad");
  });

  it("el botón de reintentar llama sin recargar la página", () => {
    const info = linkBanner("connecting", NOW - 5_000, NOW);
    if (!info) throw new Error("el cartel debería existir");
    const onRetry = vi.fn();
    render(<LinkBanner info={info} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Reintentar ahora" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
