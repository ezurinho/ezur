# Investigación de interfaz y laboratorio — 23/11/2026

Datos de GitHub tomados el 2026-11-23 desde la API (`stargazers_count`,
`pushed_at`, licencia). Nada de esta tabla es de memoria.

| Proyecto | ★ | Último push | Licencia | Lenguaje | Qué aporta a ezur |
|---|---:|---|---|---|---|
| freqtrade/freqtrade | 57 173 | 2026-11-23 | GPL-3.0 | Python | Informe de backtest por bloques, *enter/exit tag stats*, resumen con Sharpe/Sortino/Calmar/SQN |
| OpenBB-finance/OpenBB | 75 651 | 2026-11-18 | NOASSERTION | Python | Consistencia de proveedores de datos y capa de «research» separada del trading |
| microsoft/qlib | 50 506 | 2026-11-04 | MIT | Python | Separación estricta entre dataset, modelo y evaluación |
| nautechsystems/nautilus_trader | 31 752 | 2026-11-23 | LGPL-3.0 | Rust | Paridad investigación↔live con la misma implementación de estrategia |
| mementum/backtrader | 23 783 | 2024-08-19 | GPL-3.0 | Python | Referencia histórica; congelado desde 2024, no se copia |
| hummingbot/hummingbot | 21 357 | 2026-11-20 | Apache-2.0 | Python | Market making multi-venue; backtesting nativo limitado |
| quantopian/zipline | 20 264 | 2024-02-13 | Apache-2.0 | Python | Congelado; su lección es el *pipeline* de datos, no el código |
| tradingview/lightweight-charts | 17 946 | 2026-11-18 | Apache-2.0 | TypeScript | Lo que ya usamos para velas |
| polakowo/vectorbt | 9 917 | 2026-11-11 | NOASSERTION | Python | Barrido vectorizado de parámetros; útil fuera del bucle de ticks |
| ghostfolio/ghostfolio | 9 763 | 2026-11-22 | AGPL-3.0 | TypeScript | UI de cartera: benchmark, asignación, «X-ray» de exposición |
| jesse-ai/jesse | 8 828 | 2026-11-17 | MIT | Python | Benchmark batch, *rule significance testing*, Monte Carlo |
| ranaroussi/quantstats | 7 906 | 2026-11-02 | Apache-2.0 | Python | Informe de métricas con benchmark y drawdown |
| Drakkar-Software/OctoBot | 6 973 | 2026-11-21 | GPL-3.0 | Python | Interfaz visual multi-dispositivo y backtesting desde la UI |
| Superalgos/Superalgos | 5 816 | 2026-11-14 | Apache-2.0 | JavaScript | Visualización de estrategia como grafo |
| hudson-and-thames/mlfinlab | 4 973 | 2023-10-02 | NOASSERTION | Python | Purged CV; congelado, se cita el concepto |

## Hallazgos que cambian decisiones

### 1. La comparación por lotes es el patrón, no la excepción

Jesse documenta *Benchmark* como «run batch backtests, compare across
timeframes, symbols, and strategies. Filter and sort results by key performance
metrics» (`README`, sección Benchmark). vectorbt existe entero para eso. ezur
solo sabía correr una estrategia por vez desde la CLI: la pantalla de
laboratorio con tabla comparativa no es un adorno, es la función que estas
herramientas consideran central.

**Adoptado:** `POST /api/backtest/compare` + vista Laboratorio. **No adoptado:**
optimización de parámetros por fuerza bruta dentro del servidor (vectorbt lo
hace mejor y fuera del bucle de ticks).

### 2. El veredicto se separa de las métricas

Freqtrade imprime un bloque `SUMMARY METRICS` con Sharpe, Sortino, Calmar y SQN
(`docs/backtesting.md`), y aun así deja la decisión al operador. Jesse añade
pruebas de significancia y Monte Carlo **antes** de paper trading. La lección
para ezur: las puertas G1–G14 ya son ese veredicto; lo que faltaba era
enseñarlas junto al resultado, no en otro documento.

**Adoptado:** puertas con ✓/✗ y motivo en la misma tarjeta del backtest, y
`verdict` en la fila del historial. **No adoptado:** Monte Carlo y *rule
significance* propios (requieren N corridas; el arnés puede lanzarlas, pero hoy
no hay estrategia candidata que merezca ese gasto — se declara).

### 3. Trazabilidad de la corrida

Nautilus insiste en «identical strategy implementations between research and
live deployment»; para poder afirmarlo hace falta identificar la corrida. En
ezur `run_id` era el prefijo del hash del dataset: dos estrategias sobre el
mismo CSV compartían identificador.

**Adoptado:** `run_id` único por ejecución, `dataset_id` como hash de contenido,
`config_hash` del settings efectivo y `run_group` para comparaciones.
**No adoptado:** persistencia de estado en Redis (Nautilus) — aquí el estado es
SQLite y ya sobrevive reinicios.

### 4. La interfaz de cartera enseña exposición, no solo rentabilidad

Ghostfolio (9 763 ★) organiza la pantalla alrededor de asignación, benchmark y
«X-ray» de exposición. ezur enseña P&L pero no *cuánto del resultado viene de un
solo instrumento o de un solo día*. `stats.by_side` y `top5_share` ya existen en
el backend y no se veían.

**Adoptado:** histograma de R por buckets reales y concentración visible en
Estadísticas. **No adoptado:** benchmark contra índice — el perfil actual es un
solo par cripto 24/7 y compararlo contra SPY sería una comparación inventada.

### 5. Lo congelado no se copia

backtrader (último push 2024-08-19), zipline (2024-02-13) y mlfinlab (2023-10-02)
siguen teniendo estrellas y siguen apareciendo en listas. No entran: el criterio
es actividad, no popularidad.

## Lo que se implementa esta noche (y por qué)

| Función | Origen de la idea | Archivo destino |
|---|---|---|
| `run_id` único + `config_hash` + `run_group` | Nautilus / auditoría | `server/backtest.py`, `server/experiments.py` |
| Comparar N estrategias en un dataset | Jesse Benchmark, vectorbt | `server/api.py`, vista `Lab` |
| Puertas junto al resultado | Freqtrade summary + ezur G1–G14 | vista `Lab` |
| Histograma de R y concentración | Ghostfolio / QuantStats | `pages/Stats.tsx` |
| Ayuda de atajos y paleta con acciones | patrón de terminal | `components/Shortcuts.tsx` |
| Alerta de prueba desde la UI | operación real | `POST /api/alerts/test` |

## Lo que se decide no hacer

- Copiar el informe HTML de QuantStats: es un PDF disfrazado y no se puede
  filtrar. Se prefieren tablas vivas.
- Copiar el grafo de estrategia de Superalgos: bonito, pero un plugin de Python
  con tests es más honesto que un lienzo que hay que interpretar.
- Copiar el asistente MCP de Jesse: ya hay un agente en esta terminal; duplicar
  la capa de IA dentro del producto no mejora la medida.
