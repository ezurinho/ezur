# H5 re-hecho sobre el panel congelado de H10

**Respuesta corta:** el veredicto no cambia. H5 sigue archivada, y en la
configuración que respeta sus reglas falla la puerta de esperanza por un factor
de doce. La corrección del sesgo de supervivencia no escondía un resultado
desplegable.

**Fecha:** 2026-11-27. **Ventana:** 2025-01-01 / 2026-10-31.

## Qué se cambió y qué no

H5 se midió sobre 20 perpetuos elegidos por liquidez de 2026, un sesgo de
supervivencia que su propio archivo declara. El panel de H10 corrige justo eso:
887 símbolos, deslistados dentro, liquidez punto en tiempo.

| Se cambia | Se mantiene intacto |
|---|---|
| El universo: 20 majors → el panel congelado | Señal: media de funding de 7 días, z-score de 90 |
| | Cartera: quintil inferior largo, superior corto, dollar-neutral |
| | Exposición: 25.000 USD de bruto, mismo nocional por posición |
| | Rebalanceo: lunes al cierre UTC, semanal |
| | Coste: 6 pb por posición y lado |
| | R: 250 USD; puertas en R y en dólares, no en pb |

**Dos avisos que condicionan la lectura.** El panel empieza el 2023-01-01, así
que el bloque de desarrollo de H5 (2020-2024) no se puede reproducir y no hay
PBO ni DSR. Y la ventana 2025-01/2026-10 ya la gastó H5: **nada de aquí puede
confirmar una hipótesis**; sólo el fallo es informativo.

## Resultados

Tres configuraciones, porque la fórmula de H5 da geometrías muy distintas según
el universo y la diferencia importa.

| Configuración | Por lado | Nocional | Ops | Neto | PF | Esperanza | Coste | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Quintil sin filtro de liquidez | 127 | 98 USD | 33.296 | +9.100 | 1,0666 | 0,0011 R | 0,0003 R | +5.292 |
| **Quintil con el filtro del panel** | **45** | **278 USD** | **15.568** | **+16.150** | **1,1124** | **0,0041 R** | **0,0003 R** | **+8.947** |
| k = 4 sobre el panel filtrado | 4 | 3.125 USD | 1.520 | +33.963 | 1,1928 | 0,0894 R | 0,0075 R | **−7.161** |

| Puerta | Umbral | Sin filtro | **Filtro del panel** | k = 4 |
|---|---:|---|---|---|
| Operaciones | ≥ 100 | 33.296 ✔ | 15.568 ✔ | 1.520 ✔ |
| PF | > 1,10 | 1,0666 ✘ | 1,1124 ✔ | 1,1928 ✔ |
| Esperanza | > 0,05 R | 0,0011 ✘ | **0,0041 ✘** | 0,0894 ✔ |
| Coste | < 0,25 R | 0,0003 ✔ | 0,0003 ✔ | 0,0075 ✔ |
| Sin top-5 | > 0 | +5.292 ✔ | +8.947 ✔ | **−7.161 ✘** |

Ninguna de las tres pasa todas las puertas. La del medio es la que respeta las
reglas de H5 sobre el panel tal como se congeló —con su filtro de liquidez, que
es parte de la construcción del panel—.

## Por qué falla la configuración fiel

Por geometría, no por señal. La esperanza de H5 se mide **por operación y en R**,
y R está fijado en 250 USD mientras el nocional por posición se divide entre `k`:

- H5 original: 4 por lado → 3.125 USD por posición → 0,0301 R por operación.
- Panel de H10: 45 por lado → 278 USD por posición → 0,0041 R por operación.

La cuenta cuadra con el cociente de nocionales (0,0301 × 4/45 = 0,0027 R, y el
tramo largo paga algo más de funding que los majors, de ahí el 0,0041). Para
llegar a 0,05 R por operación con posiciones de 278 USD haría falta un 4,5 %
semanal por posición; el diferencial entero del quintil en 2025-2026 son 44-98 pb
por semana. **La puerta es inalcanzable por construcción en cuanto crece la
amplitud**, sin importar la calidad de la señal.

Esto no lo arregla la corrección del sesgo: los 20 majors de H5 no eran sólo una
muestra sesgada, eran también la geometría que hacía medible su puerta.

## La configuración que pasa PF y no sirve

Con 4 posiciones por lado sobre el panel filtrado, H5 pasa PF (1,1928), esperanza
(0,0894 R) y coste, y **falla la misma puerta que tumbó su variante raw**: sin
las cinco mejores operaciones pierde 7.161 USD. Por años:

| Año | Neto | Sin top-5 | Precio | Funding |
|---|---:|---:|---:|---:|
| 2025 | +38.252 | −2.551 | +31.039 | +8.773 |
| 2026 | −4.289 | −17.056 | −25.998 | +22.999 |

Dos cosas que conviene no leer mal. Primero, **no es la geometría de H5**: 4 de 45
elegibles es el 9 % superior e inferior, no el quintil, así que es un corte más
profundo que el suyo y su PF no significa «H5 funciona». Segundo, 2026 pierde
dinero: el funding cobra 22.999 USD y el precio relativo se lleva 25.998.

## Lo que sí cambia con el panel

- **El sesgo de supervivencia no era la causa del fallo.** Corregido, el quintil
  amplio gana más dólares en total (+16.150 frente a los +6.087 de H5 en su OOS)
  y sigue sin llegar a la puerta por operación. El sesgo importaba menos que la
  geometría.
- **En el tramo largo el funding manda.** En k = 4, el funding aporta 31.772 USD
  y el precio 5.041: el 86 % del bruto, cuando en H5 el precio era el 89 %. El
  diagnóstico que enterró a H5 —«no es carry, es momentum disfrazado»— **no se
  reproduce** aquí. Pero el carry que aparece está concentrado en pocas semanas,
  y ahí falla top-5.
- Eso es exactamente lo que H10 intentó explotar, y lo que la regla 10 rechazó
  por magnitud: el tramo largo paga de verdad, pero no lo suficiente por posición
  ni con la estabilidad que piden las puertas.

## ¿Merece la pena?

**Como resurrección, no.** La ventana está gastada, así que ningún resultado
positivo sería admisible; dos de las tres configuraciones fallan la puerta que ya
falló H5; la que pasa PF falla top-5 en los dos años y pierde dinero en 2026.

**Como información, sí, y ya está pagada.** Cierra la duda de si el sesgo de
supervivencia tapaba un resultado mejor, y deja medido que el problema del tramo
largo es de **escala y concentración**, no de falta de funding. Es la misma
conclusión a la que llegó el cribado de H10 por otra vía —80,51 pb capturados
frente a 240 exigidos—, ahora con P&L en vez de con dispersión.

## Contabilidad

Tres configuraciones medidas, no cero: `docs/TRIALS.md` pasa de **50 a 53**
ensayos, y el DSR de cualquier hipótesis posterior debe declarar 53. Ninguna es
promocionable —la familia está archivada y la ventana gastada—, pero contarlas es
lo que impide que un día se elija la configuración que pasó PF sin decir que se
probaron tres.

## Artefactos

- Simulador: `scripts/h5_on_h10_panel.py` (reglas de H5, panel de H10, las tres
  configuraciones en una pasada).
- Salida: `data/h10/h5_on_h10.json` y `data/h10/h5_on_h10.log`.
- Reglas originales: `docs/PRE-REGISTRO-H5.md`; archivo: `docs/ARCHIVO-H5.md`.
- Panel: `docs/ARCHIVO-H10.md`.
