# Decisiones pendientes (Fase 0)

Puerta **P0**: sin estos ADR cerrados no se empieza la Fase 4. Un holdout
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
| Estado | CERRADO (2026-11-27) |
| Proveedor | Binance Vision (`data.binance.vision`) para histórico; API pública de OKX para papel y confirmación |
| Granularidad | 1 minuto; tick se pospone a la fase de ejecución |
| Coste | 0: datos públicos, sin clave ni cuota; solo almacenamiento y tiempo de descarga |
| Contratos y vencimientos documentados | Spot `BTCUSDT` (sin vencimiento); UM perpetuo `BTCUSDT` (sin vencimiento, funding 8 h); trimestrales `BTCUSDT_YYMMDD` (último viernes de mar/jun/sep/dic, 08:00 UTC) |
| Alternativa descartada | OKX como única fuente histórica; API de Binance para vivo; vendors de pago (Kaiko, Tardis, Amberdata, Crypto Lake); tick inmediato |
| Motivo | Es la única fuente gratuita, verificable por checksum y con historia suficiente para 2020-2026; desbloquea G1/G3/G14 y permite verificar rolls con contratos reales |
| Criterio mínimo | ≥ 12 meses de historia con volumen real (ADR 0.1); la ventana canónica es 2020-01-01 → presente |

**Contexto.** La nota de datos es 3/10: el bot mide sobre velas sintéticas y CSV, y el propio README lo dice. La API pública de OKX entrega cientos de velas por llamada, suficiente para el gráfico y el backfill de 4 h, pero no para validar una tendencia diaria. `api.binance.com` responde 451/403 desde esta región; `data.binance.vision` sí responde y publica los ZIP mensuales con su `.CHECKSUM`. Ya se midió: 3.591.915 velas de 1 m de `BTCUSDT` entre 2020-01-01 y 2026-10-31, 2.496 velas diarias y ningún día ausente. G1/G3/G14 siguen en «no medible» porque el dataset sintético no puede pasar el validador con datos reales ni verificar rolls.

**Decisión.**

1. **Dos venues, un solo dataset.** El histórico largo se descarga de **Binance Vision**; el feed de papel sigue en **OKX**. La razón no es preferencia: Binance no deja usar su API desde aquí, y OKX no entrega años de 1 m sin decenas de miles de peticiones. Vision se usa solo para construir el dataset; OKX se usa para el vivo y para confirmar que el histórico no se ha desviado.
2. **Cobertura.** Spot `BTCUSDT`, UM perpetuo `BTCUSDT` y trimestrales `BTCUSDT_YYMMDD`. Base de 1 minuto; 15 m, 1 h, 4 h y 1 D se obtienen con el `resample` determinista que ya existe. Ventana canónica: **2020-01-01 → presente**; 2017-08 a 2019-12 queda como contexto opcional y no se usa para puertas ni holdout.
3. **Símbolo normalizado.** En el CSV del bot el símbolo es `BTC-USDT` para spot y perpetuo; el símbolo exacto del vendor (`BTCUSDT`, `BTCUSDT_YYMMDD`) vive en el manifiesto. Así el motor no aprende nombres de exchange y el mismo dataset sirve para OKX y Binance.
4. **Manifiesto y hash.** Cada dataset lleva un `manifest.json` con vendor, URLs, checksums, mercado, símbolos, intervalo, rango, filas, huecos, rolls, cobertura de funding, fecha de construcción y versión del código. `dataset_id` sigue siendo el SHA-256 del CSV (compatibilidad con el ledger); el manifiesto añade su propio `manifest_sha256`. Un dataset sin manifiesto no es válido para un veredicto.
5. **Rolls con contratos reales, no una serie sintética.** Para trimestrales se descarga cada contrato por separado y se construye una serie continua con un **ledger de rolls explícito**: se cierra el contrato que vence y se abre el siguiente en la misma barra, con comisión y slippage de ambos lados; el evento queda en el manifiesto con símbolos, precios y coste. La serie que ven las señales es **sin ajustar**; la ajustada, si se usa, es solo para el gráfico. Así G3 puede verificar la continuidad contra los contratos reales en vez de responder «sin rolls que verificar».
6. **Política de roll.** Vencimiento el último viernes de marzo, junio, septiembre y diciembre a las 08:00 UTC. Roll **T-3 días a las 08:00 UTC**. Si el contrato entrante no tiene barras en la ventana, se rechaza el roll y se documenta; no se rellena.
7. **Funding y mark price.** Se descargan `fundingRate` y `markPriceKlines` del UM. El dataset los incluye; si el motor los cobra o no es ADR 0.6, no este.
8. **Basis entre venues.** El histórico es de Binance y el papel de OKX; la diferencia de precio se mide (ver calidad) y el **holdout final se confirma con datos de OKX**, no solo de Binance. Un backtest de research no es evidencia de ejecución en otro venue.

