# Qué hacen los mejores, y qué copiamos

Investigación hecha el **23 de noviembre de 2026**. Datos de estrellas, forks,
licencia y último push leídos en vivo de la API de GitHub ese día; el resto sale
de los README, de la documentación oficial y de los papers citados. Nada de
memoria.

La pregunta «¿cuál es el mejor bot de trading o bot de IA para trading ahora
mismo?» no tiene una respuesta única, y quien la dé sin matices está vendiendo
algo. Lo que sí tiene respuesta es **mejor en qué**: mejor motor, mejor
validación, mejor ejecución, mejor investigación, mejor interfaz. Esta nota
ordena el mercado por esas dimensiones y termina con lo que ezur debe copiar.

---

## 1. Datos reales (API de GitHub, 2026-11-23)

| Repositorio | ★ | Forks | Lenguaje | Licencia | Último push | Creado |
|---|---:|---:|---|---|---|---|
| TauricResearch/TradingAgents | 123.521 | 23.659 | Python | Apache-2.0 | 2026-11-17 | 2024-12-28 |
| OpenBB-finance/OpenBB | 75.651 | 7.894 | Python | AGPL/otra | 2026-11-18 | 2020-12-20 |
| virattt/ai-hedge-fund | 64.820 | 11.386 | Python | MIT | 2026-11-09 | 2024-11-29 |
| freqtrade/freqtrade | 57.171 | 11.802 | Python | GPL-3.0 | 2026-11-23 | 2017-05-17 |
| microsoft/qlib | 50.506 | 7.962 | Python | MIT | 2026-11-04 | 2020-08-14 |
| vnpy/vnpy | 46.461 | 12.614 | Python | MIT | 2026-11-11 | 2015-03-02 |
| ccxt/ccxt | 44.961 | 8.995 | Python | MIT | 2026-11-22 | 2017-05-14 |
| HKUDS/Vibe-Trading | 38.711 | 6.314 | Python | MIT | 2026-11-22 | 2026-04-01 |
| hsliuping/TradingAgents-CN | 33.047 | 6.870 | Python | — | 2026-11-14 | 2025-06-26 |
| nautechsystems/nautilus_trader | 31.752 | 4.338 | Rust | LGPL-3.0 | 2026-11-23 | 2018-06-25 |
| mementum/backtrader | 23.783 | 5.330 | Python | GPL-3.0 | 2024-08-19 | 2015-01-10 |
| QuantConnect/Lean | 22.659 | 5.444 | C# | Apache-2.0 | 2026-11-20 | 2014-11-28 |
| AI4Finance-Foundation/FinGPT | 21.685 | 3.073 | Jupyter | MIT | 2026-11-18 | 2023-02-11 |
| hummingbot/hummingbot | 21.357 | 5.169 | Python | Apache-2.0 | 2026-11-20 | 2019-04-02 |
| AI4Finance-Foundation/FinRL | 17.172 | 3.666 | Jupyter | MIT | 2026-11-18 | 2020-07-26 |
| OpenByteInc/QuantDinger | 13.918 | 2.831 | Python | Apache-2.0 | 2026-11-22 | 2025-12-28 |
| StockSharp/StockSharp | 11.150 | 2.319 | C# | — | 2026-11-22 | 2014-12-08 |
| polakowo/vectorbt | 9.917 | 1.324 | Python | — | 2026-11-11 | 2017-11-14 |
| kernc/backtesting.py | 9.281 | 1.594 | Python | AGPL-3.0 | 2026-08-05 | 2019-01-02 |
| jesse-ai/jesse | 8.828 | 1.295 | Python | MIT | 2026-11-17 | 2018-11-09 |
| AI4Finance-Foundation/FinRobot | 8.467 | 1.432 | Python | Apache-2.0 | 2026-10-24 | 2024-02-27 |
| tensortrade-org/tensortrade | 7.273 | 1.341 | Python | Apache-2.0 | 2026-02-19 | 2019-07-30 |
| Drakkar-Software/OctoBot | 6.973 | 1.330 | Python | GPL-3.0 | 2026-11-21 | 2018-02-23 |
| ricequant/rqalpha | 6.890 | 1.803 | Python | — | 2026-10-28 | 2016-07-20 |
| Superalgos/Superalgos | 5.816 | 5.991 | JavaScript | Apache-2.0 | 2026-11-14 | 2019-08-12 |
| edtechre/pybroker | 3.726 | 465 | Python | — | 2026-11-21 | 2023-01-16 |
| TradeMaster-NTU/TradeMaster | 3.136 | 571 | Jupyter | Apache-2.0 | 2025-06-04 | 2022-08-23 |
| wquguru/nof0 | 2.753 | 427 | Go | — | 2025-12-07 | 2025-10-22 |
| ginlix-ai/LangAlpha | 2.340 | 392 | Python | Apache-2.0 | 2026-11-23 | 2026-01-18 |
| coding-kitties/investing-algorithm-framework | 2.252 | 321 | Python | Apache-2.0 | 2026-11-17 | 2019-12-18 |
| stefan-jansen/zipline-reloaded | 2.021 | 354 | Python | Apache-2.0 | 2026-11-02 | 2021-02-25 |
| pipiku915/FinMem-LLM-StockTrading | 974 | 194 | Python | MIT | 2024-08-18 | 2023-12-01 |
| gbeced/basana | 878 | 112 | Python | — | 2026-11-06 | 2023-03-04 |

