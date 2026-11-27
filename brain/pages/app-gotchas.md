---
id: app-gotchas
title: "Gotchas de la app: carpeta bloqueada, smoke, asar y feed de updates"
category: reference
status: active
tags: [electron, gotchas, pack, updates]
created: "2026-11-27T16:19:28"
updated: "2026-11-27T16:19:28"
---

<!-- compiled_truth -->
- Si Ezuryseth esta abierto, `publish-local.js` no puede reemplazar `Downloads/ezuryseth`: reintenta el renombrado y, si sigue bloqueado, falla con "Close Ezuryseth if it is running" y deja la copia anterior intacta. No hay que borrar la carpeta a mano.
- `FPSBOOSTER_SKIP_LOCAL_SMOKE=1` salta el smoke test del paquete. Es una salida de emergencia, no una forma de tapar un smoke que falla.
- `--smoke-test` se salta el lock de instancia unica a proposito: durante el smoke pueden coexistir dos procesos.
- `src/device-guard.vbs` esta en `asarUnpack`: si se mueve de sitio o se renombra, deja de quedar fuera del asar y la app empaquetada no lo encuentra.
- El feed de actualizaciones exige HTTPS (HTTP solo en localhost, 127.0.0.1 o ::1), sin query ni hash, y debe apuntar a un directorio, nunca a `latest.yml`.
- La raiz del workspace no es repo git: alli solo se versionan `AGENTS.md` y `CLAUDE.md` por lista blanca, asi que el codigo de la app no tiene historial. Ver tambien [[brain-installer-gotcha]].


## Timeline

- time: 2026-11-27T16:19:28
  kind: decision
  summary: "Created this page: Gotchas de la app: carpeta bloqueada, smoke, asar y feed de updates"
  source: created via brain create-page
  affects: [app-gotchas]

- time: 2026-11-27T16:19:28
  kind: decision
  summary: Reune los fallos que no son obvios leyendo el codigo
  source: brain update-truth
  affects: [app-gotchas]
