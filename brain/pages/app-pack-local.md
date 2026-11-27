---
id: app-pack-local
title: "Empaquetado local: test, lint, pack y refresco de Downloads"
category: reference
status: active
tags: [electron, pack, despliegue]
created: "2026-11-27T16:08:22"
updated: "2026-11-27T16:08:22"
---

<!-- compiled_truth -->
Cualquier cambio que afecte a la aplicación (main.js, preload.js, src/**, renderer/**, assets/**, package.json) termina refrescando la copia desempaquetada en `%USERPROFILE%\Downloads\ezuryseth`.

Secuencia obligatoria: `npm test`, `npm run lint`, `npm run pack`. `pack` acaba ejecutando `scripts/publish-local.js`, que copia el build, verifica el hash del ejecutable copiado y corre el smoke test del paquete; si algo falla, conserva la copia anterior. `npm run publish:local` sólo recopia sin reconstruir.

Es una copia local sin firmar. No se crean releases, instaladores ni se sube la versión salvo que el usuario lo pida.


## Timeline

- time: 2026-11-27T16:08:22
  kind: decision
  summary: "Created this page: Empaquetado local: test, lint, pack y refresco de Downloads"
  source: created via brain create-page
  affects: [app-pack-local]

- time: 2026-11-27T16:08:22
  kind: decision
  summary: Documenta el flujo obligatorio de empaquetado
  source: brain update-truth
  affects: [app-pack-local]
