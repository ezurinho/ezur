---
id: afk-automation
title: "AFK en paper: keepalive, watchdog y research finito"
category: decision
status: active
tags: [afk, automation, watchdog, paper]
created: "2026-11-28T01:10:55"
updated: "2026-11-28T01:11:26"
---

<!-- compiled_truth -->
- AFK significa **paper desatendido**. `live_enabled` sigue en `false`; «no stop» no autoriza LIVE, promoción ni saltarse una parada deliberada.
- La operación usa tres tareas: `ezur-paper` (tras iniciar sesión, 30 s), `ezur-watchdog` (60 s) y `ezur-watchdog-keepalive` (cada 5 min). La tercera relanza al vigilante si murió; su lock hace salir a las copias simultáneas.
- `scripts/tarea_programada.ps1` usa las cmdlets de Task Scheduler, no la opción `/TR` antigua: la ruta de este repo supera el límite de 261 caracteres. No volver a la opción antigua para estas tareas.
- El research AFK es finito: `server.research --loop` termina cuando no quedan specs; tres fallos seguidos paran el bucle. No se regeneran variantes ni se usa `--force` para mantenerlo ocupado, y no hay LLM dentro del bucle.
- Paradas duras: LIVE activo, `equity_mismatch`, ledger roto, duplicados/posición fantasma, feed stale >15 min, reinicios repetidos o disco lleno. El watchdog reinicia el proceso, no arregla al proveedor.
- Las tareas son del usuario actual y requieren sesión iniciada. Arrancar sin login exige un servicio de Windows con credenciales; no se simula desde la skill.
- Evidencia del 2026-11-28: las tres tareas quedaron registradas, `/api/ready` respondió `ready: true` y `data/watchdog.log` registró el arranque del vigilante.


## Timeline

- time: 2026-11-28T01:10:55
  kind: decision
  summary: "Created this page: AFK en paper: keepalive, watchdog y research finito"
  source: "Sesión 2026-11-28: full automation/AFK sin LIVE"
  affects: [afk-automation]

- time: 2026-11-28T01:11:26
  kind: decision
  summary: "Fija AFK en paper: tres tareas, keepalive del watchdog, research finito y paradas duras; sin LIVE"
  source: "Sesión 2026-11-28; /api/ready listo y tareas registradas"
  affects: [afk-automation]
