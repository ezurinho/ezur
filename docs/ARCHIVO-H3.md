# Archivo H3 — momentum cross-sectional en perpetuos

**Veredicto:** archivada el 2026-11-27. La candidata pierde -30,9 % en la
validación OOS (PF 0,70); el beneficio de desarrollo dependía de cinco periodos
y no sobrevive al cambio de régimen.

## Qué se probó

Panel de 7 perpetuos USDT (BTC, ETH, BNB, XRP, ADA, LTC, LINK), 17.363 cierres
diarios 2020-2026 (SHA-256 `c31a916a…`). En cada rebalanceo, largo los 2 activos
con mejor retorno de los últimos `L` días y corto los 2 peores, equiponderados,
dollar-neutral, 1× bruto (12,5 % por pata). Ejecución al cierre del día
siguiente, coste 7 pb por pata y lado (5 pb taker + 2 pb slippage). Cinco
variantes pre-registradas; candidata H3-28-7.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Periodos | Ops | Neto | CAGR | PF | DD | P&L sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 14/7 | 257 | 2.056 | +162,78 % | 21,31 % | 1,3523 | -53,76 % | +14.297,91 |
| **28/7** | **255** | **2.040** | **+31,65 %** | **5,65 %** | **1,1449** | **-56,79 %** | **-16.586,61** |
| 56/7 | 251 | 2.008 | -18,43 % | -3,99 % | 1,0233 | -67,84 % | -28.987,83 |
| 28/14 | 127 | 1.016 | +65,32 % | 10,57 % | 1,3174 | -52,33 % | -18.603,24 |
| 28/7/3 | 252 | 3.024 | +54,06 % | 9,02 % | 1,1991 | -32,48 % | -3.121,35 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Periodos | Ops | Neto | CAGR | PF | DD | P&L sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 14/7 | 93 | 744 | +0,79 % | 0,43 % | 1,0468 | -27,49 % | -7.528,49 |
| **28/7** | **91** | **728** | **-30,92 %** | **-18,29 %** | **0,7046** | **-35,05 %** | **-13.417,41** |
| 56/7 | 87 | 696 | -28,96 % | -17,03 % | 0,6792 | -31,40 % | -12.530,62 |
| 28/14 | 46 | 368 | -43,02 % | -26,44 % | 0,4737 | -46,10 % | -16.311,45 |
| 28/7/3 | 91 | 1.092 | -22,21 % | -12,81 % | 0,7394 | -28,00 % | -10.084,35 |

## Puertas (candidata)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 728 | pasa |
| PF OOS | > 1,10 | 0,7046 | **falla** |
| Esperanza OOS | > 0,05 R | -0,0447 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0063 R | pasa |
| P&L sin top-5 | > 0 | -13.417,41 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | PF OOS ya falla |
| DSR | ≥ 0,95 | no ejecutado | PF OOS ya falla |
| Estrés 2× | PF > 1,00 | no ejecutado | PF OOS ya falla |
| CPCV positivos | > 50 % | no ejecutado | PF OOS ya falla |
| Entradas aleatorias | p < 0,05 | no ejecutado | PF OOS ya falla |

## Lectura

- **El momentum cripto se agotó.** El desarrollo 2020-2024 era +5,65 % anual con
  DD -57 % y todo el P&L en cinco periodos; en 2025-2026 el long-short pierde
  -30,9 %. El régimen de alt-season de 2020-2021 no se repitió.
- **La rotación no es el problema.** El coste es 0,0063 R por operación, muy por
  debajo de 0,25 R; el bruto ya es negativo en OOS. No es fricción, es señal.
- **La concentración lo delata.** Quitar los cinco mejores periodos deja el
  desarrollo en -16.586 USD: la "ventaja" eran cinco rachas, no una prima
  estable. La variante 14/7 es la única que no pierde en OOS, pero su PF 1,047
  no llega a 1,10 y su P&L sin top-5 es -7.528.
- **Sesgos declarados:** universo elegido por liquidez de 2020 (supervivencia),
  funding no modelado y ejecución al cierre del día siguiente. Los tres
  empujarían el resultado hacia arriba, no hacia abajo.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H3.md`.
- Simulador: `server/momentum.py`; pruebas: `tests/test_momentum.py`.
- Panel: `data/momentum/perp_1d_panel.csv` (hash `c31a916a…`).
- Salidas: `data/h3_dev.txt`, `data/h3_val.txt`.
