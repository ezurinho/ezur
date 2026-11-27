# Archivo H2 — carry de funding BTC (delta-neutral)

**Veredicto:** archivada el 2026-11-27 por la puerta de muestra, no por la
economía. El carry gana en OOS, pero con 4 episodios en 22 meses no hay forma
de distinguir la prima de la suerte; el plan exige ≥100 operaciones OOS y no se
relaja.

## Qué se probó

Larga spot + corta perpetuo, delta-neutral, nocional constante de 25.000 USD y
2× bruto (1× spot, 1× perpetuo). Entrada cuando la media de los últimos `W`
pagos de funding supera `umbral`; salida cuando cae por debajo de cero.
Ejecución en el siguiente pago de 8 h, al cierre de esa vela. Coste de ida y
vuelta 0,25 % (4 piernas × 5 pb + 5 pb de spread/slippage), estresado a 0,5 % y
1,0 %.

Cinco variantes pre-registradas; candidata H2-21-05 (ventana de 21 pagos, 7
días; umbral 0,005 % por 8 h, ~5,5 % anual). Pre-registro en
`docs/PRE-REGISTRO-H2.md`.

## Datos

| Serie | Fuente | Filas | SHA-256 |
|---|---|---:|---|
| Funding BTCUSDT 8 h | Binance Vision, mensual 2020-01/2026-10 | 7.488 | `35cec5b7…` |
| Perpetuo BTC-USDT-SWAP 1 h | OKX `/market/history-candles` | 59.904 | `1d0b0c67…` |
| Spot BTC 5 m | dataset canónico `90d33bd1…` | 718.386 | — |

**Límite declarado:** el funding es de Binance y los precios de OKX. En el mes
de solape (95 pagos) la correlación es 0,65 y la media difiere -0,00026 % por
8 h: el proxy es razonable pero no es el funding que se cobraría en OKX. Un test
formal en OKX necesita su historial completo, que la API pública no expone más
allá de ~1 mes.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Episodios | Neto | Anual | Funding | Basis | Costes |
|---|---:|---:|---:|---:|---:|---:|
| 9 / 0,005 % | 31 | +60,7 % | 12,14 % | 17.114,91 | 7,97 | 1.937,50 |
| **21 / 0,005 %** | **14** | **+64,9 %** | **12,97 %** | **16.936,61** | **154,11** | **875,00** |
| 63 / 0,005 % | 6 | +64,1 % | 12,82 % | 16.443,12 | -38,81 | 375,00 |
| 21 / 0,010 % | 7 | +61,1 % | 12,21 % | 15.713,50 | -1,15 | 437,50 |
| 9 / 0,0025 % | 39 | +59,7 % | 11,93 % | 17.292,05 | 61,88 | 2.437,50 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Episodios | Neto | Anual | Funding | Basis | Costes |
|---|---:|---:|---:|---:|---:|---:|
| 9 / 0,005 % | 7 | +5,32 % | 2,91 % | 1.756,51 | 11,92 | 437,50 |
| **21 / 0,005 %** | **4** | **+4,30 %** | **2,35 %** | **1.320,06** | **5,92** | **250,00** |
| 63 / 0,005 % | 1 | +4,78 % | 2,61 % | 1.247,04 | 9,81 | 62,50 |
| 21 / 0,010 % | 0 | 0,00 % | 0,00 % | 0,00 | 0,00 | 0,00 |
| 9 / 0,0025 % | 11 | +4,88 % | 2,66 % | 1.879,08 | 28,10 | 687,50 |

Candidata: 4 episodios, 3 ganadores, +1.075,98 USD (+4,30 %), 2,35 % anual,
95,5 días de media. Estrés de costes: 0,5 % → +3,30 % (1,81 % anual); 1,0 % →
+1,30 % (0,71 % anual). Bootstrap de episodios (10.000 remuestreos): neto
+4,30 %, IC80 [1,85 %, 6,75 %], p(neto ≤ 0) = 0,005. La prima es positiva, pero
la muestra es minúscula y el retorno OOS es inferior a una letra del Tesoro.

## Puertas

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 4 | **falla** |
| PF OOS | > 1,10 | 34,33 | pasa (degenerado: 3 ganadores y 1 perdedor) |
| Esperanza OOS | > 0,05 R | +0,7173 R | pasa con R = 1,5 % del nocional (declarado) |
| Coste ponderado | < 0,25 R | 0,1667 R | pasa |
| P&L sin top-5 | > 0 | 0,00 | **falla** (4 episodios: quitar 5 lo deja vacío) |
| PBO | ≤ 0,20 | no ejecutado | puerta de muestra fallida |
| DSR | ≥ 0,95 | no ejecutado | puerta de muestra fallida |
| Estrés 2× | PF > 1,00 | neto +1,81 % anual | pasa en neto, PF degenerado |
| CPCV positivos | > 50 % | no ejecutado | puerta de muestra fallida |
| Entradas aleatorias | p < 0,05 | no ejecutado | puerta de muestra fallida |

## Lectura

- **La prima existe.** El funding medio de 2020-2026 es 0,0106 % por 8 h
  (11,6 % anual) y el 86 % de los pagos son positivos. El carry cobra esa renta
  sin dirección; el basis aporta poco (±154 USD en 5 años).
- **El retorno OOS es demasiado fino.** 2,35 % anual antes de impuestos y con
  un solo venue no compensa el riesgo operativo (margen, liquidación del
  perpetuo, cambio de reglas, retiradas). A 2× costes queda en 1,81 % anual.
- **La muestra no permite concluir.** 4 episodios no son una muestra; el PF de
  34 es un artefacto de tener un solo perdedor. La puerta de 100 operaciones
  existe precisamente para no confundir una prima con una racha.
- **El marco de puertas no encaja con baja rotación.** Un carry que permanece
  meses invierte no puede producir 100 operaciones en 22 meses. Si se quiere
  estudiar carry en serio, hace falta una puerta propia (episodios ≥ 30,
  histórico ≥ 5 años, neto > letra del Tesoro + 2 %, concentración top-5) y un
  historial de funding de OKX, no un proxy de Binance. Eso es un cambio de plan
  y no se aplica sin autorización.

## Divulgación

Antes de congelar las reglas se midió la distribución del funding y se probaron
ventanas/umbrales (estudio de viabilidad). El umbral 0,005 % y la ventana 21
salieron de ese estudio, no de una conjetura pura. La validación 2025-2026 es
OOS para la regla congelada, pero no es un experimento prístino: el sesgo sería
optimista y aun así el retorno es 2,35 % anual.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H2.md`.
- Simulador: `server/carry.py`; pruebas: `tests/test_carry.py`.
- Salidas: `data/h2_dev.txt`, `data/h2_val.txt`.
- Freeze: `data/BTC-USDT-SWAP_1h.freeze.json`,
  `data/funding/BTCUSDT_funding_binance.freeze.json`.
