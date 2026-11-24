import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: {} }));

import { hourZoneNote } from "../pages/Stats";

describe("reloj del desglose por hora", () => {
  it("nombra la zona con la que el servidor agrupó", () => {
    const note = hourZoneNote("America/New_York");
    expect(note).toContain("America/New_York");
    expect(note).toContain("no por el de tu equipo");
    expect(hourZoneNote("UTC")).toContain("(UTC)");
  });

  it("sin zona no inventa una: solo dice de qué reloj habla", () => {
    const note = hourZoneNote(undefined);
    expect(note).toContain("reloj de la sesión");
    expect(note).not.toContain("UTC");
  });
});
