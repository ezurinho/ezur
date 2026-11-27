# Archivo H6 — TSMOM long-only en 20 perpetuos

**Veredicto:** archivada el 2026-11-27. La candidata pierde -40,8 % en OOS
frente a -18,0 % de BTC, con peor drawdown (-68,7 % vs -53,0 %). Las variantes
60/90 baten a BTC en neto, pero con peor drawdown y P&L sin top-5 negativo. Es
beta de alts, no una ventaja independiente.

## Qué se probó

20 perpetuos USD-M, cierres diarios 2020-2026 (47.255 filas, SHA-256
`53c169aa…`). Señal de retorno de `L` días al cierre del lunes; entrada al
cierre del martes solo si la señal es positiva; equal-weight o inverso a
volatilidad; rebalanceo semanal o bisemanal; 7 pb por posición y lado. Cinco
variantes; candidata H6-28-EW. Puerta adicional pre-registrada: batir a BTC
buy-and-hold en neto **y** en drawdown.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Episodios | Neto | PF | Esperanza | DD | Top-5 |
|---|---:|---:|---:|---:|---:|---:|
| **28-EW** | 512 | +14.802,74 % | 3,3898 | 0,7337 R | -89,22 % | +3.640.042 |
| 60-EW | 359 | +2.175,16 % | 3,0854 | 0,9644 R | -93,23 % | +477.970 |
| 90-EW | 292 | +16.003,28 % | 4,4434 | 1,4020 R | -87,88 % | +3.918.435 |
| 28-IV | 512 | +33.155,60 % | 3,8669 | 0,8602 R | -90,59 % | +8.198.129 |
| 28-BI | 384 | +3.181,97 % | 2,7599 | 0,6646 R | -88,35 % | +757.136 |
| BTC B&H | — | +1.199,73 % | — | — | -76,67 % | — |

El desarrollo es un artefacto de beta: una cesta equal-weight de 20 alts en
2020-2021 multiplica el capital con drawdowns del 90 %. No es una ventaja
estable; es el mercado con más volatilidad.

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Ops | Neto | PF | Esperanza | DD | Top-5 |
|---|---:|---:|---:|---:|---:|---:|
| **28-EW** | 384 | **-40,84 %** | 0,8766 | -0,0497 R | -68,72 % | -22.364,94 |
| 60-EW | 246 | +0,13 % | 1,4720 | 0,1957 R | -61,72 % | -20.400,17 |
| 90-EW | 200 | -21,31 % | 1,3230 | 0,1761 R | -73,04 % | -25.158,07 |
| 28-IV | 384 | -33,77 % | 0,8971 | -0,0359 R | -61,96 % | -18.136,01 |
| 28-BI | 292 | -60,43 % | 0,6240 | -0,2063 R | -75,08 % | -26.466,97 |
| **BTC B&H** | — | **-18,04 %** | — | — | **-52,98 %** | — |

## Puertas (candidata 28-EW)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 384 | pasa |
| PF OOS | > 1,10 | 0,8766 | **falla** |
| Esperanza OOS | > 0,05 R | -0,0497 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0090 R | pasa |
| P&L sin top-5 | > 0 | -22.364,94 | **falla** |
| Neto > BTC B&H | sí | -40,84 % vs -18,04 % | **falla** |
| DD < DD de BTC | sí | -68,72 % vs -52,98 % | **falla** |
| PBO / DSR / estrés / CPCV / aleatorias | — | no ejecutado | la candidata ya falla |

## La mejor variante no basta

H6-60-EW es la única que bate a BTC en neto (+0,13 % vs -18,04 %) y pasa PF,
esperanza y coste. Pero su drawdown es **peor** que el de BTC (-61,72 % vs
-52,98 %), su P&L sin las cinco mejores operaciones es **-20.400,17** y no se
ejecutaron DSR ni PBO porque la puerta de drawdown ya la elimina. Batir a BTC
en un bear market quedándose con más riesgo no es una ventaja.

## Lectura

- El TSMOM long-only funciona en el papel porque compra beta de alts en un
  mercado alcista; en OOS 2025-2026 esa beta fue negativa y el resultado también.
- La evidencia de Han et al. (Sharpe 1,51 neto) usa una cesta amplia de todas
  las monedas líquidas y 2013-2023; no se replica con 20 majors en 2025-2026.
- La puerta de benchmark hizo su trabajo: sin ella, el +14.802 % de desarrollo
  habría parecido una estrategia ganadora.
- La pata corta no se probó aquí; H3 ya mostró que el momentum cross-sectional
  pierde en OOS y que la pata corta es la que sufre.

## Nulidad por permutación (2026-11-27)

`python scripts/permutation_families.py --family H6` baraja los retornos diarios
de cada símbolo y reconstruye el precio (50 permutaciones, semilla 20261127): la
tendencia desaparece y la distribución marginal se conserva.

| | Esperanza |
|---|---:|
| Observado (28-EW) | −0,0497 R |
| Nulidad, mediana | −0,1292 R |
| Nulidad, p5 / p95 | −0,2161 / −0,0230 R |

El observado es **menos malo que el 90 % de las permutaciones** (p de dos colas
0,90 sobre el valor absoluto, que aquí engaña: la nulidad no está centrada en
cero). La lectura no es «es ruido», sino la que ya daba la etiqueta: la señal de
tendencia evita parte de la caída de las alts en 2025-2026 —una entrada al azar
habría perdido unos 0,08 R más por episodio— y aun así pierde 40,8 %. Manda la
beta, el timing sólo la mitiga, y no compensa coste ni beta negativa. Veredicto
sin cambios.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H6.md`.
- Simulador: `server/tsmom.py`; pruebas: `tests/test_tsmom.py`.
- Datos: `data/funding_xs/perp_1d_panel.csv` (hash `53c169aa…`).
- Salidas: `data/h6_dev.txt`, `data/h6_val.txt`.
