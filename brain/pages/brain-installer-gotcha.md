---
id: brain-installer-gotcha
title: "El instalador de brain.md sobrescribe package.json, LICENSE y README"
category: reference
status: active
tags: [brain, instalacion, gotcha]
created: "2026-11-27T16:08:22"
updated: "2026-11-27T16:08:23"
---

<!-- compiled_truth -->
`brain-install.js` escribe su MANIFEST en la raíz del proyecto, e incluye su propio `package.json`, `LICENSE` y `README.md`. Ejecutarlo directamente sobre un repo existente los reemplaza.

Procedimiento seguro: correrlo en un directorio temporal y copiar sólo `BRAIN.md`, `bin/`, `brain/` y `skills/`. Comprobar después que el `build.files` del proyecto no incluya esas rutas.


## Timeline

- time: 2026-11-27T16:08:22
  kind: decision
  summary: "Created this page: El instalador de brain.md sobrescribe package.json, LICENSE y README"
  source: created via brain create-page
  affects: [brain-installer-gotcha]

- time: 2026-11-27T16:08:23
  kind: decision
  summary: "Aviso sobre la instalación del toolkit"
  source: brain update-truth
  affects: [brain-installer-gotcha]