**Calidad del feed (G1/G3/G14).**

| Comprobación | Umbral | Si falla |
|---|---|---|
| Checksum del ZIP contra `.CHECKSUM` | 100 % de los meses | Re-descargar; si persiste, abortar el mes |
| Esquema, UTC, barras cerradas | exacto | Rechazar el fichero |
| Duplicados y timestamps monótonos | 0 | Rechazar |
| Invariantes OHLC (`low ≤ o,c ≤ high`, `v ≥ 0`) | 0 violaciones | Rechazar |
| Completitud 1 m | 1.440 barras/día; huecos > 5 barras/día se marcan; > 1 día se rechaza | Cuarentena y revisión |
| Días diarios completos | 2.496/2.496 en 2020-2026 | Rechazar la ventana |
| Precio Binance vs OKX (90 días solapados) | mediana ≤ 5 pb; p99 ≤ 25 pb | Investigar antes de usar; no ajustar el umbral después de ver resultados |
| Funding UM | una tasa cada 8 h, sin huecos | Rechazar la ventana |
| Frescura del feed vivo | ≤ 150 s vivo; ≤ 15 min retrasado (ADR 0.12) | Mostrar «retrasado/parado», no operar |
| Reproducibilidad | mismo CSV y mismo manifiesto ⇒ mismo hash dos veces | Rechazar (G1/G2) |
| Continuidad de roll | sin hueco en la costura, coste registrado, contrato viejo sin barras tras vencer | Rechazar el roll |

Nunca se rellena un hueco hacia delante ni se inventa una barra: un hueco se declara y, si afecta a la ventana de validación, invalida el dataset. La reconciliación de precio compara cierres, no volumen: el volumen es del venue y no tiene por qué coincidir.

**Plan para conectarla (sin implementar el adaptador todavía).**

- **Fase 0 · Contrato.** Añadir al esquema de configuración `data.provider` con `vision` y `data.market` (`spot`/`um`/`quarterly`), `data.symbol`, `data.history_start` y `data.manifest`; documentar el manifiesto. No se toca el motor. *Aceptación:* la configuración valida, los tests siguen verdes y el valor por defecto continúa siendo `simulated`.
- **Fase 1 · Constructor histórico.** Descargar ZIPs + `.CHECKSUM`, verificar, convertir al CSV del bot, remuestrear y escribir el manifiesto; descarga incremental mensual. *Aceptación:* 2020-01 → 2026-10 con 3.591.915 filas de 1 m, 2.496 días diarios, 100 % de checksums y hash reproducible; el CSV canónico queda por debajo del límite de 250 MB del loader.
- **Fase 2 · Reconciliación.** Informe de 90 días solapados Binance/OKX con mediana y p99 de la diferencia de cierre. *Aceptación:* dentro de los umbrales de la tabla; si no, se para y se investiga antes de tocar puertas.
- **Fase 3 · Validador y puertas.** El dataset real entra por el mismo `Dataset.load`; G1/G3/G14 pasan de «no medible» a medidos; un backtest golden congelado demuestra determinismo. *Aceptación:* `--gates` con datos reales, sin filas «no medible» en G1/G3/G14, mismo `dataset_id` en dos corridas.
- **Fase 4 · Futuros y rolls.** Si ADR 0.1 elige perpetuo o trimestral: ficheros por contrato, calendario de vencimientos, ledger de rolls y serie continua. *Aceptación:* un trimestre con vencimiento conocido cuadra, el coste del roll se registra y G3 verifica la costura contra los contratos.
- **Fase 5 · Holdout.** Congelar el manifiesto antes de abrir la ventana; evaluar una sola vez; confirmar con OKX. *Aceptación:* hashes registrados antes de la evaluación y una única lectura del holdout.

