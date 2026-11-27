# Archivo H5 — apuesta de precio con sesgo de funding

*Pre-registrada como «carry cross-sectional de funding». La etiqueta cambió al
medir la nulidad; el veredicto y las cifras no.*

**Veredicto:** archivada el 2026-11-27. La candidata pre-registrada falla
esperanza y concentración top-5. Una variante secundaria (funding bruto, sin
z-score) pasa las puertas simples en la ventana completa, pero **falla el DSR
(0,54 con 30 ensayos) y el top-5 en cada subperiodo**, y su P&L es más precio
que funding. No se despliega.

## Qué se probó

20 perpetuos USD-M, 141.980 pagos de funding y 47.255 cierres diarios
2020-2026 (SHA-256 funding `36956d1c…`, cierres `53c169aa…`). Cada lunes se
ordenan por la media de funding de 7 días (z-score de 90 días o nivel bruto),
largo del quintil inferior, corto del superior, dollar-neutral, 25.000 USD de
bruto, 6 pb por posición y lado. Cinco variantes; candidata H5-Q20-Z90-W.

Sesgo declarado: los 20 símbolos son los líquidos de 2026; no incluye
perpetuos deslistados. El resultado está sesgado a favor, no en contra.

## Desarrollo (2020-01-01 / 2025-01-01, 5,0 años)

| Variante | Episodios | Neto | PF | Esperanza | DD | Precio | Funding | Top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Q20-Z90-W** | 1.109 | +10,74 % | 1,0334 | 0,0141 R | -63,06 % | +7.052,86 | +5.105,83 | -18.945,88 |
| Q30-Z90-W | 1.375 | -11,09 % | 1,0099 | 0,0032 R | -43,70 % | +295,01 | +5.476,10 | -17.590,92 |
| Q20-RAW-W | 845 | +148,20 % | 1,1386 | 0,0665 R | -44,45 % | +17.916,05 | +13.486,85 | +11.726,30 |
| Q20-Z90-D | 2.159 | +358,11 % | 1,1592 | 0,0400 R | -58,75 % | +41.471,88 | +10.123,93 | +66.659,64 |
| Q20-Z30-W | 1.324 | -48,94 % | 0,9729 | -0,0116 R | -66,90 % | -7.363,99 | +4.976,95 | -31.646,59 |

## Validación OOS (2025-01-01 / 2026-11-01, 1,83 años)

| Variante | Ops | Neto | PF | Esperanza | DD | Precio | Funding | Top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Q20-Z90-W** | 800 | +24,35 % | 1,1114 | 0,0301 R | -18,77 % | +6.672,63 | +856,80 | **-1.863,63** |
| Q30-Z90-W | 1.020 | +23,90 % | 1,1146 | 0,0225 R | -18,87 % | +6.423,42 | +591,11 | -207,63 |
| Q20-RAW-W | 636 | +36,25 % | 1,1849 | 0,0525 R | -11,14 % | +7.092,37 | +2.442,63 | +3.525,60 |
| Q20-Z90-D | 1.872 | -1,19 % | 1,0050 | 0,0009 R | -24,36 % | +2.843,14 | +1.075,04 | -7.629,97 |
| Q20-Z30-W | 1.030 | -0,18 % | 1,0122 | 0,0032 R | -19,21 % | +2.261,28 | +496,24 | -7.492,98 |

## Puertas (candidata Q20-Z90-W)

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 800 | pasa |
| PF OOS | > 1,10 | 1,1114 | pasa |
| Esperanza OOS | > 0,05 R | 0,0301 R | **falla** |
| Coste ponderado | < 0,25 R | 0,0075 R | pasa |
| P&L sin top-5 | > 0 | -1.863,63 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | la candidata ya falla |
| DSR | ≥ 0,95 | no ejecutado | la candidata ya falla |

## La variante que casi pasa: Q20-RAW-W