Lectura rápida: las estrellas miden atención, no dinero ganado. Cuatro de los
cinco repositorios más populares son frameworks de **investigación** o de
**infraestructura**; ninguno publica una curva de capital auditada. Los dos
proyectos con más actividad nueva (`Vibe-Trading`, `QuantDinger`) nacieron en
los últimos doce meses y son agentes LLM con ejecución real opcional.

---

## 2. Veredicto por categoría

No hay «el mejor bot». Hay un mejor en cada eje, y elegir mal el eje es cómo se
pierde dinero.

| Si lo que quieres es… | Elige | Por qué |
|---|---|---|
| Motor de ejecución serio, backtest y live idénticos | **NautilusTrader** | Núcleo en Rust, determinista, mismo código en research y producción, multi-venue y multi-instrumento con resolución de nanosegundos |
| Realismo de mercado institucional | **QuantConnect LEAN** | Modela relleno, slippage, comisiones, liquidación, buying power, margin calls, disponibilidad de cortos y dividendos como familias de modelos separadas |
| Automatizar cripto en producción mañana | **Freqtrade** | 57k★, GPL, mantenido a diario, *protections*, dry-run, FreqAI, Telegram/REST |
| Market making y liquidez en CEX/DEX | **Hummingbot** | Conectores, *controllers*, gestión de órdenes y de inventario pensada para market making |
| Buscar alpha con ML de verdad | **Qlib** (+ RD-Agent) | Pipeline de datos → features → modelo → backtest → serving, módulos desacoplados, zoo de modelos con papers |
| Investigación con RL | **FinRL** / **TradeMaster** | Entornos de trading estandarizados y *papers* reproducibles |
| Framework de agentes LLM con más tracción | **TradingAgents** | 123k★, equipo de analistas + debate + gestor de riesgo, memoria de decisiones, backtest propio |
| Arquitectura «agent-native» con procedencia | **Vibe-Trading** (arXiv 2611.24845) | Cada resultado conserva fuente, alcance temporal, configuración y ejecución; puerta de autoridad explícita para operar |
| Órdenes gobernadas por un agente | **LangAlpha** | Consentimiento por conexión, aprobación por orden, token de ejecución de un solo uso atado a los argumentos, credenciales fuera del sandbox |
| Aprender mirando código pequeño | **backtesting.py**, **vectorbt**, **Jesse** | API mínima, ejemplos claros, sin andamiaje empresarial |
| Interfaz para no programadores | **OctoBot**, **Superalgos** | UI visual, estrategias por bloques |
| Terminal de datos y research | **OpenBB** | Agregación de proveedores y workspace |
| Mercados chinos y futuros | **vnpy**, **rqalpha**, **StockSharp** | Gateways y reglas de mercado locales |

