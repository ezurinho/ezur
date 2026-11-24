import { describe, expect, it } from "vitest";

import { localStamp } from "../pages/Console";

describe("hora de la consola", () => {
  const now = new Date(2026, 10, 24, 12, 0, 0);

  it("un evento de hoy se enseña solo con la hora, en tu reloj", () => {
    const event = new Date(2026, 10, 24, 9, 5, 7);
    expect(localStamp(event.toISOString(), now)).toBe(
      event.toLocaleTimeString(undefined, { hour12: false }),
    );
  });

  it("un evento de otro día lleva la fecha delante", () => {
    const event = new Date(2026, 10, 23, 23, 40, 0);
    const day = event.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
    const time = event.toLocaleTimeString(undefined, { hour12: false });
    expect(localStamp(event.toISOString(), now)).toBe(`${day} ${time}`);
  });

  it("no inventa una hora si la marca viene rota", () => {
    expect(localStamp("basura")).toBe("");
  });
});
