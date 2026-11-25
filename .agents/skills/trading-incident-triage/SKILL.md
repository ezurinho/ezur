---
name: trading-incident-triage
description: "Diagnostica incidentes de ezur sin destruir evidencia: motor parado, feed stale, cero operaciones, equity descuadrada, trades duplicados, ledger roto, replay atascado o base bloqueada. Úsala cuando el bot no opera, los datos envejecen, los números no cuadran o hay que decidir si parar y cómo contener."
version: 1.0.0
---

# Triaje de incidentes

## Cuándo usarla

El bot no entra, el estado es `error`, la calidad pasa a `degraded`/`stale`, la equity
no cuadra, aparecen operaciones repetidas, el ledger no verifica o el replay se queda
clavado. Para la rutina normal usa `trading-bot-ops`.

## Los primeros diez minutos

1. **No borres la base, no hagas reset, no reinicies a ciegas.** Primero se captura.
2. Guarda el estado:

```powershell
curl.exe -s http://127.0.0.1:8765/api/health | Tee-Object reports/incident-health.json
curl.exe -s http://127.0.0.1:8765/api/status | Tee-Object reports/incident-status.json
curl.exe -s "http://127.0.0.1:8765/api/events?limit=200" | Tee-Object reports/incident-events.json
python -m server.diagnostics --profile profiles/okx --strict
python -m server.experiments --verify
```

3. Copia la base antes de cualquier escritura:

```powershell
Copy-Item profiles/okx/terminal.db "backups/incident-$(Get-Date -Format yyyyMMdd-HHmm).db"
```

4. Clasifica: ¿el proceso vive? ¿el motor corre? ¿el feed emite? ¿el riesgo bloquea?
   ¿los datos persisten?

## Matriz de síntomas

| Síntoma | Primera comprobación | Causa frecuente |
|---|---|---|
| `engine.status` no es `running` | `/api/health` y `/api/status` | perfil con `auto_start: false`, parada manual, error de feed |
| `quality: stale` | `last_bar_age_s` y `engine.feed` | proveedor caído, red, CSV agotado, reloj |
| Cero operaciones con motor `running` | `data.risk.block_reason` | warmup, sesión cerrada, límite de riesgo, racha, promoción |
| `block_reason: equity_mismatch` | `server.diagnostics --strict` | libro y curva guardada divergen |
| Trades repetidos | `data.mode` y `feed.loop_sessions` | replay en bucle del demo, no duplicados reales |
| Ledger no verifica | `server.experiments --verify` | edición manual o corrupción del JSONL |
| Replay clavado | `/api/events`, consola | feed agotado sin `loop_sessions`, error de parseo |
| `database is locked` | procesos y puerto 8765 | dos instancias sobre el mismo perfil |

## 1. El motor no corre

```powershell
curl.exe -s http://127.0.0.1:8765/api/health
Get-Content profiles/okx/config.json | Select-String 'auto_start|live_enabled|provider'
```

