# Pre-registro H1 — tendencia BTC spot 1 h

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar y antes de ejecutar cualquier backtest.
**Hipótesis:** el trend following en BTC spot a 1 h conserva una ventaja neta
después de costes porque reduce la rotación 4× frente a 15 m sin perder la señal
de tendencia. Si falla una puerta dura, H1 se archiva y no se reajusta.

## Corrección de viabilidad (antes de medir)

El plan pedía 4 h y ≥100 operaciones OOS. El conteo de señales sobre el dataset
canónico mostró que 4 h no puede cumplirlo en un solo par: con un canal de 55
velas y filtro SMA200 hay 31 señales espaciadas 24 h en 2025; con 40 velas, 36;
con 10 velas, 55. Aun sin ocupación de posición, ninguna llega a 100.

Se corrige el marco a **1 h** antes de implementar o ejecutar nada, y se amplía
la validación a 2025-01-01/2026-11-01 (22 meses, sin tocar el holdout de
2026-12). Con 1 h y canal de 10-20 velas hay 121-150 señales espaciadas en 2025,
suficientes para superar las 100 operaciones OOS tras descontar la ocupación.
La corrección es de viabilidad muestral, no de resultados: no se ha corrido
ningún backtest de H1 todavía.

## Por qué existiría la ventaja

- **Rotación:** 15 m son 96 velas/día (35.040/año); 1 h son 24/día (8.760/año).
  El presupuesto de fricción cae 4×. BLL (IRFA 2024) mide break-even costs de
  4,21–6,10 % en diario frente a 0,58–0,98 % en 60 m: el coste se acerca al
  bruto al bajar de frecuencia, pero 1 h sigue por encima del umbral.
- **Quién paga:** infra-reacción a la información y efecto disposición en
  tenedores de BTC (venden ganadores antes de tiempo), adopción extrapolativa
  del retail tras las subidas (BIS WP 1049: 73–81 % del retail perdió en su
  primera inversión) y longs apalancados que financian el basis. El trend
  follower cobra la continuación; el funding es un coste de implementación, no
  la fuente de la prima (BIS WP 1087).
- **Stops:** la evidencia converge en 3–4 ATR como zona robusta y en que 8–12
  ATR ya no es un stop, sino un stop de catástrofe que exige otra salida. Por
  eso H1 usa 3 ATR y sale por trailing, no por objetivo fijo.

**Límite honesto:** no hay estudio peer-reviewed de trend following BTC-only a
1 h con retorno neto y drawdown. La evidencia de frecuencias altas es
consistente en que el bruto existe y el coste decide; esta es una hipótesis
pre-registrada, no una promesa.

## Reglas exactas (congeladas)

| Campo | Regla |
|---|---|
| Instrumento | BTC spot (`BTCUSDT_SPOT`), una sola posición, sin cortos, sin pirámide |
| Marco de señal | 1 h, velas UTC agregadas desde el dataset de 5 m |
| Entrada | cierre > máximo de las `N` velas de 1 h anteriores **y** cierre > SMA(200) de 1 h |
| Ejecución | apertura de la vela siguiente (`next_open`), slippage y comisión del perfil |
| Stop inicial | entrada − `k` × ATR(14) de 1 h |
| Trailing | tras cada vela cerrada: stop = max(stop, máximo alto desde la entrada − `k_trail` × ATR(14)); nunca baja |
| Objetivo | 100 R (desactivado a efectos prácticos; la salida es el trailing) |
| Time stop | 1.000.000 de velas (desactivado) |
| Riesgo | 0,25 % del capital por operación; límites del perfil `okx` (1 posición, 4 operaciones/día, DD 2,5 %) |
| Costes | perfil `okx`: comisión 0,049 por unidad y lado, medio spread 0,07 pb, slippage 1 tick, máximo 5 ticks |
| Datos | `data/btc_5m_spot_canonical.pkl`, 718.386 velas, hash `90d33bd1…`, 2020-01-01/2026-10-31 |

La entrada es a mercado en la apertura siguiente, no limit. El motor solo tiene
`next_open` y `signal_price`; `signal_price` degrada a `next_open` cuando la vela
no cruza el precio, así que usarla habría mezclado dos ejecuciones. Se elige la
opción conservadora: pagar taker siempre. Queda declarado como desviación de la
idea original («entrada limit») antes de medir, no después.

## Universo pre-registrado (5 variantes)

| ID | N | k (stop) | k_trail | Papel |
|---|---:|---:|---:|---|
| H1-10-3 | 10 | 3,0 | 3,0 | canal corto |
| **H1-15-3** | **15** | **3,0** | **3,0** | **candidata a priori** |
| H1-20-3 | 20 | 3,0 | 3,0 | canal largo |
| H1-15-4 | 15 | 4,0 | 4,0 | stop más ancho |
| H1-15-25 | 15 | 3,0 | 2,5 | salida más ajustada |

La candidata es la del centro de la rejilla, elegida **antes** de ver resultados.
No se elige la mejor variante del ciclo: el ciclo mide el procedimiento, no
corona un ganador. No se añaden variantes después de esta fecha.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, WFA, CPCV, estrés |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una sola vez, reglas congeladas |
| Holdout | 2026-12-01 / 2027-05-31 | sellado; no se abre con este pre-registro |
| No usado | — | no queda tramo sin asignar |

## Puertas duras (las del plan, sin cambios)

| Criterio | Umbral |
|---|---:|
| Operaciones OOS | ≥ 100 |
| PF OOS | > 1,10 |
| Esperanza OOS | > 0,05 R |
| Coste ponderado | < 0,25 R |
| PBO | ≤ 0,20 |
| DSR | ≥ 0,95 |
| Estrés 2× | PF > 1,00 |
| CPCV positivos | > 50 % |
| Entradas aleatorias | p < 0,05 |
| P&L sin top-5 | > 0 |

Si falla una, H1 se archiva. No se reintenta con los mismos datos, no se cambia
el umbral y no se abre el holdout.

## Criterio de aceptación de la Fase 1

Pre-registro commiteado antes de implementar, dataset con hash, reglas y
variantes congeladas, y ninguna ejecución de backtest hasta que este documento
esté en `master`.
