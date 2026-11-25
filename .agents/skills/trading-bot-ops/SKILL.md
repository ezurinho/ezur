---
name: trading-bot-ops
description: "Opera la terminal de trading ezur: arranque por perfil, estados del motor, liveness, salud del feed, controles, copias de seguridad, cambio de estrategia y reconciliación de equity. Úsala cuando haya que arrancar o parar el bot, revisar por qué no opera, cambiar de perfil, hacer una copia o recuperar una cuenta descuadrada."
version: 1.1.0
---

# Operación de la terminal

## Cuándo usarla

Arrancar, parar o pausar el bot; comprobar que el feed está vivo; cambiar de perfil o
de estrategia; hacer copia antes de tocar algo; reconstruir la equity; reiniciar el
estado operativo. Para fallos concretos (no entra, datos viejos, trades duplicados,
ledger roto) usa `trading-incident-triage`.

## Reglas duras

1. **Paper solamente.** `live_enabled` se queda en `false`; LIVE exige adaptador,
   flag y confirmación explícita. No lo actives para «probar».
2. **No edites SQLite con el motor vivo.** Usa la API o los comandos de este skill.
3. **No relajes puertas ni tests** para que una operación pase.
4. **Cada cifra sale de un comando ejecutado**, no de una estimación.
5. Antes de un reset o un `--apply`, copia: el comando archiva, pero la copia
   externa es tuya.

## Arranque y perfiles

| Perfil | Comando (PowerShell) | Datos |
|---|---|---|
| OKX paper | `$env:EZUR_PROFILE_DIR="profiles/okx"; python run.py` | Velas 1m reales de OKX |
| Demo | `$env:EZUR_PROFILE_DIR="profiles/demo"; python run.py` | Sintéticos, replay en bucle |
| Agresivo | `$env:EZUR_PROFILE_DIR="profiles/agresivo"; python run.py` | Sintéticos, más riesgo |

`start_paper.bat` hace lo mismo que la primera fila, con el servidor en segundo plano
(`pythonw`, sin ventana): sus decisiones quedan en `data/run/start_paper.log` y la
salida del motor en `data/run/engine.log`.

Sin `EZUR_PROFILE_DIR` se usan
`data/config.json` y `data/terminal.db`. El panel queda en `http://127.0.0.1:8765`;
`EZUR_HOST`, `EZUR_PORT` y `EZUR_OPEN=1` cambian host, puerto y apertura del navegador.

Las tareas `ezur-paper` (motor) y `ezur-watchdog` (vigilante) se recrean desde esta
copia con `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1`;
comprueba que la acción registrada de cada una apunta al fichero de este repo y falla
si no. Se quitan las dos añadiendo `-Borrar` al final.

Con `auto_start: true` (por defecto) el motor ya está `running` al abrir. Con `false`
queda `idle`/`stopped` hasta `POST /api/bot/start`. Con `promotion.required=true` y
`mode=block`, el arranque manual también se bloquea si la evidencia no pasa, incluido
el `config_hash`; no fuerces el start, valida o deja el paper parado.

## Salud en 30 segundos

```powershell
curl.exe -s http://127.0.0.1:8765/health
curl.exe -s http://127.0.0.1:8765/api/health
curl.exe -s http://127.0.0.1:8765/api/status
```

`/health` es liveness del proceso: responde `{"status":"ok"}` si el servidor está
vivo, sin depender del motor. Es el que usa `scripts/watchdog.py`.
`/api/health` devuelve `status`, `version` y `engine` con `status`, `mode`, `feed`,
`last_bar_age_s` y `session`. Un 200 no basta: si `engine.status` no es `running` o
`last_bar_age_s` crece sin parar, el proceso vive pero el bot no.

`/api/status` devuelve el snapshot v1 completo. Mira, en este orden:

| Campo | Sano | Problemático |
|---|---|---|
| `data.status` | `running` | `stopped`, `paused`, `error` |
| `data.data.quality` | `ok` | `degraded` (>180 s), `stale` (>900 s) |
| `data.data.provider` | el esperado (`okx`/`simulated`) | otro o vacío |
| `data.risk.block_reason` | `null` | `stale_data`, `stale_order`, `equity_mismatch`, `loss_streak` |
| `data.strategy.state` | el del plugin (`scanning`, `disabled`…) | `error` o vacío inesperado |
| `data.position` / `data.orders` | coherentes con Operaciones | posición fantasma u orden vieja |

## Watchdog del proceso

```powershell
python scripts/watchdog.py
```