- `auto_start: false` → `POST /api/bot/start`; no es un fallo.
- `status: error` → mira el último evento `error` y el log del proceso.
- El proceso no responde → comprueba que no hay otra instancia:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object OwningProcess
Get-Process -Id <pid> | Select-Object ProcessName,Path
```

Dos procesos sobre el mismo `terminal.db` explican locks y estados raros. Mata el
duplicado, no el que tiene la ventana correcta.

## 2. Feed stale o degraded

El watchdog corre cada 30 s y **solo envejece la calidad y cancela órdenes pendientes**:
no reinicia el feed. A los 180 s marca `degraded`; a los 900 s, `stale` y cancela
pendientes. Si el proveedor no vuelve, el motor no se cura solo.

```powershell
curl.exe -s http://127.0.0.1:8765/api/status | Select-String 'quality|last_bar_ts|staleness_ms'
curl.exe -s http://127.0.0.1:8765/api/events?limit=50
```

Revisa `data.data.quality`, `data.data.last_bar_ts`, `data.data.bars_available` y el
último `error` del feed. Para OKX, comprueba conectividad y cuota; para CSV, que el
archivo tenga velas nuevas; para simulados, que el replay no haya terminado.

Si el feed está caído y hay posición abierta, decide explícitamente: esperar, pausar
o cerrar. El watchdog no cierra posiciones.

## 3. No entra aunque haya señal

```powershell
curl.exe -s http://127.0.0.1:8765/api/status
```

Lee `data.risk.blocked`, `block_reason`, `block_count` y `data.strategy.state`.

| `block_reason` | Significado | Acción |
|---|---|---|
| `stale_data` | datos viejos | arreglar feed |
| `stale_order` | orden pendiente caducada (TTL 120 s) | normal; esperar señal nueva |
| `stale_signal` | la señal llegó tarde | normal; no forzar |
| `outside_window` | fuera de la ventana de sesión | esperar apertura |
| `emergency_active` | emergencia activa | `DELETE /api/emergency` si procede |
| `equity_mismatch` | descuadre | ver sección 4 |

Si no hay bloqueo, comprueba warmup (`warmup_requirements`), sesión (`is_open`),
límites (`max_trades_per_day`, `max_concurrent_positions`, pérdida diaria), racha
(`no_trade_after_consecutive_losses`) y que la estrategia no sea `null`.

## 4. Equity descuadrada

```powershell
python -m server.diagnostics --profile profiles/okx --strict
python -m server.equity --profile profiles/okx
```

`diagnostics` compara la curva guardada con el libro y sale con 1 si algo no cuadra.
`equity` sin flags solo informa. Si el libro es la verdad y la curva está mal:

```powershell
python -m server.equity --profile profiles/okx --apply
```

`--apply` hace copia previa. Con el motor vivo, `--force` se deshace en la próxima
vela; para arreglarlo de verdad, detén el motor primero. Tras una parada dura por
drawdown, `--reset-peak` reanuda con copia y evento; no lo uses para ocultar pérdidas.

## 5. Trades duplicados

La tabla tiene índice único parcial por señal (incluye `side`). Un duplicado real
debería ser imposible al insertar; si aparece, investiga antes de borrar.

- `profiles/demo` con `loop_sessions: true` repite la misma sesión sintética: no son
  duplicados, son pasadas distintas. Compruébalo por `mode` y timestamps.
- Un `Signal.key` inestable en el plugin puede generar dos entradas distintas.
- Un backfill que vuelve a ver la misma vela no debe insertar dos veces: el índice lo
  impide y el evento queda en consola.

```powershell
curl.exe -s "http://127.0.0.1:8765/api/trades?limit=20"
```

## 6. Ledger roto

```powershell
python -m server.experiments --verify
python -m server.experiments --find <experiment_id> --json
```

El JSONL es append-only: no lo edites para «arreglar» un hash. Si la cadena se rompe,
conserva el archivo, restaura la última copia buena y deja constancia. Sin ledger
verificado no hay promoción ni claim de validación.

## 7. Replay atascado

Si el feed termina y `loop_sessions` es `false`, el motor pasa a `stopped`: es correcto,
no un cuelgue. Si el replay se reinicia, el motor ignora ticks anteriores a la última
vela procesada para no repetir operaciones. Un CSV con huecos o fechas desordenadas
puede dejar el replay esperando: valida el dataset con `server.integrity` o
`POST /api/data/validate`.

## 8. UI desincronizada

Si la API está bien pero la pantalla no: recarga, mira la consola del navegador y el
WebSocket `/api/ws`. El snapshot es la fuente de verdad; React no calcula P&L ni
señales. Un `kind` desconocido se descarta y se registra: no rompe el render.

## Contención y cierre

| Situación | Contención |
|---|---|
| Feed caído con posición | pausar o cerrar explícitamente; no dejarlo «a ver» |
| Equity descuadrada | detener, diagnosticar, `--apply` con copia |
| Duplicados o posición fantasma | detener, copiar base, revisar libros |
| Ledger roto | detener promociones, preservar archivo, restaurar copia |

Al terminar, deja en `events` o en el reporte: hora, síntoma, comandos ejecutados,
causa, arreglo y qué se evitó. Si el incidente afectó a una operación, revisa si el
dry-run sigue siendo válido antes de promocionar nada.