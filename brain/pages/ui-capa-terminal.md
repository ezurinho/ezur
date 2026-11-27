---
id: ui-capa-terminal
title: "Interfaz plana tipo terminal: sin glow, sin cristal, sin hero"
category: decision
status: active
tags: [frontend, diseno, css]
created: "2026-11-27T16:08:22"
updated: "2026-11-27T16:08:22"
---

<!-- compiled_truth -->
La interfaz se aplana con una capa al final de `frontend/src/styles.css`; no se reescribieron componentes.

Reglas: un panel es un rectángulo con hairline de 1 px y radio 2 px, sin sombras ni `backdrop-filter`; un solo acento apagado para lo interactivo y verde/rojo reservados al resultado; cifras en monoespaciada tabular; nada de lavados radiales, rejillas de fondo, bordes luminosos animados ni orbes decorativos; el panel de estado es una frase, no un titular de landing; las tarjetas no se numeran 01/02/03.

La paleta nueva está acotada a `:root:is([data-theme="wraith"], :not([data-theme]))`. Sin esa acotación, el `:root` final pisa los bloques `[data-theme]` y el selector de temas enseña muestras que ya no aplica.


## Timeline

- time: 2026-11-27T16:08:22
  kind: decision
  summary: "Created this page: Interfaz plana tipo terminal: sin glow, sin cristal, sin hero"
  source: created via brain create-page
  affects: [ui-capa-terminal]

- time: 2026-11-27T16:08:22
  kind: decision
  summary: Fija las reglas visuales que quitaron el aspecto generado
  source: brain update-truth
  affects: [ui-capa-terminal]
