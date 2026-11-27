# Archivo H4 — reversión de pares spot contra BTC

**Veredicto:** archivada el 2026-11-27. Las cinco variantes pierden en OOS
(PF 0,87-0,95); los spreads contra BTC no revierten a 30 días, tienden.

## Qué se probó

6 pares spot (ETHBTC, BNBBTC, ADABTC, LINKBTC, LTCBTC, XRPBTC), 14.976 cierres
diarios 2020-2026 (SHA-256 `52c9c96b…`). z-score del logaritmo del par contra su
media/desviación de `L` días; entrada con `|z| > umbral`, salida con `|z| < 0,5`
o 30 días; dollar-neutral, 25.000 USD de bruto repartido, ejecución al cierre
del día siguiente, 7 pb por pata y lado. Cinco variantes; candidata H4-30-2.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Episodios | Ops | Neto | CAGR | PF | DD | P&L sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20/2,0 | 367 | 1.468 | -55,18 % | -14,82 % | 0,5895 | -57,23 % | -20.362,80 |
| **30/2,0** | **307** | **1.228** | **-48,11 %** | **-12,29 %** | **0,5739** | **-51,25 %** | **-16.571,73** |
| 60/2,0 | 192 | 768 | -36,45 % | -8,66 % | 0,6253 | -42,09 % | -12.029,87 |
| 30/1,5 | 426 | 1.704 | -57,05 % | -15,55 % | 0,5941 | -59,15 % | -18.898,86 |
| 30/2,5 | 188 | 752 | -47,00 % | -11,92 % | 0,4678 | -49,27 % | -14.959,45 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Episodios | Ops | Neto | CAGR | PF | DD | P&L sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20/2,0 | 144 | 576 | -3,90 % | -2,15 % | 0,8848 | -14,19 % | -2.413,48 |
| **30/2,0** | **111** | **444** | **-2,75 %** | **-1,51 %** | **0,9235** | **-15,02 %** | **-1.856,74** |
| 60/2,0 | 66 | 264 | -2,60 % | -1,43 % | 0,8940 | -10,43 % | -2.367,65 |
| 30/1,5 | 168 | 672 | -2,97 % | -1,63 % | 0,9496 | -18,17 % | -2.407,74 |
| 30/2,5 | 68 | 272 | -2,76 % | -1,52 % | 0,8708 | -13,77 % | -1.789,00 |

## Puertas (candidata)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 444 | pasa |
| PF OOS | > 1,10 | 0,9235 | **falla** |
| Esperanza OOS | > 0,05 R | -0,0044 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0058 R | pasa |
| P&L sin top-5 | > 0 | -1.856,74 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | PF OOS ya falla |
| DSR | ≥ 0,95 | no ejecutado | PF OOS ya falla |
| Estrés 2× | PF > 1,00 | no ejecutado | PF OOS ya falla |
| CPCV positivos | > 50 % | no ejecutado | PF OOS ya falla |
| Entradas aleatorias | p < 0,05 | no ejecutado | PF OOS ya falla |

## Lectura

- **No hay reversión a 30 días.** El spread contra BTC sigue su tendencia; el
  z-score de 2 desviaciones no marca un exceso que vuelva, marca el comienzo de
  una rotación. Es consistente con H3: en este periodo el momentum relativo
  funciona mejor que la reversión, y aun así H3 perdió en OOS.
- **El coste no explica nada.** 0,0058 R por operación; el bruto ya es negativo.
- **La pérdida de desarrollo es grande** (-48 % con DD -51 %), así que no es un
  caso de "casi": la regla estaba mal en el periodo de diseño, no solo fuera de
  muestra.
- **Sesgos:** supervivencia de los pares, ejecución al cierre diario, ausencia
  de funding (las dos patas son spot, así que no aplica). Los tres empujarían el
  resultado hacia arriba, no hacia abajo.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H4.md`.
- Simulador: `server/pairs.py`; pruebas: `tests/test_pairs.py`.
- Panel: `data/pairs/spot_pairs_1d.csv` (hash `52c9c96b…`).
- Salidas: `data/h4_dev.txt`, `data/h4_val.txt`.
