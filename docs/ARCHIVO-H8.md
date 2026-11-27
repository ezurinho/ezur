# Archivo H8 — spread de funding entre venues

**Veredicto:** archivada el 2026-11-27, el mismo día de la medida. La candidata
gana en OOS, pero **no pasa la puerta de muestra ni la de esperanza**: 17
episodios (34 operaciones) y 0,0094 R, frente a 100 operaciones y 0,05 R. El
spread existe, pero en 2025-2026 es demasiado raro y demasiado pequeño después de
costes. No se abre el holdout.

## Qué se probó

BTC, ETH, SOL, XRP y DOGE; el mismo activo en **Binance USD-M y Hyperliquid**.
Funding diario sumado por venue (8 h en Binance, 1 h en Hyperliquid), precios de
cierre de cada venue, señal con la media de 7 o 30 días hasta t-1, ejecución al
cierre t. Largo en el venue barato, corto en el caro, delta-neutral, 25.000 USD de
bruto (5.000 por activo; 2.500 por pata). Salida con spread < 3 %, cambio de par
extremo o 28 días. Coste 7 pb por pata y lado (6 pb taker/slippage + 1 pb
transferencia/colateral). Cinco variantes; candidata **H8-S7-W-12**.

**Datos:** 168.144 eventos de funding, 12.653 filas diarias y 12.690 cierres,
2023-05-12/2026-10-31. SHA-256 funding `6dec74d1…`, precios `e594cd7e…`, eventos
`1169e72f…`. OKX se excluyó antes de medir porque su API pública solo conserva 67
días; Bybit está bloqueado por región. El panel final es Binance + Hyperliquid.

## Desarrollo (2023-07-01 / 2025-01-01, 1,5 años)

| Variante | Episodios | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **S7-W-12** | 63 | 126 | +6,29 % | 17,52 | 0,0485 R | −0,13 % | +43,63 | +1.924,07 | +1.015,00 |
| S30-W-12 | 51 | 102 | +5,06 % | 11,64 | 0,0484 R | −0,20 % | −29,92 | +1.621,21 | +760,87 |
| S7-D-12 | 78 | 156 | +7,53 % | 22,24 | 0,0465 R | −0,13 % | +26,64 | +2.334,73 | +1.285,71 |
| S7-W-8 | 75 | 150 | +6,58 % | 11,61 | 0,0425 R | −0,18 % | +51,97 | +2.067,18 | +1.078,43 |
| BTC-W-12 | 14 | 28 | +4,16 % | 17,51 | 0,1455 R | −0,36 % | +41,63 | +1.467,14 | +237,76 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Episodios | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **S7-W-12** | **17** | **34** | **+0,32 %** | **10,46** | **0,0094 R** | −0,07 % | +19,20 | +179,90 | +18,85 |
| S30-W-12 | 8 | 16 | +0,14 % | 3,93 | 0,0087 R | −0,10 % | +7,48 | +83,15 | −7,94 |
| S7-D-12 | 26 | 52 | +0,35 % | 2,71 | 0,0066 R | −0,13 % | +23,45 | +244,83 | +11,83 |
| S7-W-8 | 44 | 88 | +0,26 % | 1,55 | 0,0030 R | −0,23 % | +2,96 | +371,14 | −15,16 |
| BTC-W-12 | 3 | 6 | +0,31 % | sin perdedores | 0,0513 R | −0,20 % | +4,37 | +177,61 | −0,03 |

La candidata tiene 14 ganadoras y 3 perdedoras. Todas las entradas son largas en
Binance y cortas en Hyperliquid, salvo dos reversiones (XRP abril 2025 y DOGE
octubre 2025). El spread de entrada va de 12,2 % a 41,7 % anualizado.

## Puertas (candidata S7-W-12)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 34 | **falla** |
| PF OOS | > 1,10 | 10,46 | pasa |
| Esperanza OOS | > 0,05 R | 0,0094 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0140 R | pasa |
| P&L sin top-5 | > 0 | +18,85 | pasa |
| PBO | ≤ 0,20 | no ejecutado | la muestra ya falla |
| DSR | ≥ 0,95 | no ejecutado | la muestra ya falla |
| Estrés 2× | PF > 1,00 | no ejecutado | la muestra ya falla |
| CPCV / aleatorias | — | no ejecutado | la muestra ya falla |

No se ejecutaron PBO, DSR, estrés, CPCV ni aleatorias: la puerta de muestra y la
de esperanza fallan antes. No se bajó el umbral ni se añadieron variantes para
rescatarla.

## Lectura

- **El spread de Hyperliquid existe, pero no escala.** En desarrollo había 63
  episodios; en 2025-2026 solo 17. La compresión que anticipaba Talos es real:
  el 12 % anualizado se cruza pocas veces y, cuando se cruza, el funding neto es
  de unos 10 USD por episodio.
- **El coste se come casi todo:** +179,90 USD de funding y +19,20 de precio
  contra 119 USD de costes. El neto es +80,17 USD en 1,83 años, un 0,18 % anual.
  Es positivo, pero no es una prima explotable a este tamaño.
- **Bajar el umbral a 8 % no arregla nada:** duplica los episodios (44) pero la
  esperanza cae a 0,0030 R y el P&L sin top-5 es negativo. El diario tampoco: 26
  episodios, 0,0066 R. No se prueba un 5 % ni un 6 %.
- **La variante BTC-only no tiene muestra:** 3 episodios y 6 operaciones. Su
  esperanza alta es ruido de tres operaciones.
- **El PF alto es engañoso:** 14 ganadoras y 3 perdedoras con beneficios medios
  minúsculos. El PF no mide la falta de oportunidades; la puerta de muestra sí.
- **No es un problema de precio:** el P&L de precio es +19,20 USD; el funding es
  la fuente, pero su magnitud no compensa la fricción y la baja frecuencia.
- **El holdout sigue sellado.** No se usó 2026-11-01/2027-05-31.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H8.md`.
- Revisión de diseño: `docs/REVISION-DISENO-H8.md`.
- Simulador: `server/funding_spread.py`; pruebas: `tests/test_funding_spread.py`.
- Datos: `data/funding_spread/` con `freeze.json` y hashes.
- Salidas: `data/h8_dev.txt`, `data/h8_val.txt`.
- Siguiente: H9 (basis spot-perp) según `docs/PLAN-2027.md`; no se mide en esta
  sesión.
