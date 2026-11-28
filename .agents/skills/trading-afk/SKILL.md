---
name: trading-afk
description: "Deja ezur en paper desatendido sin convertirlo en un bucle ciego: preflight, tareas de Windows, watchdog con keepalive, research acotado, vigilancia, paradas duras y handoff. Úsala cuando se pida full automation, full AFK, no stop, dejar el bot solo o una sesión larga sin intervención."
version: 1.0.0
---

# Operación AFK

## Qué significa aquí

AFK es **paper desatendido**: el motor sigue con datos y reglas reales mientras nadie
mira la pantalla. «No stop» significa no interrumpirlo mientras está sano; **no**
significa mantener vivo un proceso roto, saltarse una parada deliberada ni encender
LIVE.

LIVE sigue prohibido: `live_enabled` se queda en `false`. Una sesión AFK no promociona
una estrategia, no cambia umbrales y no convierte un backtest en una orden.

## Preflight

Ejecuta esto antes de dejar la máquina sola. Si algo falla, no arranques el modo AFK.

```powershell
# 1. El perfil que va a correr no está en live y no bloquea el arranque por sorpresa.
$cfg = Get-Content profiles/okx/config.json | ConvertFrom-Json
$cfg.live_enabled          # debe ser false o no existir (el default es false)
$cfg.auto_start            # true: el paper se reanuda solo tras un reinicio del proceso
$cfg.promotion             # required/mode/evidence: no lo fuerces

# 2. El proceso y el motor están sanos.
curl.exe -s http://127.0.0.1:8765/health
curl.exe -s http://127.0.0.1:8765/api/ready
curl.exe -s http://127.0.0.1:8765/api/status

# 3. La evidencia no está rota.
python -m server.diagnostics --profile profiles/okx --strict
python -m server.experiments --verify

# 4. Las tres tareas apuntan a esta copia del repo.
schtasks.exe /Query /TN ezur-paper /FO LIST /V
schtasks.exe /Query /TN ezur-watchdog /FO LIST /V
schtasks.exe /Query /TN ezur-watchdog-keepalive /FO LIST /V
```

Si faltan las tareas, se recrean desde el repo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1
```

El script verifica la acción registrada de cada tarea. Si una apunta a otra carpeta,
falla en vez de dar por bueno un arranque que no existe.

Antes de irte, comprueba también:

- `data/watchdog.log` existe y la última línea no es un error repetido.
- Hay espacio libre suficiente para `profiles/okx/terminal.db` y sus backups.
- Si hay webhook de alertas, una alerta de prueba llega de verdad; sin él, nadie se
  entera de una parada de madrugada.
- No hay otro proceso escuchando en `8765` ni otro watchdog con el mismo lock.

## Arranque

Las tareas `ezur-paper` y `ezur-watchdog` se disparan al iniciar sesión (30 y 60 s).
`ezur-watchdog-keepalive` vuelve a lanzar el vigilante cada 5 minutos. Si el vigilante
murió, la copia nueva arranca; si sigue vivo, el lock de instancia única la hace salir
sin tocar el motor.

Las tareas `ezur-paper` y `ezur-watchdog` no se ejecutan hasta el próximo inicio de
sesión; el keepalive empieza un minuto después de registrarse y luego repite cada 5
minutos. Para arrancar ya, usa el camino manual y deja que las tareas cubran el
siguiente reinicio:

```powershell
Start-Process -FilePath ".\start_paper.bat" -WindowStyle Hidden
Start-Process -FilePath ".venv\Scripts\pythonw.exe" -ArgumentList "scripts\watchdog.py" -WindowStyle Hidden
```

No lances un segundo motor ni un segundo watchdog «por si acaso»: el lock por cuenta y
el lock del watchdog existen para que la copia extra salga sin duplicar operaciones.

### Research desatendido

El bot y el motor de research son procesos separados. Si hay una cola pendiente y
quieres medirla mientras el paper corre:

```powershell
New-Item -ItemType Directory -Force data\research | Out-Null
$p = Start-Process -FilePath ".venv\Scripts\python.exe" `
  -ArgumentList @("-m", "server.research", "--loop", "--cooldown", "30") `
  -WorkingDirectory (Get-Location) `
  -RedirectStandardOutput "data\research\afk.out.log" `
  -RedirectStandardError "data\research\afk.err.log" `
  -WindowStyle Hidden -PassThru
$p.Id | Set-Content data\research\afk.pid
```