Y los que están de facto congelados: `backtrader` (último push agosto 2024),
`zipline` original (sustituido por `zipline-reloaded`), `gekko` (2020),
`zenbot` (2022), `FinMem` (2024). Siguen siendo útiles para leer, no para elegir.

---

## 3. Fichas: qué hace cada uno y qué se aprende

### NautilusTrader — el patrón «un solo runtime»

Núcleo en Rust con bindings de Python (PyO3), bus de mensajes y caché como
piezas ensamblables, persistencia opcional en Redis, resolución de nanosegundos.
Su tesis: *research* en Python vectorizado y *producción* en un lenguaje compilado
son dos mundos, y el salto entre ellos es donde se pierde el edge.

**Lección para ezur:** el mismo `TradingEngine` ya corre replay y simulación, pero
no hay un test que exija **paridad** entre el mismo día en backtest y en paper.
Ese test es la versión barata de la promesa de Nautilus.

### QuantConnect LEAN — el realismo, descompuesto

Su documentación de *reality modeling* separa familias de modelos: relleno
(immediate, latest price, equity, future, future option), slippage, comisiones,
liquidación, buying power, margin calls, disponibilidad de cortos, tipo libre de
riesgo, dividendos e interés de margen. Cada una se sustituye por separado.

**Lección para ezur:** nuestro `ExecutionConfig` mezcla relleno, comisión y
slippage en un solo objeto. Los tres modelos de fill que acabamos de añadir van
en esa dirección; el siguiente paso es separarlos en objetos con su propio
contrato.

### Freqtrade — las *protections* como ciudadanas de primera

Cuatro protecciones con ventana de lookback: `StoplossGuard` (N stops en un
periodo → parar), `MaxDrawdown` (con dos modos: *ratios* heredado y *equity*
real), `LowProfitPairs` (pareja con beneficio por debajo del umbral → bloquear) y
`CooldownPeriod` (espera tras salir). Todas con `only_per_pair`, `only_per_side`
y desbloqueo por tiempo.

Detalle que vale oro: su propio documento advierte que el modo `ratios` **no es**
el drawdown de la curva de capital. Una protección de drawdown que no mide el
drawdown es un adorno.

**Lección para ezur:** tenemos racha de pérdidas y cooldown, pero no un guardián
de drawdown sobre el pico de capital. Es la protección que más falta.

### Hummingbot — conectores y órdenes, no señales

Market making multi-exchange: conectores estandarizados, *controllers* con
lógica de inventario, seguimiento de órdenes y presupuesto de inventario.

**Lección para ezur:** cuando llegue el adaptador real, el trabajo no es «enviar
una orden», es reconciliar órdenes y posiciones contra el broker.

### Qlib — módulos desacoplados y serving online

Datos, features, modelos, estrategias, ejecución y reportes como piezas
intercambiables; el mismo pipeline sirve en *offline* (research) y *online*
(producción) sin reescribir. RD-Agent añade agentes LLM que proponen factores y
los evalúan en bucle.

**Lección para ezur:** separar «investigación de señal» de «ejecución» es lo que
permite que el mismo artefacto se valide y luego se opere.

### Vibe-Trading — procedencia y puerta de autoridad

Tres ideas centrales, textuales del paper (arXiv 2611.24845, 18-nov-2026): cada
resultado conserva **fuente, alcance temporal, configuración y ejecución que lo
produjo**; el *grounding* de evidencia compartido permite verificar; y una
**puerta de autoridad explícita** separa la investigación de la ejecución real.
En la práctica: 28 fuentes de datos con cadenas de *fallback* deterministas,
19 conectores de broker con perfiles read/sim/live, 478 alphas comparadas entre
cinco librerías, cuentas «Shadow» para replicar tus propias reglas.

**Lección para ezur:** nuestro ledger registra hash de configuración y de
métricas, pero no el **hash del dataset** ni un `run_id` que agrupe la ejecución
completa. Sin eso, un resultado no es reproducible, solo repetible.

