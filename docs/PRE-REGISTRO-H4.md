# Pre-registro H4 — reversión de pares spot contra BTC

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** cuando un altcoin se desvía mucho de su relación histórica con
BTC, el spread revierte; un long-short dollar-neutral entre las dos patas cobra
esa reversión después de costes.

## Por qué existiría la ventaja

Los pares spot contra BTC comparten el factor mercado; lo que fluctúa es la
relación relativa. Si el flujo de un alt concreto lo empuja fuera de su rango
(rotación sectorial, listados, noticias), el market maker que toma el otro lado
exige una prima por liquidez y el spread vuelve. No es arbitraje: la relación
puede cambiar de régimen y el stop temporal es la única protección.

**Datos nuevos:** 6 pares spot de Binance (ETHBTC, BNBBTC, ADABTC, LINKBTC,
LTCBTC, XRPBTC), 10.962 cierres diarios 2020-01-01/2026-10-31, SHA-256
`52c9c96b…` (corrección de parseo: los ficheros de 2025 traen microsegundos). No se usa el panel de perpetuos de H3 ni el dataset de BTC de
H1/H2. Sesgo de supervivencia declarado: los pares se eligen por liquidez de
2026, aunque todos existían en 2020.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo | 6 pares spot contra BTC |
| Señal | z-score del logaritmo del precio del par contra su media y desviación de `L` días |
| Entrada | `|z| > umbral`: si z>0, corto el alt y largo BTC; si z<0, al revés |
| Salida | `|z| < 0,5` o 30 días naturales desde la entrada |
| Cartera | 6 pares, capital repartido; cada par dollar-neutral, 2.083 USD por pata |
| Exposición | 25.000 USD de bruto total (1× capital), neto 0 |
| Ejecución | al cierre del día siguiente a la señal, nunca con el precio de la señal |
| Costes | 7 pb por pata y lado: 5 pb taker + 2 pb slippage |
| Funding | no aplica: las dos patas son spot |
| Capital | 25.000 USD; sin apalancamiento adicional |

## Universo pre-registrado (5 variantes)

| ID | L (días) | Umbral | Papel |
|---|---:|---:|---|
| H4-20-2 | 20 | 2,0 | ventana corta |
| **H4-30-2** | **30** | **2,0** | **candidata a priori** |
| H4-60-2 | 60 | 2,0 | ventana larga |
| H4-30-15 | 30 | 1,5 | más entradas |
| H4-30-25 | 30 | 2,5 | menos entradas |

La candidata H4-30-2 usa el z-score clásico de 30 días y 2 desviaciones; no se
eligió por resultado, sino por ser el estándar de reversión de spreads.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez, reglas congeladas |
| Holdout | 2026-12-01 / 2027-05-31 | sellado |

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

**Operación:** cada pata abierta o cerrada cuenta; una vuelta completa son 4
operaciones. Con ~108 episodios OOS (6 pares) son ~432 operaciones.
**R:** 1 % del capital (250 USD) por operación, declarado porque la cartera no
tiene stop por operación.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, ninguna ejecución de backtest hasta cerrar este documento.
El simulador es determinista y separado del motor de órdenes.
