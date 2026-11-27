# Archivo H7 — desequilibrio de flujo de taker

**Veredicto:** archivada el 2026-11-27, el mismo día de la medida. La candidata
pierde -27,33 % en OOS (PF 0,9355, esperanza -0,0111 R); el +328,7 % de
desarrollo no sobrevivió al cambio de régimen. Ninguna variante pasa las
puertas.

## Qué se probó

20 perpetuos USD-M, 47.255 barras diarias con volumen y `taker_buy_base`
(2020-2026, SHA-256 `baa1a7bd…`). Flujo = compra agresiva / volumen; z-score de
20 días; media de 3 z; señal al cierre t-1; ejecución al cierre t; quintiles
dollar-neutral; rebalanceo cada 3 días; 6 pb por posición y lado; funding
incluido. Cinco variantes; candidata H7-Z20-3D.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Episodios | Neto | PF | Esperanza | DD | Precio | Funding | Top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Z20-3D** | 3.138 | +328,71 % | 1,1080 | 0,0263 R | -45,79 % | +52.236 | +1.842 | +61.871 |
| Z5-1D | 10.483 | -92,13 % | 0,9269 | -0,0107 R | -93,54 % | -14.178 | +653 | -46.503 |
| Z60-3D | 2.856 | +174,16 % | 1,0868 | 0,0213 R | -31,02 % | +38.910 | +3.179 | +23.718 |
| Z20-3D-T | 4.502 | +124,64 % | 1,0698 | 0,0111 R | -35,85 % | +33.955 | +1.554 | +18.130 |
| BTC-TS | 71 | +41,59 % | 1,4704 | 0,3079 R | -22,67 % | +13.939 | -878 | -5.564 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Z20-3D** | 2.652 | **-27,33 %** | 0,9355 | -0,0111 R | -35,85 % | -2.224 | -140 | -11.152 |
| Z5-1D | 8.540 | -64,21 % | 0,8867 | -0,0116 R | -66,15 % | -8.817 | +12 | -19.772 |
| Z60-3D | 2.412 | -27,97 % | 0,9291 | -0,0124 R | -32,82 % | -3.025 | +44 | -12.638 |
| Z20-3D-T | 3.738 | -0,17 % | 1,0042 | 0,0004 R | -19,83 % | +4.536 | -92 | -6.262 |
| BTC-TS | 52 | -5,69 % | 0,8110 | -0,0991 R | -17,48 % | -395 | -113 | -5.220 |

## Puertas (candidata Z20-3D)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 2.652 | pasa |
| PF OOS | > 1,10 | 0,9355 | **falla** |
| Esperanza OOS | > 0,05 R | -0,0111 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0075 R | pasa |
| P&L sin top-5 | > 0 | -11.152,13 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | PF OOS ya falla |
| DSR | ≥ 0,95 | no ejecutado | PF OOS ya falla |
| Estrés 2× | PF > 1,00 | no ejecutado | PF OOS ya falla |
| CPCV / entradas aleatorias | — | no ejecutado | PF OOS ya falla |

## Lectura

- **El flujo de taker no paga a 3 días en 20 majors.** El desarrollo captura
  2020-2021, cuando el flujo agresivo precedía a subidas fuertes; en 2025-2026
  el signo se invierte y la cartera dollar-neutral pierde.
- **El coste no es la causa:** 0,0075 R por operación, el bruto ya es negativo
  (-2.224 USD de precio y -140 de funding).
- **La variante de terciles es la única que no pierde** (-0,17 %, PF 1,0042),
  pero tampoco gana: es ruido, no una ventaja.
- **BTC-TS no tiene muestra:** 52 operaciones OOS, por debajo de 100, y además
  PF 0,8110.
- **La literatura lo anticipaba:** el poder predictivo del order flow es real,
  pero a frecuencias altas el edge es del orden del coste; a 3 días se desvanece
  o se invierte.

## Nulidad por permutación (2026-11-27)

`python scripts/permutation_families.py --family H7` baraja el ratio de flujo de
cada símbolo en el tiempo (50 permutaciones, semilla 20261127); precios, volumen
y funding quedan reales.

| | Esperanza |
|---|---:|
| Observado (Z20-3D) | −0,0111 R |
| Nulidad, mediana | −0,0089 R |
| Nulidad, p5 / p95 | −0,0230 / +0,0032 R |

p de dos colas 0,37; el observado cae en el 64 % de la distribución nula. **El
resultado de H7 no se distingue del ruido.** Eso no lo absuelve: la candidata se
archiva porque no tiene edge que desplegar —PF 0,9355, esperanza negativa y
ninguna de las cinco variantes por encima de 1,10—, no porque se haya demostrado
que el flujo destruya dinero. Con 1.326 episodios la estimación es precisa; lo
que no hay es señal, y a 3 días el edge del order flow es del orden del coste.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H7.md`.
- Simulador: `server/taker_flow.py`; pruebas: `tests/test_taker_flow.py`.
- Datos: `data/flow/taker_flow_1d.csv` (hash `baa1a7bd…`).
- Salidas: `data/h7_dev.txt`, `data/h7_val.txt`.
