---
id: app-scripts
title: Mapa de scripts npm y que hace cada uno
category: reference
status: active
tags: [electron, npm, scripts, build]
created: "2026-11-27T16:19:27"
updated: "2026-11-27T16:19:28"
---

<!-- compiled_truth -->
- `start`: `electron .`. `smoke`: `electron . --smoke-test`, que carga la ventana y sale con codigo 0 a los 1,5 s del `did-finish-load`.
- `test`: `node --test` sobre 16 archivos de `test/`. `lint`: `eslint .`. `check`: los dos.
- `icon`: `scripts/make-icon.js` genera `assets/icon.png` e `icon.ico`.
- `pack`: `npm run icon`, luego `electron-builder --dir`, luego `scripts/publish-local.js`. El porque del refresco a Downloads esta en [[app-pack-local]].
- `dist`, `dist:nsis`, `dist:portable`: builds de Windows. `predist*` corre `npm test` y `postdist*` corre `publish-local`.
- `dist:release`: `scripts/release.js` (con `predist:release` = tests). `release:check`, `verify:signature` y `verify:release` inspeccionan sin publicar.
- `test:e2e`: `test/e2e-packaged.test.js` contra el paquete. `release:local` = `dist` + e2e.
- `serve-updates`: `scripts/serve-updates.js` levanta un feed local para probar `electron-updater`.

`electron-builder` escribe en `dist/`, con `asar: true` y `npmRebuild: false`. `build.files` es lista explicita (main.js, preload.js, src, renderer, iconos, LICENSE, SECURITY.md, PRIVACY.md, package.json): lo que no este ahi no viaja en el paquete.


## Timeline

- time: 2026-11-27T16:19:27
  kind: decision
  summary: "Created this page: Mapa de scripts npm y que hace cada uno"
  source: created via brain create-page
  affects: [app-scripts]

- time: 2026-11-27T16:19:28
  kind: decision
  summary: Recoge el mapa de scripts y la lista blanca del paquete
  source: brain update-truth
  affects: [app-scripts]
