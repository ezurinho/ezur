# Archivo H9 — basis spot-perp (cash-and-carry)

**Veredicto:** archivada el 2026-11-27, el mismo día de la medida. La candidata
pierde -0,21 % en OOS con PF 0,1356 y -0,0047 R, y solo tiene 22 episodios
(44 operaciones). **Fallan muestra, PF, esperanza y P&L sin top-5.** Las cinco
variantes pierden en validación. El basis de 2025-2026 es demasiado pequeño
frente a los 28 pb de coste de ida y vuelta. No se abre el holdout.

## Qué se probó

20 alts de Binance (BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX, LINK, DOT, LTC,
BCH, TRX, ATOM, NEAR, ETC, FIL, UNI, AAVE, SAND). Para cada uno: basis diario
`perp/spot - 1`, funding diario y score = media de 7 o 30 días de ambos, con datos
hasta t-1. Si el score supera 2,5 pb/día y el activo está en el quintil superior,
se compra spot y se vende el perpetuo con el mismo notional (3.125 USD por pata,
4 posiciones). Salida con score < 1 pb/día, caída fuera del 40 % superior o 28
días. Coste 7 pb por pata y lado. La variante de sensibilidad baja la entrada a
1 pb/día y la salida a 0,5 pb/día.

**Datos:** 20 activos × 1.269 días, 2023-05-12/2026-10-31. 25.380 filas en cada
panel (spot, perpetuo y funding). SHA-256 spot `35f2699e…`, perpetuo
`e3cc492d…`, funding `63123020…`. Spot de Binance Vision verificado contra el
`.CHECKSUM` mensual; perpetuo y funding del panel H5. El holdout no se descargó.

## Desarrollo (2023-07-01 / 2025-01-01, 1,5 años)

| Variante | Episodios | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **C7-Q20-W-25** | 67 | 134 | +4,78 % | 8,24 | 0,0349 R | −0,40 % | +22,53 | +1.732,60 | +722,54 |
| C30-Q20-W-25 | 39 | 78 | +5,54 % | 35,82 | 0,0692 R | −0,15 % | +27,24 | +1.663,62 | +871,76 |
| C7-Q20-D-25 | 100 | 200 | +4,22 % | 5,33 | 0,0207 R | −0,49 % | +56,78 | +1.853,02 | +640,44 |
| C7-Q10-W-25 | 40 | 80 | +4,48 % | 5,59 | 0,0549 R | −0,63 % | +45,50 | +1.752,10 | +371,10 |
| C7-Q20-W-10 | 74 | 148 | +4,84 % | 7,19 | 0,0319 R | −0,44 % | +23,43 | +1.806,10 | +712,16 |

La candidata gana 43 episodios y pierde 24, con 15,6 días de media y un score de
entrada medio de 10,8 pb/día. Ya en desarrollo su esperanza (0,0349 R) no llega
a 0,05 R; la variante de 30 días sí (0,0692 R), pero es la que más se degrada
después.

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Episodios | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **C7-Q20-W-25** | **22** | **44** | **−0,21 %** | **0,1356** | **−0,0047 R** | −0,24 % | +18,39 | +122,37 | **−59,50** |
| C30-Q20-W-25 | 12 | 24 | −0,13 % | 0,2323 | −0,0056 R | −0,19 % | +3,84 | +67,52 | −42,63 |
| C7-Q20-D-25 | 35 | 70 | −0,55 % | 0,1285 | −0,0079 R | −0,56 % | +5,49 | +162,58 | −157,80 |
| C7-Q10-W-25 | 18 | 36 | −0,41 % | 0,0670 | −0,0114 R | −0,43 % | +21,70 | +190,90 | −108,03 |
| C7-Q20-W-10 | 33 | 66 | −0,46 % | 0,0657 | −0,0070 R | −0,50 % | +19,52 | +153,84 | −122,97 |

La candidata gana 4 episodios y pierde 18. El funding aporta +122,37 USD y el
precio +18,39, pero los costes son 192,50 USD: el neto es -51,73 USD. El coste
medio por episodio es 8,75 USD y el funding medio solo 5,56 USD. El score de
entrada medio cae de 10,8 pb/día en desarrollo a 4,9 pb/día en OOS.

## Puertas (candidata C7-Q20-W-25)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 44 | **falla** |
| PF OOS | > 1,10 | 0,1356 | **falla** |
| Esperanza OOS | > 0,05 R | −0,0047 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0175 R | pasa |
| P&L sin top-5 | > 0 | −59,50 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | la muestra ya falla |
| DSR | ≥ 0,95 | no ejecutado | la muestra ya falla |
| Estrés 2× | PF > 1,00 | no ejecutado | la muestra ya falla |
| CPCV / aleatorias | — | no ejecutado | la muestra ya falla |

