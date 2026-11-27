# Registro de ensayos del laboratorio

Este fichero existe para que el DSR y el PBO se calculen sobre **todos** los
intentos, no solo sobre el que se enseña. Cada fila es una variante que llegó a
medirse; las que se descartaron antes de medir no cuentan, pero se listan para
que no haya dudas.

## Familias y variantes medidas

| Familia | Variantes | Periodo de medida | Resultado OOS | Archivo |
|---|---:|---|---|---|
| SMA 15 m (rejilla canónica) | 5 | 2020-2026, WFA/CPCV | PF 0,9763, esperanza +0,0252 R, PBO 0,4087, DSR 0,0912 | `docs/ARCHIVO-SMA-15M.md` |
| Donchian 1 h (H1) | 5 | 2025-01/2026-11 | PF 0,7529, esperanza -0,0436 R, P&L -545 USD | `docs/ARCHIVO-H1.md` |
| Carry BTC (H2) | 5 | 2025-01/2026-11 | 4 episodios, +2,35 % anual, IC80 1,85-6,75 % | `docs/ARCHIVO-H2.md` |
| Momentum cross-sectional (H3) | 5 | 2025-01/2026-11 | PF 0,7046, esperanza -0,0447 R, P&L -30,9 % | `docs/ARCHIVO-H3.md` |
| Pares spot contra BTC (H4) | 5 | 2025-01/2026-11 | PF 0,9235, esperanza -0,0044 R, P&L -2,75 % | `docs/ARCHIVO-H4.md` |
| Carry cross-sectional de funding (H5) | 5 | 2025-01/2026-11 | candidata PF 1,1114, esperanza 0,0301 R, top-5 -1.864; raw PF 1,1849 pero DSR 0,54 | `docs/ARCHIVO-H5.md` |
| TSMOM long-only en 20 perpetuos (H6) | 5 | 2025-01/2026-11 | candidata -40,8 %, PF 0,8766; 60 d bate a BTC pero con peor DD y top-5 -20.400 | `docs/ARCHIVO-H6.md` |
| Flujo de taker (H7) | 5 | 2025-01/2026-11 | candidata -27,3 %, PF 0,9355, top-5 -11.152; ninguna variante pasa | `docs/ARCHIVO-H7.md` |
| Spread de funding entre venues (H8) | 5 | 2025-01/2026-11 | candidata +0,32 %, PF 10,46, esperanza 0,0094 R, 17 episodios/34 ops; ninguna variante llega a 100 ops | `docs/ARCHIVO-H8.md` |
| Basis spot-perp (H9) | 5 | 2025-01/2026-11 | candidata -0,21 %, PF 0,1356, esperanza -0,0047 R, 22 episodios/44 ops; las cinco variantes pierden | `docs/ARCHIVO-H9.md` |
| H5 re-hecho sobre el panel de H10 | 3 | 2025-01/2026-10 | motor validado contra funding_xs: la configuración fiel da 0,0066 R (falla 7,6×); k=4 pasa las simples pero falla top-5 en cada año | `docs/MEDICION-H5-PANEL-H10.md` |

**Total de variantes medidas:** 53. A ellas se suman las pruebas de viabilidad
exploratorias (umbrales de funding, ventanas de momentum) que no llegaron a
pre-registro; no se usan para coronar nada, pero inflan el espacio de búsqueda.
El DSR de cualquier hipótesis futura debe declarar al menos 53 ensayos, no 5.

## Descartadas antes de medir

| Familia | Variantes declaradas | Estado |
|---|---:|---|
| Carry cross-sectional en el tramo largo (extensión de H5) | 5 | cribado económico fallido (80,51 pb frente a los 240 pb de su geometría); archivada sin backtest |

Las cinco variantes de H10 están congeladas en `docs/PRE-REGISTRO-H10.md` y no se
midieron. **No se suman al total**: sólo cuentan las variantes que llegaron a
medirse, y el cribado económico no produce estadístico de estrategia. El DSR de
cualquier hipótesis posterior declara **53 ensayos** —50 previos más las tres
re-mediciones de H5 sobre el panel de H10— y no 55: el pre-registro decía 55
asumiendo que H10 llegaría a medirse, y no se midió.

## Lo que el registro ya dice

- Ninguna de las 50 variantes supera **todas** las puertas duras del plan en OOS.
- La mejor expectativa OOS es la del carry (+2,35 % anual), pero con 4
  episodios; no es una muestra.
- El mejor PF de desarrollo (momentum 14/7, 1,3523) se convierte en 1,0468 en
  OOS; el mejor PF OOS (carry, 34,33) es degenerado por tener un solo perdedor.
- El patrón se repite: el bruto se desvanece al cambiar de régimen y el coste no
  es la causa principal (0,006-0,03 R por operación, muy por debajo de 0,25 R).
- La variante raw de H5 pasó PF, esperanza, coste y top-5 en la ventana
  completa, pero cayó en DSR (0,54) y en el top-5 de cada año. Es el primer
  casi-éxito y la mejor prueba de que el DSR y la concentración no son
  decorativos.
- El TSMOM long-only de H6 multiplicó por 148 en desarrollo con DD -89 % y
  perdió -40,8 % en OOS con peor drawdown que BTC. La puerta de benchmark evitó
  confundir beta de alts con una ventaja.
- El flujo de taker de H7 pasó de +328,7 % en desarrollo a -27,3 % en OOS
  con PF 0,9355; el coste (0,0075 R) no explica nada y la única variante que no
  pierde es ruido plano. El order flow agregado no paga a 3 días en 20 majors.
- El spread de funding de H8 gana +0,32 % en OOS con PF 10,46, pero solo 17
  episodios y 0,0094 R. Bajar la entrada a 8 % sube a 44 episodios y deja
  0,0030 R; el problema es frecuencia y tamaño, no el umbral.
- El basis spot-perp de H9 pierde -0,21 % en OOS con PF 0,1356 y 22 episodios.
  El funding por episodio (5,56 USD) no cubre el coste (8,75 USD); las cinco
  variantes pierden y el quintil superior acaba concentrado en BNB.

## Regla de higiene

Antes de medir una hipótesis nueva se añade aquí su familia y su número de
variantes. Si el DSR se calcula sin este registro, el resultado no se acepta.
No se borran filas: una hipótesis archivada sigue contando para el múltiple
testing.