**Consecuencias.** G1/G3/G14 dejan de ser un límite y la nota de datos debería subir de 3 a 8–9 sin tocar el motor. A cambio aparece una dependencia operativa: descarga mensual, verificación de checksums y reconciliación; si Vision cambia una ruta o deja de publicar, el dataset se congela y se documenta, no se rellena. El espacio es del orden de 1 GB de ZIPs y 160 MB de CSV; los ZIPs van a `data/vision` (ignorado por git) y solo los manifiestos pequeños se versionan. Los datos son públicos; no se redistribuyen los ficheros crudos del vendor.

**Lo que este ADR no decide.** El instrumento primario y los de contexto (ADR 0.1), la ejecución (0.3), la temporalidad de decisión (0.5) y si el funding se cobra en el P&L (0.6). Tampoco implementa el adaptador: hasta que exista, `data.provider=simulated` sigue siendo el único camino completo y el valor por defecto del código no cambia.

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
| 2026-11-27 | 0.2 | Binance Vision para histórico y OKX para papel; 1 m con checksums, funding y rolls por contrato | Ezuryseth |

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

El ADR 0.2 se cerró el 2026-11-27 con Binance Vision para el histórico y OKX para papel. La tabla sigue mostrando `simulated` porque el adaptador aún no existe: la decisión fija el destino, no adelanta el estado del código.

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

## ADR 0.17 · La escalera de frenos recorta, no cierra; y la pausa por racha solo existe sin frenos suaves

**Contexto.** Con `soft_brakes: true`, `risk.py` multiplica el tamaño en vez de
rechazar: drawdown, pérdida diaria y racha recortan unidades, y solo el tope
duro (`soft_brake_halt_multiple` veces el límite de drawdown) cierra la puerta.
La rama de la racha tiene una consecuencia que no se ve leyendo el perfil: el
`elif cfg.loss_streak_cooldown_min` solo se evalúa cuando `soft_brakes` es
falso, así que con frenos suaves la pausa de minutos no se aplica nunca. El 23
de noviembre, con 240 min configurados y racha de 5, el motor siguió operando a
media máquina: −615,68 $ en un día, el 90 % del rojo acumulado.

**Decisión.** La escalera se mantiene como está: recortar antes que cerrar es
el contrato que fija `test_risk_ladder.py`, y un freno que corta la sesión
entera por tres pérdidas seguidas es una decisión de producto, no un detalle de
implementación. Lo que se fija por escrito es la semántica real: con
`soft_brakes` activo, `loss_streak_cooldown_min` no pausa nada y quien quiera
pausa dura tiene que apagar los frenos suaves.

**Consecuencia.** El perfil puede declarar una pausa que no ocurre, y ese
valor además entra en el hash de la config: cambiarlo para dejar de mentir
invalidaría la evidencia de promoción. Mientras el hash firme el bloque
`risk` entero, la pausa de 240 min se queda como está y se documenta aquí en
lugar de tocarse a ciegas.

## ADR 0.18 · La pausa por racha vuelve a pausar

**Contexto.** El ADR 0.17 dejó escrito que, con `soft_brakes` activo, el
`loss_streak_cooldown_min` no se aplicaba nunca: la racha solo recortaba el
tamaño. El perfil anunciaba 240 minutos de pausa y no ocurrían. Con la huella
de investigación separada del perfil, tocar los frenos ya no invalida la
evidencia, así que cumplir lo declarado deja de costar una re-medida.

**Decisión.** Si el perfil declara `loss_streak_cooldown_min > 0`, la racha
rechaza la entrada hasta que pase la pausa, con o sin frenos suaves. El
recorte a media máquina queda solo para perfiles que alcanzan la racha sin
declarar minutos. No se toca ningún límite de riesgo ni se relaja ninguna
puerta: es la misma racha, ahora sí esperando lo que dice el fichero.

**Consecuencia.** Tras tres pérdidas seguidas el motor deja de abrir durante
240 minutos en el perfil de OKX. El `block_reason` resultante caduca por tiempo
y el motor ya sabía expirarlo (`engine._expire_blocks`), así que no hace falta
otro estado.