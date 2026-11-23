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
