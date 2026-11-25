# Decisiones pendientes (Fase 0)

Puerta **P0**: sin estos siete ADR cerrados no se empieza la Fase 4. Un holdout
evaluado con criterios que luego cambian no es un holdout.

Cada ADR necesita: decisión, alternativa descartada, motivo y fecha. Mientras
diga `PENDIENTE`, el sistema puede operar en simulación pero no puede producir
evidencia válida.

## ADR 0.1 — Mercado e instrumentos

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Instrumento primario | — |
| Instrumentos de contexto | — |
| Alternativa descartada | — |
| Motivo | — |
| Criterio mínimo | ≥ 12 meses de historia con volumen real |

## ADR 0.2 — Fuente de datos

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Proveedor | — |
| Granularidad | tick / 1m |
| Coste | — |
| Contratos y vencimientos documentados | — |
| Alternativa descartada | — |

## ADR 0.3 — Ejecución

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Broker o ejecución simulada | — |
| Adaptador implementado | no |
| Consecuencia | sin adaptador, LIVE queda bloqueado por diseño |

## ADR 0.4 — Capital y tolerancia

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Capital de referencia | — |
| Drawdown máximo aceptado | — |
| Pérdida diaria máxima | — |

Números, no adjetivos.

## ADR 0.5 — Temporalidades

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Temporalidad de decisión | — |
| Temporalidad de contexto | — |
| Velas de calentamiento requeridas | — |

## ADR 0.6 — Costes

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Comisión por unidad y lado | — |
| Slippage esperado | — |
| Funding aplicable | — |
| Fuente del dato | — |

Los valores deben venir del broker, no de una estimación propia.

## ADR 0.7 — Calendario

| Campo | Valor |
|---|---|
| Estado | PENDIENTE |
| Zona horaria de sesión | — |
| Horario operativo | — |
| Feriados aplicados | — |
| Cierres anticipados | — |

## ADR 0.8 — Alertas fuera de banda

**Decisión.** Un webhook opcional, apagado por defecto, recibe los eventos de
nivel `warn` y `error` como JSON. La entrega va en un hilo aparte con cola
acotada, deduplicación de 60 s y reintentos contados.

**Por qué.** Una parada de emergencia que solo se ve en la pantalla que no estás
mirando no es una parada. Freqtrade y Hummingbot lo resuelven con Telegram; un
webhook genérico sirve para Telegram, Slack, Discord o un endpoint propio sin
depender de ninguna API concreta.

**Por qué no bloquea.** Un `POST` dentro del bucle de ticks convierte un webhook
lento en velas perdidas. La cola acotada prefiere descartar y contar antes que
acumular memoria sin límite.

**Por qué el contador y no el log.** Un webhook caído una hora genera cientos de
fallos idénticos. Se cuentan (`failed`, `dropped`) y se muestra un evento, no uno
por intento.

**Alternativa descartada.** Escribir a un archivo y dejar que un tercero lo lea:
menos código, pero nadie mira ese archivo a las 3 de la mañana.

## ADR 0.9 — Guardián de drawdown y ledger encadenado

**Decisión.** Dos controles nuevos, ambos apagados por defecto:
`risk.max_drawdown_pct` (drawdown sobre el pico de capital realizado) y una
cadena SHA-256 en el ledger de experimentos (`prev_hash` / `chain_hash`).

**Por qué el drawdown.** Teníamos pérdida diaria máxima, racha de pérdidas y
cooldown, pero ninguna medida del daño acumulado desde el máximo. Freqtrade
documenta el mismo problema y avisa de que su modo `ratios` **no** es el
drawdown de la curva de capital; aquí se mide sobre equity, no sobre suma de R.

**Por qué la cadena.** «Append-only» era una promesa del código, no algo que un
lector pudiera comprobar. Con la cadena, cambiar un veredicto en el medio se
detecta y se señala el índice. Es la idea de `ai-hedge-fund`, aplicada a un
JSONL en vez de a un NAV.

**Coste.** Dos columnas por línea y un SHA-256 por registro: despreciable.

## ADR 0.10 — Dos modos de interfaz y arranque automático

**Decisión.** `ui` deja de ser un único layout: la terminal tiene **Básico** y
**Avanzado**, y el motor arranca solo (`auto_start: true`).

**Por qué dos modos.** El snapshot v1 es deliberadamente rico: fases, métricas,
zonas, marcadores, puertas, embudo. Eso es lo que un operador quiere cuando
audita una estrategia y exactamente lo que hace inservible la pantalla para
alguien que solo quiere saber si el bot está ganando o perdiendo. Enseñar todo a
todos no es transparencia, es ruido: la información que no se puede interpretar
se ignora igual que la que no existe.

