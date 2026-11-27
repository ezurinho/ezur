# Pre-registro H1 — tendencia BTC spot 4 h

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar y antes de ejecutar cualquier backtest.
**Hipótesis:** el trend following en BTC spot a 4 h conserva una ventaja neta
después de costes porque reduce la rotación ~24× frente a 15 m sin perder la
señal de tendencia. Si falla una puerta dura, H1 se archiva y no se reajusta.

## Por qué existiría la ventaja

- **Rotación:** 15 m son 96 velas/día (35.040/año); 4 h son 6/día (2.190/año).
  El presupuesto de fricción cae con la frecuencia. BLL (IRFA 2024) mide
  break-even costs de 4,21–6,10 % en diario frente a 0,44–0,98 % en 60 m y
  0,29–0,83 % en 10 m: cuanto más corto el marco, más cerca está el coste de
  comerse el bruto. Khan (SSRN 7573918, preprint 2026) sitúa la frontera de
  rentabilidad entre 1 h y 4 h, y encuentra que 5 m no es rentable ni con coste
  casi nulo.
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
4 h con retorno neto y drawdown. El resultado H4 más cercano es un preprint
sobre 150+ perpetuos (Sharpe 2,08, MDD −15,6 %, 213 operaciones/mes), que sirve
como orden de magnitud, no como expectativa. Esta es una hipótesis pre-registrada,
no una promesa.

## Reglas exactas (congeladas)

| Campo | Regla |
|---|---|
| Instrumento | BTC spot (`BTCUSDT_SPOT`), una sola posición, sin cortos, sin pirámide |
| Marco de señal | 4 h, velas UTC agregadas desde el dataset de 5 m |
| Entrada | cierre > máximo de las `N` velas de 4 h anteriores **y** cierre > SMA(200) de 4 h |
| Ejecución | apertura de la vela siguiente (`next_open`), slippage y comisión del perfil |
| Stop inicial | entrada − `k` × ATR(14) de 4 h |
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
| H1-40-3 | 40 | 3,0 | 3,0 | variante de canal corto |
| **H1-55-3** | **55** | **3,0** | **3,0** | **candidata a priori** |
| H1-70-3 | 70 | 3,0 | 3,0 | variante de canal largo |
| H1-55-4 | 55 | 4,0 | 4,0 | stop más ancho |
| H1-55-25 | 55 | 3,0 | 2,5 | salida más ajustada |

La candidata es la del centro de la rejilla, elegida **antes** de ver resultados.
No se elige la mejor variante del ciclo: el ciclo mide el procedimiento, no
corona un ganador. No se añaden variantes después de esta fecha.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, WFA, CPCV, estrés |
| Validación | 2025-01-01 / 2026-01-01 | OOS real, una sola vez, reglas congeladas |
| Holdout | 2026-12-01 / 2027-05-31 | sellado; no se abre con este pre-registro |
| No usado | 2026-01-01 / 2026-10-31 | fuera de desarrollo y validación |

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