El bucle es **finito**: cuando no quedan specs pendientes, termina. No lo reinicies
generando variantes sin fin para mantenerlo ocupado; repetir búsquedas sobre el mismo
dato es sobreajuste, no productividad. `--seeds` y `--generate` son actos explícitos,
no pasos automáticos de cada arranque. Tres fallos seguidos paran el bucle: investiga
antes de relanzarlo.

## Vigilancia

Cada 5 minutos, mientras estés despierto o desde otra máquina:

```powershell
curl.exe -s http://127.0.0.1:8765/api/ready
curl.exe -s http://127.0.0.1:8765/api/health
schtasks.exe /Query /TN ezur-watchdog-keepalive /FO LIST
Get-Content data\watchdog.log -Tail 30
```

Cada 30 minutos, mira lo que un 200 no cuenta:

| Campo | Sano | Problemático |
|---|---|---|
| `/api/ready` | `ready: true` | `feed_stale`, `heartbeat_stale`, `engine_*` |
| `engine.status` | `running` | `stopped`, `paused`, `error` |
| `data.data.quality` | `ok` | `degraded` (>180 s), `stale` (>900 s) |
| `data.risk.block_reason` | `null` o una pausa explicada | `equity_mismatch`, `stale_data`, `loss_streak` |
| tareas | las tres existen y su acción apunta al repo | tarea desaparecida o ruta vieja |
| `data/research/runs.jsonl` | crece si hay cola | bucle parado con cola pendiente |

Cada día, además:

```powershell
python -m server.diagnostics --profile profiles/okx --strict
python -m server.experiments --verify
python -m server.research --report
Get-ChildItem profiles\okx\backups | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

## Paradas duras

Detén el motor (`POST /api/bot/stop` o el control de la interfaz) y pasa a
`trading-incident-triage` si aparece cualquiera de estas:

- `live_enabled` pasó a `true` o alguien intentó habilitar LIVE.
- `equity_mismatch` persiste tras `server.equity`.
- `server.experiments --verify` falla, hay un trade duplicado o una posición fantasma.
- El feed lleva más de 15 minutos `stale`; el watchdog del proceso no arregla al
  proveedor.
- El watchdog se reinicia tres veces en 15 minutos o el keepalive encuentra un fallo
  que no se explica. No desactives la tarea a ciegas: primero captura el estado.
- El disco se está quedando sin espacio o la base no se puede copiar.
- El bucle de research acumula tres fallos seguidos.

Para una parada deliberada, para el motor y **no** borres las tareas: el watchdog de
readiness no reinicia un motor `stopped`/`paused` a propósito. Si hace falta quitar el
keepalive durante un mantenimiento, deshabilita solo esa tarea y vuelve a habilitarla
al terminar.

## Qué no hace

- No enciende LIVE ni firma promociones.
- No reinicia el feed ni cambia de estrategia por su cuenta.
- No borra la base, el ledger ni los backups.
- No garantiza arranque sin sesión iniciada: las tareas son del usuario actual. Un
  servicio de Windows con credenciales es otra decisión y no se simula desde aquí.
- No convierte «no stop» en un bucle infinito de generación de estrategias.

## Handoff

Al terminar una sesión AFK, deja un reporte breve con: hora, perfil, estado de las tres
tareas, PIDs, `/api/ready`, última vela, `block_reason`, número de trades, equity,
verificación del ledger, últimas líneas de `data/watchdog.log` y de
`data/research/afk.err.log`, y cualquier incidente. Sin esas cifras no hay sesión AFK
verificada, solo una máquina encendida.

## Skills relacionadas

- `trading-bot-ops`: arranque, controles y watchdog en detalle.
- `trading-incident-triage`: qué hacer cuando la parada dura ya ocurrió.
- `trading-ai-strategy-engine`: qué mide el bucle de research y qué no se puede afirmar.
- `trading-validation-pipeline`: promoción y holdout; nunca se automatizan aquí.