| Puerta | Umbral | Resultado | Estado |
|---|---:|---:|---|
| Operaciones OOS | ≥ 100 | 636 | pasa |
| PF OOS | > 1,10 | 1,1849 | pasa |
| Esperanza OOS | > 0,05 R | 0,0525 R | pasa |
| Coste ponderado | < 0,25 R | 0,0075 R | pasa |
| P&L sin top-5 | > 0 | +3.525,60 | pasa |
| **DSR (30 ensayos)** | ≥ 0,95 | **0,5402** | **falla** |
| DSR (5 variantes) | ≥ 0,95 | 0,7637 | **falla** |
| Estrés 2× | PF > 1,00 | PF 1,1566; esperanza 0,0450 R | pasa PF, roza esperanza |
| Top-5 por subperiodo | > 0 | 2025: -1.871,67; 2026: -3.657,15 | **falla** |
| PBO | ≤ 0,20 | no ejecutado | — |
| CPCV / entradas aleatorias | — | no ejecutado | — |

**Por qué no se acepta:** se eligió después de ver los resultados (5 variantes,
todas declaradas), su DSR no llega ni al 0,95 ni al 0,76, y en cada año por
separado el P&L sin las cinco mejores operaciones es negativo. El +36 % de la
ventana completa depende de que las mejores operaciones de 2025 y 2026 caigan
en la misma muestra; no es una prima estable.

## Diagnóstico precio vs funding

La literatura advierte que un "carry" puede ser funding positivo compensado por
una pérdida de precio relativo. Aquí es al revés: el funding aporta
+2.442,63 USD y el precio +7.092,37 USD en la variante raw; en la candidata, el
funding solo +856,80 USD frente a +6.672,63 USD de precio. **No es un carry: es
un long-short de momentum disfrazado de ordenación por funding.** Eso explica
que funcione en la ventana completa y se rompa por subperiodos.

## Lectura

- La candidata pre-registrada falla dos puertas: no hay hipótesis que archivar
  con honores.
- La variante raw es el primer resultado del laboratorio que pasa PF,
  esperanza, coste y top-5 en OOS, y aun así **no es desplegable**: DSR 0,54 y
  concentración por año. El protocolo funcionó.
- El funding no es la fuente del retorno; el precio relativo sí. Si se quiere
  estudiar momentum de alts, es otra hipótesis, no un carry.
- Sesgo de supervivencia: 20 nombres vivos. La corrección probablemente empeora
  el resultado, no lo mejora.

## Nulidad por permutación (2026-11-27, después de archivar)

Se pasó al motor la prueba que ya tenía el cribado (`scripts/engine_validation.py`,
50 permutaciones del funding por símbolo, ventana OOS 2025-01/2026-11).

| | Esperanza |
|---|---:|
| Observado (Q20-Z90-W) | **+0,0301 R** |
| Nulidad: mediana | −0,0034 R |
| Nulidad: p95 | +0,0326 R |
| Nulidad: máximo de 50 | +0,0676 R |
| Percentil del observado | **94** (p = 0,0784) |

**El resultado no sobrevive.** Cuatro de cada cincuenta barajados del funding
producen una esperanza igual o mejor, y el p95 de la nulidad (+0,0326) está por
encima del observado (+0,0301). No es distinguible del ruido.

**Y el motivo es el que el diagnóstico de precio ya apuntaba.** Aislando la pata
de funding —precios constantes, mismo funding y mismos costes— el resultado es
**−643,20 USD, −0,0032 R, PF 0,6301**: el carry por sí solo **no cubre los
costes**, que son 1.500 USD. Los 6.029,43 USD de neto salen íntegramente de la
pata de precio (+6.672,63).

Consecuencia: H5 no era un carry con exposición de precio; era una **apuesta de
precio transversal** con un sesgo de funding, y el sesgo no pagaba. El archivo se
refuerza y la etiqueta cambia.

Canarios del motor: la señal de un día de rebalanceo no cambia al envenenar su
fila (diferencia 0,0), la del día siguiente sí (2,33), y los episodios cerrados
antes del veneno son idénticos hasta el céntimo (1.626,79 USD).

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H5.md`.
- Simulador: `server/funding_xs.py`; pruebas: `tests/test_funding_xs.py`.
- Datos: `data/funding_xs/funding_panel.csv`, `perp_1d_panel.csv` y `freeze.json`.
- Salidas: `data/h5_dev.txt`, `data/h5_val.txt`.
