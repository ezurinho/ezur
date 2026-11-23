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