**Por qué el modo no va al servidor.** Es una preferencia de lectura, como el
zoom. Va a `localStorage`; el snapshot no gana un campo y el contrato v1 no se
mueve. Cambiar de modo no reinicia nada ni toca el motor.

**Por qué arranque automático.** Un bot que necesita que un humano pulse
«empezar» a las 3 de la mañana no opera a las 3 de la mañana. `auto_start` es
`true` por defecto y el perfil lo repite para que se vea; con `false` el motor
queda `idle` hasta `POST /api/bot/start`, que es lo que quieren los tests y
quien prefiere revisar antes de exponer capital.

**Contrapartida aceptada.** El modo básico esconde cosas que sí importan en una
auditoría (R, drawdown, puertas). Por eso cada vista básica enlaza al avanzado y
la configuración completa sigue a un clic; esconder sin salida habría sido otra
decisión, peor.

## ADR 0.11 — Laboratorio, trazabilidad y escrituras serializadas

**Decisión.** El backtest deja de ser solo CLI: hay una vista **Laboratorio**
(avanzado) que corre una estrategia o compara varias sobre el mismo dataset, y
cada ejecución obtiene identidad propia (`run_id`), hash de configuración y,
cuando compara, `run_group`.

**Por qué.** Jesse documenta *Benchmark* como «run batch backtests, compare
across timeframes, symbols, and strategies»; vectorbt existe entero para eso.
ezur tenía el motor y las puertas, pero comparar tres estrategias obligaba a
abrir una terminal y recordar rutas. La función que estas herramientas
consideran central no debería ser un script.

**Por qué `run_id` único.** Antes era el prefijo del hash del dataset: dos
estrategias sobre el mismo CSV compartían identificador y «la corrida X» no
significaba nada. `dataset_id` sigue siendo el contenido; `run_id` es el acto.

**Orden del ranking.** Las estrategias sin operaciones van al final. `0.00 R`
con cero trades es ausencia de datos, no el mejor resultado; encabezar la tabla
con eso sería un error de lectura garantizado.

**Escrituras serializadas.** El motor escribe desde el bucle de eventos y la API
desde el hilo de la petición. Sin bloqueo, dos `with conn:` solapados lanzan
«cannot commit - no transaction is active». Se añadió un `RLock` re-entrante
alrededor de la conexión (`_LockedConnection`), con test de 4 hilos × 25
escrituras. Las lecturas no se bloquean.

**Publicación inmediata.** `POST /api/bot/{action}` publica el snapshot antes de
responder (y captura el estado antes de ceder el turno): un botón que contesta
«running» mientras la pantalla dice «stopped» se lee como terminal roto.

**Coste.** Una vista nueva, dos endpoints y un lock por escritura. Ninguna
puerta cambió de criterio.

## Registro

| Fecha | ADR | Decisión | Autor |
|---|---|---|---|
| — | — | — | — |

## Valores por defecto del código

Mientras un ADR siga `PENDIENTE`, el sistema usa estos valores. Cerrar un ADR es
confirmarlos o sustituirlos: cada fila indica la clave exacta de configuración.
Ninguno de estos valores es una decisión de producto, son supuestos heredados.

| ADR | Campo | Valor actual | Clave |
|---|---|---|---|
| 0.1 | Instrumento primario | `PRIMARY` (perfil demo) | `instruments.items[].symbol` |
| 0.1 | Instrumentos de contexto | `CTX_A` (perfil demo) | `instruments.items[].role` |
| 0.2 | Proveedor | `simulated`; `csv` y `live` sin adaptador | `data.provider` |
| 0.2 | Granularidad | velas de 1 minuto | `data.timeframe` |
| 0.3 | Ejecución | simulada, sin adaptador de broker | `execution.model` |
| 0.4 | Capital de referencia | 25.000 USD | `risk.initial_capital` |
| 0.4 | Drawdown máximo aceptado | 3 % diario (puerta G6 pide ≤ 2 % en backtest) | `risk.max_daily_loss_pct` |
| 0.4 | Pérdida diaria máxima | 3 % | `risk.max_daily_loss_pct` |
| 0.5 | Temporalidad de decisión | 1 m | `data.timeframe` |
| 0.5 | Temporalidad de contexto | 1 m (misma serie) | — |
| 0.5 | Velas de calentamiento | las que declare el plugin (`Warmup`) | `server/strategy/base.py` |
| 0.6 | Comisión por unidad y lado | 0,62 USD | `execution.commission_per_unit_side` |
| 0.6 | Slippage esperado | 1 tick, tope de 3 ticks | `execution.slippage_ticks`, `max_slippage_ticks` |
| 0.6 | Funding | no aplica al instrumento demo | — |
| 0.7 | Zona horaria de sesión | `America/New_York` | `instruments.session.timezone` |
| 0.7 | Horario operativo | 09:30–16:00, cierre de posiciones 15:55 | `session.open/close`, `risk.session_close_time` |
| 0.7 | Feriados y cierres anticipados | vacíos en el código; se inyectan como datos | `Calendar(holidays=..., early_closes=...)` |