### TradingAgents — el patrón multi-agente y su letra pequeña

Analistas (fundamental, sentimiento, noticias, técnico) en paralelo, investigadores
toro/oso debatiendo, *trader*, equipo de riesgo y gestor de cartera que aprueba o
rechaza. Memoria en `trading_memory.md` que **liquida** cada decisión cuando vence
su horizonte, calcula retorno y alpha contra el índice regional, y escribe una
reflexión que el gestor lee en la siguiente ronda. Checkpoint por ticker para
reanudar ejecuciones interrumpidas.

Su sección de reproducibilidad es honesta y merece copiarse entera: los LLM no
son deterministas ni a temperatura fija; los datos vivos cambian entre
ejecuciones; por eso el resultado de hoy no reproduce el de ayer. Su backtest
(paper, §5.1) cubre **1-ene a 29-mar-2024**, cinco tecnológicas, contra cinco
baselines (buy & hold, MACD, KDJ+RSI, ZMR, SMA), con la regla de entrar al primer
cierre posterior a la decisión para no usar noticias posteriores al cierre.

**Lección para ezur:** la memoria que se liquida contra el resultado real es un
mecanismo de aprendizaje barato y verificable. Y su ventana de evaluación —tres
meses, cinco activos— es exactamente el tipo de muestra que nuestras puertas G4
(mínimo 80 operaciones) rechazarían.

### ai-hedge-fund — ledger encadenado y mandatos sin tickers

Se declara explícitamente «educational», «the system does not actually make any
trades», pero su ingeniería de producto es la más madura de los proyectos LLM:
paper trading con **ledger encadenado por hash** por fondo, aprobación de la
decisión exacta antes de ejecutar, *kill switch*, backtest contra benchmark y
mandatos que definen estrategia y capital **sin** fijar tickers (el universo se
elige por ejecución).

**Lección para ezur:** encadenar el ledger de experimentos con el hash anterior
convierte una lista de líneas en una prueba de que nadie insertó un resultado en
el medio. Es barato y es exactamente nuestro problema.

### LangAlpha — órdenes gobernadas

Consentimiento por conexión (grupos de capacidades), aprobación por orden,
token de ejecución de un solo uso atado al intento, la herramienta y el hash de
los argumentos; credenciales del broker fuera del sandbox; *reconciler* que
cuadra las órdenes con los registros del broker; ledger de cada intento.

**Lección para ezur:** es el diseño que debe tener nuestro ADR 0.3 cuando se
implemente el adaptador. Hoy `LiveConfig` exige `adapter_implemented` y
confirmación explícita: la puerta existe, pero el mecanismo interno no.

### QuantDinger — filtro pre-trade y agentes por MCP

Plataforma self-hosted: idea → código Python → backtest → paper/live →
monitorización, con un **filtro de decisión pre-trade** opcional y agentes vía
MCP. Su aviso es prudente: órdenes reales solo si se habilitan, empezar en paper,
claves restringidas.

**Lección para ezur:** nuestro `RiskManager` ya es ese filtro; lo que falta es
exponerlo con un contrato estable (MCP o HTTP) para que un agente lo consulte sin
poder saltárselo.

### El resto, en una línea

`OpenBB` agrega datos; `vnpy`, `rqalpha` y `StockSharp` cubren mercados y brokers
que Occidente ignora; `OctoBot` y `Superalgos` enseñan que la UI vende; `Jesse`
es el backtest cripto más limpio para leer; `vectorbt` y `backtesting.py` son la
mejor forma de entender equity curves sin infraestructura; `tensortrade`,
`FinRL`, `TradeMaster`, `FinGPT` y `FinRobot` son material de investigación, no
productos.

---

## 4. La ola «AI trading agent»: qué es real

**Real:**
- La descomposición por roles funciona para *producir informes* y para forzar
  debate; es una técnica de razonamiento, no una fuente de edge.
- La memoria liquidada contra resultados (TradingAgents) y el ledger encadenado
  (ai-hedge-fund) son mecanismos verificables de mejora del proceso.
