# Operación

Procedimientos para quien opera la terminal. Todo es local: no hay servicios
externos, ni colas, ni credenciales.

## Arrancar

```powershell
python run.py                                        # perfil por defecto
$env:TERMINAL_PROFILE_DIR="profiles/demo"; python run.py   # perfil de ejemplo
```

Queda en `http://127.0.0.1:8765`. El motor arranca **detenido**: nada se evalúa
hasta pulsar Iniciar o llamar a `POST /api/bot/start`.

## Los cuatro controles

| Control | Efecto | Estado persistido |
|---|---|---|
| Iniciar | el motor vuelve a evaluar y a consumir el feed | `running` |
| Pausar | deja de evaluar; la posición y la orden pendiente siguen vivas | `paused` |
| Detener | motor detenido; misma idea que pausa, distinto nombre de estado | `stopped` |
| Emergencia | cancela órdenes pendientes y bloquea entradas nuevas | `paused` + `emergency` |

La emergencia **no** cierra una posición abierta: eso lo decide el operador con
«Cerrar posición». Bloquear la salida junto con la entrada es cómo se pierde
dinero por no poder salir.

## Rutina diaria

1. `GET /api/health` y mirar la barra superior: sesión, calidad del dato, modo.
2. Si la calidad dice `degraded` o `stale`, revisar el feed antes de operar. La
   frescura se mide entre ticks, no contra el reloj: un replay de ayer no es
   «viejo», un feed parado sí.
3. Iniciar y leer el panel de estrategia: fases, métricas y motivo de bloqueo.
4. Al cerrar: Detener. Las posiciones abiertas se cierran solas a la hora
   configurada si `close_at_session_end` está activo.

## Diagnóstico

```powershell
python -m server.diagnostics --db profiles/demo/terminal.db   # solo lectura
python -m server.funnel                                        # embudo de evaluación
python -m server.experiments --help 2>$null; curl http://127.0.0.1:8765/api/stats
```

| Síntoma | Dónde mirar |
|---|---|
| No entra en ninguna operación | panel de riesgo: `block_reason` y `block_count` |
| El gráfico está vacío tras cambiar instrumentos | el feed se reconstruye y el replay reinicia; esperar unos segundos |
| `quality: stale` | el feed dejó de emitir; revisar proveedor o CSV |
| Consola llena de un solo mensaje | los rechazos repetidos se agrupan cada 120 s a propósito |
| El veredicto no cambia | es correcto: la estrategia no tiene edge |

## Reset operativo

```powershell
python -m server.reset --dry-run     # qué se borraría
python -m server.reset --yes         # archiva y limpia
```

Archiva la base de datos en `backups/` antes de tocar nada y deja `trades`,
`events`, `equity` y `kv` vacíos. Los backtests se conservan salvo que se pida
lo contrario (`POST /api/stats/reset` con `include_backtests: true`).

## Cambiar de estrategia en caliente

```powershell
curl -X PUT http://127.0.0.1:8765/api/config -H "Content-Type: application/json" `
  -d '{"patch": {"strategy": {"id": "donchian", "params": {"channel": 20}}}}'
```

El plugin se reconstruye, el feed se rehace y el replay reinicia desde el
principio de la sesión. Unos parámetros inválidos devuelven `422` y el motor
sigue con la estrategia anterior: nunca se queda a medias.

## Copias de seguridad

| Qué | Dónde | Frecuencia |
|---|---|---|
| Base de datos | `profiles/<perfil>/terminal.db` | diaria |
| Configuración | `profiles/<perfil>/config.json` | al cambiarla |
| Ledger de experimentos | `reports/experiments.jsonl` | nunca se borra |
| Reportes de simulación | `reports/backtest/` | por corrida |

El ledger es append-only: es la única prueba de qué se probó y con qué veredicto.
Perderlo convierte el historial de investigación en opiniones.

## Lo que no hace

- No envía órdenes a un broker: no hay adaptador y LIVE está bloqueado por diseño.
- No promete rentabilidad. La puerta G5 rechaza todo lo que no tenga expectativa
  positiva, y hoy rechaza las tres estrategias incluidas.
- No autoajusta parámetros: cualquier cambio es explícito y queda registrado.
