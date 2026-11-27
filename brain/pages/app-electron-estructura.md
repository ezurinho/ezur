---
id: app-electron-estructura
title: "Estructura de Ezuryseth: proceso principal, preload y modulos de sistema"
category: project
status: active
tags: [electron, arquitectura, seguridad]
created: "2026-11-27T16:19:27"
updated: "2026-11-27T16:19:27"
---

<!-- compiled_truth -->
Ezuryseth es una app Electron de optimizacion de Windows. `main.js` (1441 lineas) es el proceso principal y registra todo el IPC; `preload.js` (81 lineas) expone `window.fps` por contextBridge; `renderer/` es HTML/CSS/JS estatico sin bundler; `src/` son unos 30 modulos CommonJS con la logica de sistema (optimizador, red, DNS, energia, GPU, servicios, rollback).

La ventana se crea con `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` y `spellcheck: false`: el renderer no tiene Node, solo los metodos de `window.fps`.

Todo el IPC de peticion pasa por un unico `handle()` que primero valida el remitente con `isTrustedIpcSender` (la URL debe ser `file:` apuntando exactamente a `renderer/index.html`, sin query ni hash, y desde el frame principal) y despues aplica el lock de operacion si el canal esta en `EXCLUSIVE_IPC_OPERATIONS`. Los controles de ventana (`window:minimize`, `window:toggle-maximize`, `window:close`) usan `ipcMain.on` y repiten la comprobacion.

Instancia unica con `requestSingleInstanceLock()`, salvo en `--smoke-test`; el segundo lanzamiento enfoca la ventana existente. El estado vive en `app.getPath('userData')` con `src/store.js` (JSON, historial maximo 12) y migra desde los nombres legacy `FPS Booster Pro` y `fps-booster-pro`.

Los tweaks que tocan Windows pasan por `runWithSnapshotGate`, que garantiza un punto de restauracion antes de aplicar; el rollback esta en `src/windows-rollback.js`.


## Timeline

- time: 2026-11-27T16:19:27
  kind: decision
  summary: "Created this page: Estructura de Ezuryseth: proceso principal, preload y modulos de sistema"
  source: created via brain create-page
  affects: [app-electron-estructura]

- time: 2026-11-27T16:19:27
  kind: decision
  summary: Documenta la estructura y el modelo de confianza de la app
  source: brain update-truth
  affects: [app-electron-estructura]