- La puerta de autoridad y las órdenes gobernadas (Vibe-Trading, LangAlpha) son
  la respuesta correcta al riesgo de dejar un LLM con una cuenta real.
- La procedencia (fuente, fecha, configuración, run) es lo que separa un
  resultado reproducible de una anécdota.

**No real (o no demostrado):**
- Que un LLM prediga precios con ventaja estable. Los propios frameworks lo
  admiten: recomiendan investigación, avisan de no-determinismo y evalúan sobre
  ventanas de meses.
- Que las estrellas indiquen rentabilidad. `ai-hedge-fund` dice literalmente que
  no opera; `TradingAgents` avisa de que el rendimiento varía con el modelo, la
  temperatura y el periodo.
- Que un backtest de tres meses sobre cinco tecnológicas en un mercado alcista
  demuestre algo. Con nuestras puertas, ese experimento ni se registra.

**Conclusión honesta:** hoy el «mejor bot de IA» es el que **no deja que la IA
toque el capital**. La IA aporta investigación, generación de hipótesis,
explicación y operación; la ejecución debe seguir siendo determinista, con
límites duros y auditoría.

---

## 5. Lo que ezur copia, por orden de valor

| # | Idea | Origen | Dónde va | Cómo se comprueba |
|---|---|---|---|---|
| 1 | Guardián de drawdown sobre el pico de capital | Freqtrade (`MaxDrawdown` en modo equity) | `server/risk.py`, `RiskConfig.max_drawdown_pct` | test: equity cae 5 % desde el pico → entrada rechazada |
| 2 | Ledger encadenado por hash | ai-hedge-fund | `server/experiments.py` (`prev_hash`, `chain_hash`, `verify_chain`) | test: editar una línea del medio rompe la cadena |
| 3 | `dataset_hash` + `run_id` por ejecución | Vibe-Trading | `build_record`, informes de simulación | test: mismo dataset y config → mismo `run_id` |
| 4 | Memoria de decisiones liquidada contra el resultado | TradingAgents | tabla `decisions` + job de liquidación | test: decisión vencida calcula retorno y alpha |
| 5 | Órdenes gobernadas (token de un solo uso, args hash) | LangAlpha | `server/broker/` (futuro) | test de doble envío rechazado |
| 6 | Paridad backtest/live del mismo día | Nautilus | `tests/test_parity.py` | mismo día, mismos fills, desviación 0 |
| 7 | Realismo descompuesto en familias de modelos | LEAN | refactor de `ExecutionConfig` | tests por familia |
| 8 | Cadenas de proveedores con `local:` sin fallback | Vibe-Trading | `server/market/` | test: `local:` nunca sale a la red |
| 9 | Filtro pre-trade expuesto por contrato | QuantDinger | `server/api.py` | test de contrato |
| 10 | Run directory con estrategia, trades y equity | Vibe-Trading | `reports/runs/<run_id>/` | test: artefactos presentes y hasheados |

Lo que **no** copiamos: personas de inversores famosos como sustituto de un
modelo (ai-hedge-fund), debate multi-agente como capa de decisión de capital
(TradingAgents), telemetría infinita de UI (Superalgos), ni frameworks que no se
actualizan desde 2024.

---

## 6. Cierre

El mercado open source está maduro en **infraestructura** y joven en
**validación**. Los mejores motores (Nautilus, LEAN) casi no hablan de
rentabilidad; los proyectos más populares de IA (TradingAgents, ai-hedge-fund) se
declaran investigación y admiten no operar o no ser deterministas. Esa asimetría
es la oportunidad de ezur: no competir en estrellas ni en agentes, sino en la
única cosa que nadie publica, **un resultado reproducible con su veredicto y su
cadena de custodia**.

Fuentes: API de GitHub (2026-11-23), READMEs y documentación de cada proyecto,
arXiv 2412.20138 (TradingAgents) y arXiv 2611.24845 (Vibe-Trading), documentación
de *reality modeling* de QuantConnect y de *protections* de Freqtrade.