Los valores de coste del ADR 0.6 son un supuesto de trabajo, no un dato del
broker: el propio ADR exige que vengan del broker. Hasta entonces cuentan como
`not_measured` en la puerta G8.

## ADR 0.12 · La interfaz dice la edad del dato y la salida del bloqueo

**Contexto.** El chip del gráfico decía «en vivo» siempre, y el bloqueo del motor
se mostraba como un código con un contador. Ambos casos producen la misma lectura
falsa: «esto se arregla solo».

**Decisión.**
- La frescura se calcula con la última vela (`≤150 s` vivo, `≤15 min` retrasado,
  más `parado hace N`, sin vela `sin datos`). Es la misma medida que
  `staleness_ms` del snapshot, aplicada a la pared del reloj.
- `/api/health` incluye `engine.status`, `engine.feed` y `last_bar_age_s`: un 200
  de FastAPI no prueba que el motor esté mirando el mercado.
- El bloqueo se enseña con tres datos además del código: qué significa, cuántas
  señales se rechazaron y desde cuándo, y qué lo desbloquea.

**Consecuencia.** Activar alertas desde la UI reconstruye el notifier en el acto;
sin eso, «guardado» era una promesa sin entrega (lo encontró la prueba de punta a
punta contra un webhook local).

## ADR 0.13 · Barrera temporal tras un reinicio e índice único de operaciones cerradas

**Contexto.** El feed de OKX hace backfill de 4 h y el motor restaura la posición
abierta al arrancar. Con las dos cosas a la vez, el motor recibía velas
*anteriores* a la entrada de esa posición y las procesaba: la operación se cerraba
«en el pasado», con `closed_ts` anterior a `opened_ts`, y el mismo cierre se
insertaba otra vez, así que el P&L del día se contaba dos veces. Un reinicio no
puede cambiar lo que pasó antes de él.

**Decisión.**
- `TradingEngine._restore()` fija `_replay_barrier` con `position.opened_ts`.
  `_process()` descarta cualquier tick anterior a esa marca (solo actualiza
  `last_bar_ts`) y levanta la barrera con el primer tick que la alcanza, dejando
  un evento `info` «el mercado alcanzó la posición restaurada». La barrera no se
  persiste: se reconstruye desde la posición guardada, y `_restore()` es la única
  vía de restauración (se llama solo desde `__init__`).
- Migración v2: índice único `idx_trades_unique` sobre
  `(mode, symbol, side, opened_ts, closed_ts, entry_price, exit_price, units)`.
  Antes de crearlo se deduplica la tabla —el índice no se puede crear sobre filas
  repetidas— y se registra cuántas filas se borraron como evento `warn` de
  categoría `maintenance`.
- `insert_trade()` usa `ON CONFLICT DO NOTHING` y devuelve el `id` de la fila
  existente en vez de fallar. No se usa `OR IGNORE`: eso también se tragaría una
  violación de `NOT NULL` o `CHECK` y convertiría un bug en un `0` silencioso.

**Consecuencia.** Un reinicio con backfill no puede fabricar una salida anterior
a la entrada ni duplicar el P&L. Coste: mientras dura el backfill el motor no
publica estado nuevo (solo `last_bar_ts`), y la identidad de una operación depende
de precios en coma flotante exactos: dos fills con precios distintos son dos
filas, con precios idénticos son una.

**Pendiente conocido.** `apply_migrations()` no envuelve la migración v2 en una
transacción explícita: si `CREATE UNIQUE INDEX` fallara, el `DELETE` de
deduplicación quedaría en la transacción implícita de la conexión y un `commit`
posterior lo consolidaría sin índice.

## ADR 0.14 · El stop y el objetivo tienen que estar del lado correcto

**Contexto.** `RiskManager` comprobaba que el stop existiera y que no estuviera en
el precio de entrada, pero no de qué lado caía. Un plugin con el signo cambiado
—o un payload construido a mano— abría una operación cuyo «stop» quedaba por
encima de la entrada (long) o cuyo «objetivo» quedaba por debajo: la primera vela
tocaba el nivel y el cierre se apuntaba como pérdida o ganancia de mercado que
nunca existió. Se vio al medir: al rechazar esas señales, `fade` pasa de 34 a 35
ganancias, porque una de ellas era un objetivo detrás de la entrada.

