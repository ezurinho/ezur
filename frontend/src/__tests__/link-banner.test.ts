import { describe, expect, it } from "vitest";

import { ageLabel, linkBanner } from "../utils";

describe("edad de los datos", () => {
  it("no dice «hace 0 s»: un dato recién llegado es «hace un instante»", () => {
    expect(ageLabel(0)).toBe("hace un instante");
    expect(ageLabel(2_000)).toBe("hace un instante");
  });

  it("cuenta segundos, minutos y horas con su unidad", () => {
    expect(ageLabel(42_000)).toBe("hace 42 s");
    expect(ageLabel(5 * 60_000)).toBe("hace 5 min");
    expect(ageLabel(3 * 3_600_000)).toBe("hace 3 h");
  });

  it("un reloj que va hacia atrás no produce edades negativas", () => {
    expect(ageLabel(-30_000)).toBe("hace un instante");
  });
});

describe("cartel de enlace caído", () => {
  const now = 1_800_000_000_000;

  it("con la conexión abierta no hay cartel", () => {
    expect(linkBanner("open", now - 1_000, now)).toBeNull();
  });

  it("en la primera carga sin datos no se anuncia una caída", () => {
    // Las páginas ya enseñan su esqueleto; un «sin conexión» aquí sería
    // prematuro y alarmaría antes de saber si hay enlace.
    expect(linkBanner("connecting", null, now)).toBeNull();
  });

  it("cerrado sin datos dice que no hay nada que enseñar", () => {
    const banner = linkBanner("closed", null, now);
    expect(banner?.tone).toBe("bad");
    expect(banner?.title).toBe("Sin conexión con ezur");
    expect(banner?.detail).toContain("Aún no ha llegado ningún dato");
  });

  it("cerrado con datos fecha el último snapshot y avisa de que nada se actualiza", () => {
    const banner = linkBanner("closed", now - 95_000, now);
    expect(banner?.tone).toBe("bad");
    expect(banner?.detail).toContain("hace 2 min");
    expect(banner?.detail).not.toContain("hace 95");
    expect(banner?.detail).toContain("nada se está actualizando");
  });

  it("reconectando con datos previos es ámbar, no rojo: se reintenta solo", () => {
    const banner = linkBanner("connecting", now - 20_000, now);
    expect(banner?.tone).toBe("warn");
    expect(banner?.title).toBe("Reconectando con ezur");
    expect(banner?.detail).toContain("hace 20 s");
    expect(banner?.detail).toContain("Se reintenta solo");
  });
});
