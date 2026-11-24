import { describe, expect, it } from "vitest";

import { consoleEmptyText } from "../pages/Console";

describe("texto vacío de la consola", () => {
  it("no afirma que no hay eventos antes de haberlos pedido", () => {
    expect(
      consoleEmptyText({ events: 0, loaded: false, paused: false, hidden: false }),
    ).toContain("Leyendo");
  });

  it("con eventos cargados el vacío es del filtro, no de la lista", () => {
    expect(
      consoleEmptyText({ events: 12, loaded: true, paused: false, hidden: false }),
    ).toContain("filtro");
  });

  it("con pausa o pestaña oculta explica por qué la lista no se llena", () => {
    expect(
      consoleEmptyText({ events: 0, loaded: true, paused: true, hidden: false }),
    ).toContain("pausa");
    expect(
      consoleEmptyText({ events: 0, loaded: true, paused: false, hidden: true }),
    ).toContain("segundo plano");
  });

  it("solo dice que el servidor no tiene eventos tras comprobarlo", () => {
    expect(
      consoleEmptyText({ events: 0, loaded: true, paused: false, hidden: false }),
    ).toContain("servidor");
  });
});