**Decisión.** Antes de dimensionar, `RiskManager.evaluate` rechaza con código
propio:
- `invalid_stop_side`: long con stop ≥ entrada, short con stop ≤ entrada.
- `invalid_target_side`: long con objetivo ≤ entrada, short con objetivo ≥
  entrada. Un objetivo nulo sigue permitido.

Los dos códigos están en `frontend/src/reasons.ts`, para que la pantalla diga «es
un fallo de la estrategia» y no enseñe un código crudo.

**Consecuencia.** Un plugin roto deja de producir operaciones fantasma: la señal
se rechaza y el motivo queda en el snapshot. `reference` y `donchian` no cambian
ni una cifra (60 d × 390 velas, mismo `pnl_net`); `fade` sí cambia (34 → 35
ganancias, −1.931,70 → −1.914,91 USD netos) y sigue RECHAZADA: la corrección
quita una ganancia que no existía, no crea edge.

**Resuelto en `fade` 0.2.0.** La causa estaba en `fade`, que podía emitir un
objetivo detrás de la entrada cuando la vela cerraba por encima de la media.
Ahora exige que el cierre quede por debajo de la media para el long y por encima
para el short, y el disparo descartado se anota en la fase como «extremo sin
recorrido hasta la media». Medido en 60 d × 390 velas, comparando las dos salidas
sección por sección: `closed`, `equity`, los cinco desgloses y `validation` son
idénticos (180 operaciones, −1.914,91 USD netos, PF 0,1236), porque el motor ya
rechazaba esas señales; solo cambian `strategy_version` y el recuento de eventos
(3.272 → 3.203: las 69 señales que dejan de nacer y su rechazo con él).

## ADR 0.15 · Un cierre repetido no se contabiliza dos veces

**Contexto.** El índice único de la migración v2 y la barrera temporal cierran la
puerta a la fila duplicada, pero no a la suma duplicada: `_on_trade_closed`
insertaba y después sumaba siempre el P&L a la equity, al día y a la curva.
`insert_trade` ya sabía cuándo la operación existía —devolvía su id— y el motor
tiraba ese dato.

**Decisión.**
- `Store.insert_trade_once()` devuelve `(id, era_nueva)`. `insert_trade()` se queda
  como envoltorio que devuelve sólo el id, para no romper llamantes.
- `_on_trade_closed` sólo contabiliza cuando la operación es nueva; si no, deja un
  `warning` con el id y no toca equity, día, racha ni curva.
- Las migraciones se aplican dentro de un `SAVEPOINT` con `ROLLBACK TO` al fallar.
  Medido en este driver: `BEGIN` y `SAVEPOINT` hacen transaccional el DDL; sin
  ninguno de los dos, un `CREATE TABLE` se autoconfirma y un fallo posterior deja
  media migración aplicada.

**Consecuencia.** Un cierre que llegue dos veces (reinicio con backfill, reintento,
replay) deja una fila y una suma, no dos. Coste: una consulta extra en el caso
raro de la fila duplicada.

## ADR 0.16 · La comisión de bolsa se cobra una vez

**Contexto.** `_fees` sumaba la comisión explícita del perfil
(`commission_per_unit_side` o `commission_pct_side`) y el modelo en puntos
básicos del `strategy_spec` (`fee_taker_bps + half_spread_bps`). En el perfil de
OKX la comisión explícita —0,049 USD por unidad, con unidad de 0,001 BTC— son
los mismos 5 pb de bolsa que el modelo en pb volvía a cobrar: cada lado pagaba
~10 pb. La evidencia se encarecía al medirla, no al ejecutarla.

**Decisión.**
- La comisión explícita (porcentaje del nocional o por unidad) sustituye al
  modelo en pb; el modelo en pb sólo se aplica cuando no hay comisión explícita.
- El medio spread y el impacto se suman siempre: no son la comisión de bolsa.
- `stressed_settings` duplica también `fee_maker_bps`, `fee_taker_bps` y
  `half_spread_bps`, para que el coste ×2 siga siéndolo aunque el perfil use el
  modelo en pb.

**Consecuencia.** El coste medido por lado vuelve a ser el declarado (5 pb +
medio spread). Las mediciones anteriores con el perfil de OKX están
sobrecargadas en ~5 pb por lado y hay que repetirlas antes de citarlas.