Comprueba `/health` cada 5 s; a los 3 fallos mata solo el PID que escucha en 8765 y
relanza `run.py` con el perfil `okx`. Nunca llama a `/api/bot/start`: el paper se
reanuda solo si el perfil trae `auto_start: true`, que es lo que tiene `okx`.
La tarea `ezur-watchdog` lo arranca al iniciar sesión, 60 s después del motor; el
comando manual sigue sirviendo para una sesión suelta.
Log: `data/watchdog.log`;
salida del servidor: `data/paper-15m-server.log`. No lo confundas con el watchdog de
frescura del motor, que solo marca `degraded`/`stale` y cancela pendientes.

El motor toma un lock por cuenta (`profiles/okx/terminal.lock`): un segundo proceso
sobre la misma base se niega a arrancar con el PID del dueño. El lock lo libera el
sistema al morir el proceso, así que el watchdog puede relanzar sin limpiar ficheros.

## Los cuatro controles

```powershell
curl.exe -s -X POST http://127.0.0.1:8765/api/bot/start   -H "Content-Type: application/json" -d '{}'
curl.exe -s -X POST http://127.0.0.1:8765/api/bot/pause   -H "Content-Type: application/json" -d '{}'
curl.exe -s -X POST http://127.0.0.1:8765/api/bot/stop    -H "Content-Type: application/json" -d '{}'
curl.exe -s -X POST http://127.0.0.1:8765/api/emergency
curl.exe -s -X DELETE http://127.0.0.1:8765/api/emergency
```

| Acción | Qué hace | Qué NO hace |
|---|---|---|
| Iniciar | reanuda feed y evaluación | no resucita una configuración inválida |
| Pausar | deja de evaluar; posición y orden siguen | no cancela la orden pendiente |
| Detener | motor parado | no cierra la posición |
| Emergencia | cancela órdenes y bloquea entradas | **no** cierra la posición abierta |

Para cerrar una posición: `POST /api/position/close`. Para cancelar órdenes:
`POST /api/orders/cancel`.

## Cambiar estrategia en caliente

```powershell
curl.exe -s -X PUT http://127.0.0.1:8765/api/config -H "Content-Type: application/json" `
  -d '{"patch": {"strategy": {"id": "donchian", "params": {"channel": 20}}}}'
```

El plugin se reconstruye, el feed se rehace y el replay reinicia. Parámetros inválidos
devuelven `422` y el motor sigue con la estrategia anterior. El esquema vivo está en
`GET /api/strategy/schema`. Cambiar la estrategia o sus parámetros invalida la
evidencia por `config_hash`: no es una promoción; vuelve a validar antes de operar.

## Copias y recuperación

| Qué | Dónde | Cuándo |
|---|---|---|
| Cuenta | `profiles/<perfil>/terminal.db` | diaria y antes de tocar nada |
| Config | `profiles/<perfil>/config.json` | al cambiarla |
| Ledger | `reports/experiments.jsonl` | nunca se borra |
| Reportes | `reports/backtest/` | por corrida |

```powershell
Copy-Item profiles/okx/terminal.db "backups/terminal-$(Get-Date -Format yyyyMMdd-HHmm).db"
python -m server.diagnostics --profile profiles/okx --strict
python -m server.equity --profile profiles/okx
```

`diagnostics --strict` sale con 1 si hay filas imposibles, desviación de equity o
parada dura. `equity` compara la curva guardada con el libro; `--apply` la reescribe
con copia previa y `--reset-peak` reanuda tras una parada dura. No uses `--force` con
el motor vivo salvo que sepas que la próxima vela lo deshace.

## Reset operativo

```powershell
python -m server.reset --dry-run   # enseña qué se archiva y qué se borra
python -m server.reset --yes       # archiva en backups/ y limpia trades/events/equity/kv
```

Conserva los backtests salvo que se pida `include_backtests`. El ledger no se toca.

## Cuándo parar y escalar

Detén el motor (`POST /api/bot/stop`) y no lo reinicies a ciegas si:

- `equity_mismatch` persiste tras `server.equity` (hay un descuadre que no se explica).
- El ledger no verifica (`python -m server.experiments --verify`).
- Hay trades duplicados o una posición que el broker/los datos no justifican.
- El feed lleva `stale` más de 15 minutos y el proveedor no responde.

Después: `trading-incident-triage`. No borres la base para «arreglarlo».

## Referencias

- `docs/OPERACION.md` — runbook completo, alertas, racha de pérdidas.
- `docs/API.md` — contratos de los endpoints.
- `README.md` — arranque, escritorio e instalador.