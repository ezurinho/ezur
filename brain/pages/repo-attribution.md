---
id: repo-attribution
title: "Commits sin atribución a Codebuff"
category: decision
status: active
tags: [git, github, attribution]
created: "2026-11-27T17:18:50"
updated: "2026-11-28T00:52:56"
---

<!-- compiled_truth -->
# Regla

Ningún commit de este proyecto lleva `Co-Authored-By: Codebuff` ni la línea
«Generated with Codebuff». El usuario pidió quitar el contributor `codebuff-team`
de todos sus repos y la única vía es que no quede ningún commit suyo en la rama
por defecto.

# Lo que se hizo (2026-11-27)

- Se reescribió el mensaje de todos los commits en cinco repos:
  `ezur-bot`, `combat-wraith`, `discord-quest-completer`,
  `motor-ia-estrategias-btc` y `ezuryseth-releases`. En los tres restantes
  (`ezurinho`, `chess-wraith`, `nitro-wraith`) no había rastro, así que no se
  tocaron.
- Los árboles de contenido no cambiaron (mismo hash de tree en la rama por
  defecto antes y después); sólo cambiaron los SHA de commit.
- La protección de `master` en `ezur-bot` (force-push prohibido, admins
  incluidos) se quitó, se hizo el push y se restauró tal cual.
- Backups del historial anterior: `%TEMP%\ezur-rewrite-backups\*.bundle`.

# Consecuencias

- Cualquier clon anterior diverge: hay que `fetch` y `reset --hard`.
- Los 14 PRs cerrados de `ezur-bot` conservan `refs/pull/*/head` con los commits
  viejos; no cuentan para el gráfico de contributors, pero reabrirlos o fusionar
  esas ramas reintroduciría la atribución.
- La UI de GitHub actualiza el gráfico con retraso; la API ya no lista
  `codebuff-team`.



El 2026-11-28 se verificó la API pública: los seis repos públicos de `ezurinho` listan solo a `ezurinho` (o están vacíos); `codebuff-team` no figura en `ezur-bot`. La captura con dos contributors es la vista cacheada de GitHub, no un commit vivo. El guard ahora rechaza también `Generated with Codebuff`, no solo el trailer de coautoría, y tiene pruebas (`tests/test_attribution.py`); el hook y el job `attribution` de CI comparten el mismo script. No se volvió a reescribir historial.


## Timeline

- time: 2026-11-27T17:18:50
  kind: decision
  summary: "Created this page: Commits sin atribución a Codebuff"
  source: created via brain create-page
  affects: [repo-attribution]

- time: 2026-11-27T17:18:50
  kind: decision
  summary: "Los commits no llevan trailer Co-Authored-By de Codebuff; el contributor codebuff-team se eliminó reescribiendo cinco repos el 2026-11-27."
  source: "sesión 2026-11-27"
  affects: [repo-attribution]

- time: 2026-11-27T17:51:16
  kind: decision
  summary: "La regla se refuerza con .githooks/commit-msg y el job attribution de CI; ambos comparten scripts/check_attribution.py y el hook se activa con git config core.hooksPath .githooks."
  source: "sesión 2026-11-27"
  affects: [repo-attribution]

- time: 2026-11-28T00:52:56
  kind: decision
  summary: Verifica que la API ya solo lista a ezurinho y cierra el hueco del footer Generated with Codebuff en el guard y sus pruebas
  source: "Petición del usuario: quitar Codebuff siempre en GitHub; API del 2026-11-28"
  affects: [repo-attribution]
