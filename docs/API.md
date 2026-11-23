# API

Base: `http://127.0.0.1:8765/api`. Sin autenticación: la terminal es local y de
un solo operador. Todos los cuerpos son JSON.

## Estado

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/health` | `{status, version}` |
| GET | `/status` | snapshot completo del contrato v1 |
| GET | `/validation` | veredicto de puertas + detalle por puerta |

## Motor

| Método | Ruta | Efecto |
|---|---|---|
| POST | `/bot/start` | arranca el motor y el replay del feed |
| POST | `/bot/pause` | deja de evaluar, mantiene posición y estado |
| POST | `/bot/stop` | detiene el motor |
| POST | `/emergency` | parada de emergencia persistente |
| DELETE | `/emergency` | desactiva la emergencia |

`POST /api/bot/{acción}` con una acción desconocida devuelve `404`.

## Posición y órdenes

| Método | Ruta | Efecto |
|---|---|---|
| GET | `/orders` | órdenes conocidas con su estado y brackets |
| POST | `/position/close` | cierra a mercado con el último precio conocido |
| POST | `/orders/cancel` | cancela las órdenes pendientes |

Cerrar posición durante una emergencia está permitido por diseño: la parada
bloquea entradas, no salidas.

## Configuración

| Método | Ruta | Efecto |
|---|---|---|
| GET | `/config` | configuración viva validada |
| PUT | `/config` | aplica un patch parcial; `422` si es inválido |
| POST | `/config/reset` | vuelve a los defaults |
| GET | `/strategy/schema` | lista de estrategias + esquema de parámetros del plugin |

`PUT /config` acepta `{"patch": {"risk": {"max_trades_per_day": 4}}}`. Cambiar
`strategy.id` reconstruye el plugin en caliente; unos parámetros inválidos para
ese plugin devuelven `422` y el motor sigue con la estrategia anterior. Un cambio
de instrumentos reconstruye el feed y reinicia el replay para que el símbolo
nuevo tenga datos; el histórico de velas en memoria se descarta.

## Historial

| Método | Ruta | Parámetros |
|---|---|---|
| GET | `/trades` | `limit`, `offset`, `mode`, `side`, `start`, `end` |
| GET | `/trades/export.csv` | los mismos filtros que `/trades` |
| GET | `/events` | `limit`, `level` |
| GET | `/stats` | — |
| GET | `/stats/reset/preview` | — |
| POST | `/stats/reset` | `{include_backtests: bool}` |

`/stats` devuelve `closed`, `by_hour`, `by_weekday`, `by_month`, `by_side`,
`by_day` y `equity`. Los desgloses usan la zona horaria de la sesión, y `closed`
incluye `r_median` y `r_distribution` con buckets fijos de R.

## Datos y backtesting

| Método | Ruta | Efecto |
|---|---|---|
| GET | `/datasets` | CSV disponibles en el directorio de datos |
| POST | `/data/validate` | valida alineación, huecos y símbolos |
| POST | `/backtest/run` | ejecuta un backtest, guarda resultado y registra experimento |
| GET | `/backtest/runs` | listado con cursor (`has_more`, `next_cursor`) |
| GET | `/experiments` | ledger de experimentos + resumen por veredicto |
| GET | `/funnel` | embudo de evaluación: etapas, tasa de supervivencia y desglose |

`POST /backtest/run` devuelve `run_id`, `metrics`, `trades`, `dataset_id`,
`verdict`, `validation` (informe completo de puertas) y `experiment_id`.

Por defecto (`"stress": true`) re-ejecuta el backtest dos veces más para medir
G8 (costes ×2) y G2 (determinismo). Con `"save": true` guarda el resultado.

## Gráfico

| Método | Ruta | Parámetros |
|---|---|---|
| GET | `/chart/history` | `tf` en `1m,5m,15m,30m`, `limit` |

## Tiempo real

`WS /api/ws`

- Al conectar envía un `{"type": "snapshot", ...}` inmediato.
- Después reenvía cada snapshot emitido por el motor.
- Una cola por cliente: un cliente lento no bloquea al motor ni a los demás.

## Errores

| Código | Cuándo |
|---|---|
| `404` | acción de motor o estrategia inexistente |
| `409` | arranque rechazado (emergencia activa, LIVE sin adaptador) |
| `422` | payload o configuración inválida |