No se ejecutaron PBO, DSR, estrés, CPCV ni aleatorias: la muestra, el PF, la
esperanza y el top-5 fallan antes. No se bajó el umbral ni se añadieron
variantes para rescatarla.

## Lectura

- **El carry se comprimió, no desapareció del todo.** En desarrollo el score
  medio de entrada era 10,8 pb/día; en 2025-2026 es 4,9. El funding por episodio
  cae de unos 12,9 USD a 5,56, por debajo de los 8,75 USD de costes. El precio
  aporta poco y positivo; el problema es la magnitud del carry, no el signo.
- **Bajar el umbral no arregla nada.** La variante de 1 pb/día genera 33
  episodios, pero pierde -0,46 % y su top-5 es -122,97: más operaciones solo
  reparten el mismo coste entre un carry menor.
- **El diario y el decil tampoco.** Diario: 35 episodios, -0,55 %; decil: 18
  episodios, -0,41 %. Ninguna de las cinco variantes se acerca a 100 operaciones
  ni a PF 1,10.
- **La cartera es BNB disfrazada.** 13 de los 22 episodios son BNB y aportan
  -36,69 USD. El quintil superior de basis casi siempre lo ocupa el mismo activo;
  no hay diversificación cross-sectional real.
- **Entradas con basis negativo.** El score suma funding y basis, así que algunas
  entradas (FIL -9,2 pb, SAND -7,5 pb, ETC -4,6 pb) compraban spot caro contra el
  perpetuo y perdían en la convergencia. El funding no compensó.
- **El desarrollo engaña otra vez.** +4,78 % con PF 8,24 y 67 episodios se
  convierte en -0,21 % con 22 episodios. Es el mismo patrón que H5-H8: el bruto
  se desvanece al cambiar de régimen y el coste queda expuesto.
- **El holdout sigue sellado.** No se usó 2026-11-01/2027-05-31.

## Consecuencia para el plan

H7, H8 y H9 son tres familias consecutivas fallidas. Antes de H10 toca la pausa
de dos semanas y la revisión de diseño del 2027-01-08 que marca el plan; no se
pre-registra otra familia hasta cerrarla. La puerta dura de investigación del
2027-02-26 no cambia.

## Nulidad por permutación (2026-11-27)

`python scripts/permutation_families.py --family H9` permuta **los dos
componentes del score** (50 permutaciones, semilla 20261127): baraja el funding de
cada símbolo y, a través del gancho `basis_override` del motor, el basis que entra
en la señal. Precio, ejecución y payoff siguen siendo los reales. El gancho es
opcional: con su valor por defecto el motor reproduce exactamente las cifras
archivadas. Para la pata de carry se corre además `perp = spot` (basis cero).

| | Episodios | Esperanza | PF |
|---|---:|---:|---:|
| Observado (C7-Q20-W-25) | 22 | −0,0047 R | 0,1356 |
| Nulidad basis+funding, mediana | 96 | −0,0104 R | — |
| Nulidad basis+funding, p5 / p95 | — | −0,0121 / −0,0095 R | — |
| Nulidad sólo funding, mediana | — | −0,0161 R | — |
| Sólo funding (basis = 0) | 40 | +0,0004 R | 1,0681 |

El observado supera a las **50** permutaciones completas (p unilateral 0,02, el
mínimo alcanzable con 50): el score real pierde 0,006 R menos por episodio que
uno con los dos componentes barajados, así que la ordenación no es ruido. La pata
aislada de carry queda en cero (+0,0004 R, PF 1,07): el carry no es negativo, está
comprimido.

Dos avisos para no leer de más. **El null no es una cartera del mismo tamaño:**
el score aleatorio cruza el umbral mucho más a menudo (96 episodios de mediana
frente a 22), así que la comparación vale por episodio y no como atribución entre
componentes —con sólo el funding barajado el null es más negativo (−0,0161), pero
con otra estructura de cartera—. Y **la muestra sigue siendo 22 episodios**: el
test dice que la señal ordena mejor que el azar, no que la estrategia tenga edge
que desplegar. El veredicto no cambia —PF 0,1356, BNB en 13 de 22, 28 pb de coste
de ida y vuelta— y se sostiene en las puertas, no en esta permutación.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H9.md`.
- Simulador: `server/basis_carry.py`; pruebas: `tests/test_basis_carry.py`.
- Descarga: `scripts/fetch_h9_data.py`.
- Datos: `data/basis/` con `freeze.json` y hashes; los CSV no se trackean.
- Salidas: `data/h9_dev.txt`, `data/h9_val.txt`.
- Siguiente: H10 (on-chain de stablecoins), sujeto a la revisión del 2027-01-08.
