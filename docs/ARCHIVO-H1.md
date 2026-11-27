# Archivo H1 — tendencia BTC spot 1 h

**Veredicto:** archivada el 2026-11-27. La validación OOS pierde en las cinco
variantes pre-registradas; no se abre el holdout ni se reajusta la regla.

## Qué se probó

Ruptura del máximo de `N` velas de 1 h con filtro SMA(200), long-only, stop
inicial de `k` ATR(14), trailing de `k_trail` ATR sobre el máximo desde la
entrada, objetivo 100 R (desactivado) y ejecución a la apertura siguiente.
Cinco variantes congeladas antes de medir: N=10/15/20 con k=3, N=15 con k=4 y
N=15 con trailing 2,5. Candidata a priori: N=15, k=3.

El marco se corrigió de 4 h a 1 h **antes de implementar** porque 4 h no llega a
100 operaciones OOS en un solo par: con N=55 y filtro SMA200 hay 31 señales
espaciadas 24 h en 2025; con N=10, 55. A 1 h hay 121-150, suficiente para el
mínimo del plan.

## Implementación

- `server/strategy/spec_driven.py`: `DonchianTrendStrategy`, long-only, filtro
  SMA200 y stop inicial ATR.
- `server/engine.py`: trailing al cierre de vela (`_update_trailing_stop`) y una
  sola evaluación por vela de señal. Antes, con ejecución de 5 m, la misma vela
  de 1 h se evaluaba doce veces y repetía la entrada.
- `tests/test_donchian_trend.py`: señal long-only, ausencia de señal sin
  ruptura, trailing que sube y no baja, y ausencia de trailing sin parámetro.
- Specs en `data/specs_h1/`, pre-registro en `docs/PRE-REGISTRO-H1.md`.

## Validación OOS (2025-01-01 / 2026-11-01, perfil OKX)

Capital 25.000 USD, riesgo 0,25 % por operación, comisión y spread del perfil,
sin cortos ni pirámide. 22 meses, una posición a la vez.

| Variante | Ops | PF | Esperanza | Acierto | DD USD | PnL USD |
|---|---:|---:|---:|---:|---:|---:|
| 1h_10_3_t3 | 215 | 0,5984 | -0,1428 R | 30,7 % | 949,64 | -830,52 |
| 1h_15_3_t25 | 247 | 0,7536 | -0,0382 R | 34,8 % | 847,07 | -548,63 |
| 1h_15_4_t4 | 182 | 0,9097 | +0,0313 R | 35,7 % | 699,45 | -290,06 |
| **1h_15_3_t3** | **227** | **0,7529** | **-0,0436 R** | **34,8 %** | **871,29** | **-545,21** |
| 1h_20_3_t3 | 209 | 0,7384 | -0,0664 R | 34,0 % | 839,34 | -599,89 |

Candidata: 227 operaciones, PF 0,7529, esperanza -0,0436 R, PnL -545,21 USD
(-2,2 %), DD 871,29 USD (3,5 %), sin topes de 5 operaciones: -1.022,89 USD.
Coste: 388,76 USD de fees, 0,0274 R por operación.

## Puertas

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 227 | pasa |
| PF OOS | > 1,10 | 0,7529 | **falla** |
| Esperanza OOS | > 0,05 R | -0,0436 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0274 R | pasa |
| P&L sin top-5 | > 0 | -1.022,89 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | puerta anterior fallida |
| DSR | ≥ 0,95 | no ejecutado | puerta anterior fallida |
| Estrés 2× | PF > 1,00 | no ejecutado | puerta anterior fallida |
| CPCV positivos | > 50 % | no ejecutado | puerta anterior fallida |
| Entradas aleatorias | p < 0,05 | no ejecutado | puerta anterior fallida |

El protocolo archiva al fallar una puerta dura; PBO/DSR/CPCV no se calcularon
porque el PF OOS ya está por debajo de 1 y la esperanza es negativa. No se
corrió el holdout.

**Corrección de medición (2026-11-27):** el `r_multiple` se calculaba contra el
stop já trailed, no contra el stop inicial; el trailing encogía el denominador
y amplificaba el R. Se corrigió en `server/execution.py` y se añadió
`tests/test_r_multiple.py`. La tabla usa el R corregido. El PF, el PnL y el
coste no cambian; la esperanza de la candidata pasó de -0,6034 R (inflada) a
-0,0436 R. La conclusión es la misma: el PF está por debajo de 1 y la cola de
ganadores es demasiado corta. La corrección no afecta al archivo SMA 15 m,
porque aquella familia no usaba trailing.

## Lectura

- **El coste no es la causa.** 0,0274 R por operación está muy por debajo del
  umbral de 0,25 R. El bruto también pierde (-156,45 USD): la señal y la salida
  no generan prima, no es que la fricción se la coma.
- **El trailing corta la cola.** La distribución de R tiene mediana -0,086 y
  máximo 2,51; sin operaciones de 5-10 R, el sistema no paga las pérdidas. Un
  trailing de 3 ATR sobre velas de 1 h devuelve el beneficio en cada rango.
- **El filtro SMA200 no salva la muestra.** A 1 h hay suficientes operaciones,
  pero la mayoría de las rupturas alineadas con la tendencia fallan; el acierto
  del 34,8 % con ganancias medias ~1 R no compensa.
- **La familia trend-following BTC-only queda cerrada.** Primero la SMA 15 m
  (604 ops, PF 0,9763) y ahora la Donchian 1 h (227 ops, PF 0,7529). Dos
  implementaciones, dos marcos y dos décadas de datos no muestran ventaja neta.

## Divulgación

La validación se observó durante el diagnóstico de implementación (lote
fraccionario y evaluación por vela), antes de la corrida formal. No fue un
tiro único: se repitió con el motor corregido y el resultado negativo se
mantuvo en las cinco variantes. El sesgo de haber mirado antes habría sido
optimista, no pesimista; aun así, H1 no pasa.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H1.md` (commits `d709e59` y anteriores).
- Specs: `data/specs_h1/`.
- Implementación: `server/strategy/spec_driven.py`, `server/engine.py`,
  `server/strategy/registry.py`, `tests/test_donchian_trend.py`.
- Conteo de validación: `data/h1_validation_counts.txt`.
