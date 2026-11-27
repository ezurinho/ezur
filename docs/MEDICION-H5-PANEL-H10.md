# H5 re-hecha sobre el panel congelado de H10

*(H5 = apuesta de precio con sesgo de funding. Pre-registrada como carry; la
etiqueta cambió al medir la nulidad del motor, no aquí: las cifras de este
documento son las mismas que se publicaron.)*

**Respuesta corta:** el veredicto no cambia, y el panel extendido lo refuerza. H5 sigue archivada. La configuración
que respeta sus reglas sobre el panel falla la puerta de esperanza por un factor
de 7,6. La corrección del sesgo de supervivencia no escondía un resultado
desplegable, y la única configuración que pasa las puertas simples agregadas
falla el top-5 **en cada año por separado** y depende de cinco operaciones. El
panel extendido, que la primera versión daba por inalcanzable, añade PBO, DSR y
CPCV (§3.1): el DSR de k = 4 con 54 ensayos es 0,08 en 2020-2024 y 0,21 en
2020-2026.

**Fecha:** 2026-11-27. **Ventana:** 2025-01-01 / 2026-10-31.

**Aviso de versión:** la primera versión de esta medición usaba un motor propio
con episodios semanales forzados. Validado contra `server/funding_xs.py`, ese
motor **infravaloraba** la esperanza a la mitad (0,0155 R frente a 0,0301 R en los
majors de H5). Los números de abajo son los del motor validado; §1 documenta la
reconciliación y §5 lo que la primera versión decía mal.

## 1. Validación contra el simulador original

Antes de dar por buenos los números, se corrió `server/funding_xs.py` sobre los 20
majors de H5 y la ventana OOS: reproduce lo publicado (400 episodios, 800
operaciones, PF 1,1114, esperanza 0,0301 R, precio 6.672,63, funding 856,80). El
panel y el código actuales son la referencia correcta.

Después se portó mi motor a las convenciones de H5 y se apagaron una a una:

| Corrida | Episodios | Ops | PF | Esperanza | Precio | Funding | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Publicado (funding_xs)** | 400 | 800 | 1,1114 | 0,0301 | 6.672,63 | 856,80 | −1.863,63 |
| **A · convenciones de H5** | 400 | 800 | **1,1114** | **0,0301** | **6.672,63** | **856,80** | −1.920,65 |
| B · A con episodio semanal forzado | 656 | 1.312 | 1,0733 | 0,0155 | 6.672,63 | 856,80 | −2.180,85 |
| C · A sin `ffill` (deslistado al último precio) | 400 | 800 | 1,1114 | 0,0301 | 6.672,63 | 856,80 | −1.920,65 |
| D · A con señal de 60 días mínimos | 423 | 846 | 1,1223 | 0,0334 | 7.819,74 | 840,53 | −876,06 |
| E · mi motor original (semanal, sin ffill, 60 mín.) | 696 | 1.392 | 1,0806 | 0,0174 | 7.819,74 | 840,53 | −1.200,01 |

**A reproduce H5 exactamente** en episodios, operaciones, PF, esperanza, coste
(0,0075 R), P&L de precio y de funding. El neto difiere 57,03 USD (0,9 %) porque
`funding_xs` publica el capital compuesto de los retornos diarios
(`(1+d).prod()−1`) mientras A suma los episodios; el top-5 difiere en los mismos
57,02 USD. No es una discrepancia de motor, es de unidad de cuenta, y afecta
igual a las dos cifras.

**Lo que cada convención mueve:**

- **Episodio persistente frente a semanal forzado: la diferencia grande.** H5
  mantiene la posición abierta mientras el símbolo siga en la cartera; mi motor
  la cerraba y reabría cada lunes. Eso duplica las operaciones (800 → 1.312) y
  los costes (1.500 → 2.460) sin ganar P&L, y **parte la esperanza por dos**
  (0,0301 → 0,0155) y baja el PF (1,1114 → 1,0733).
- **Señal con 60 días mínimos frente a 90 estrictos:** 23 episodios más y algo
  más de esperanza (0,0334), porque entra antes en símbolos nuevos.
- **`ffill` frente a cierre al último precio: sin efecto en los 20 majors.**
  Ninguno se deslistó en la ventana, así que el majors no valida ese camino. Sí
  importa en el panel de H10, donde los deslistados están dentro; el motor
  validado cierra al último precio disponible y paga coste de salida.
- **Funding:** el panel de H5 trae `rate` e `interval_h` y su motor normaliza a
  8 h (`rate × 8 / interval`); el panel de H10 trae el funding diario ya sumado.
  Con intervalos de 8, 4 y 2 h esa normalización no es inocua, pero el funding de
  la candidata pesa poco (856 de 6.086) y no cambia ninguna conclusión. El neto de
  H5 es 6.086,46 USD (curva diaria compuesta, lo que vería la cuenta); 6.029,43 es
  la suma aritmética de sus patas —precio 6.672,63 + funding 856,80 − costes 1.500—,
  que sirve para atribuir, no para contabilizar.

## 2. Qué se cambió y qué no

| Se cambia | Se mantiene intacto |
|---|---|
| El universo: 20 majors → el panel congelado | Señal: media de funding de 7 días, z-score de 90 |
| | Cartera: quintil inferior largo, superior corto, dollar-neutral |
| | Exposición: 25.000 USD de bruto, mismo nocional por posición |
| | Rebalanceo: lunes al cierre UTC, semanal, **posición persistente** |
| | Coste: 6 pb por posición y lado |
| | R: 250 USD; puertas en R y en dólares, no en pb |

El panel congelado de H10 empieza el 2023-01-01, pero `data/h10ext` reconstruye
el mismo panel desde 2020-01 con la misma construcción y hashes propios. Con él
el bloque de desarrollo (2020-2024) **sí** se reproduce, y PBO, DSR y CPCV están
calculados en §3.1; la versión anterior de este documento decía que no se podía.
La ventana 2025-01/2026-10 ya la gastó H5: **nada de aquí puede confirmar una
hipótesis**; sólo el fallo es informativo.

## 3. Resultados, con el motor validado

| Configuración | Por lado | Nocional | Ops | Neto (patas) | Compuesto | PF | Esperanza | Coste | Sin top-5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Quintil sin filtro de liquidez | 127 | 98 USD | 19.946 | +12.781 | +16.130 | 1,1427 | 0,0026 R | 0,0003 R | +9.388 |
| **Quintil con el filtro del panel** | **9** | **1.389 USD** | **9.404** | **+15.594** | **+20.260** | **1,1575** | **0,0066 R** | 0,0006 R | +9.378 |
| k = 4 sobre el panel filtrado | 4 | 3.125 USD | 1.168 | +38.870 | +24.590 | 1,2409 | 0,1331 R | 0,0075 R | +2.077 |

**Neto (patas)** es precio + funding − costes y sirve para atribuir de dónde sale
el resultado; **compuesto** es la curva diaria capitalizada, la única cifra
contable del laboratorio. Las puertas se miden en R por operación, así que no
dependen de esta columna. La diferencia no va siempre en la misma dirección: en
el quintil el compuesto supera a las patas y en k = 4 se queda muy por debajo
(24.590 frente a 38.870), que es el arrastre de una cartera de 8 posiciones.

| Puerta | Umbral | Sin filtro | **Filtro del panel** | k = 4 |
|---|---:|---|---|---|
| Operaciones | ≥ 100 | 19.946 ✔ | 9.404 ✔ | 1.168 ✔ |
| PF | > 1,10 | 1,1427 ✔ | 1,1575 ✔ | 1,2409 ✔ |
| Esperanza | > 0,05 R | 0,0026 ✘ | **0,0066 ✘** | 0,1331 ✔ |
| Coste | < 0,25 R | 0,0003 ✔ | 0,0006 ✔ | 0,0075 ✔ |
| Sin top-5 (total) | > 0 | +9.388 ✔ | +9.378 ✔ | +2.077 ✔ |

**La configuración fiel falla la esperanza por 7,6×** (0,0066 frente a 0,05). Las
otras dos fallan por 19× y por ninguna.

## 3.1 PBO, DSR y CPCV con el panel extendido

La primera versión de este documento afirmaba que el bloque 2020-2024 no se podía
reproducir y que por eso no había PBO, DSR ni CPCV. Era falso: `data/h10ext`
cubre 2020-01/2026-10 con el mismo panel y el motor validado corre sobre él. El
cálculo vive en `scripts/selection_h10ext.py` y su salida en
`data/h10ext/selection.json`.

**Espacio de búsqueda:** las tres geometrías de §3, ni una más. No se añaden
variantes para tener más columnas: eso sería una búsqueda nueva y otro ensayo.
La matriz diaria es de 1.675 días (2020-2024) y 2.344 (2020-2026); CSCV con 10
bloques y 252 particiones; CPCV con 10 bloques, 2 de test y purga de 1, 45
caminos; coste 6 pb, el de la medición.

| Ventana | Días | PBO (≤ 0,20) | CPCV bajo mediana | Rango OOS medio |
|---|---:|---:|---:|---:|
| 2020-04 / 2024-12 | 1.675 | 0,2063 | 4,4 % | 81 % |
| 2020-04 / 2026-10 | 2.344 | 0,1825 | 11,1 % | 81 % |

| 2020-04 / 2024-12 | Ops | Compuesto | PF | Esperanza | Sin top-5 | Sharpe diario | DSR(3) | DSR(54) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Quintil sin filtro | 15.324 | +111.367 | 1,1809 | 0,0117 R | +32.834 | 0,0979 | 0,9974 | **0,9641** |
| Quintil con filtro 5M | 14.104 | +68.108 | 1,1390 | 0,0100 R | +20.591 | 0,0787 | 0,9723 | 0,8284 |
| k = 4 con filtro 5M | 2.794 | +12.944 | 1,0625 | 0,0275 R | **−4.130** | 0,0223 | 0,3210 | **0,0798** |

Sobre 2020-2026 los DSR(54) son 0,9912, 0,9299 y **0,2080** en el mismo orden.

**DSR(3)** usa la dispersión empírica de las tres geometrías; **DSR(54)** usa el
umbral de 54 ensayos bajo nulos independientes (Var(SR) = 1/T), que es el
múltiplo del laboratorio. No son el mismo número: el segundo es más exigente y
no se mezclan.

**Lo que dicen.**

- El PBO está en el borde: 0,2063 en el bloque de desarrollo —seis milésimas por
  encima del umbral— y 0,1825 en el tramo completo. Con tres configuraciones esa
diferencia es ruido; lo honesto es decir «en el borde», no aprobar ni suspender.
- El CPCV es bajo (4,4 % y 11,1 % de caminos por debajo de la mediana, rango OOS
  medio 81 %): la geometría elegida in-sample suele quedarse por encima de la
  mediana out-of-sample. El espacio no es una máquina de sobreajuste.
- Pero la geometría elegida **nunca es k = 4**: gana 1 de 45 caminos en el bloque
  de desarrollo y 0 de 45 en el completo. Es la peor en Sharpe en las dos
  ventanas y su DSR(54) es 0,0798 y 0,2080, lejos de 0,95 incluso antes de
  deflactar por 54 ensayos. Su pase de puertas de 2025-2026 no sobrevive a la
  ventana extendida, que es lo que el top-5 por año ya avisaba.
- El quintil sí tiene un edge estadísticamente real sobre 2020-2026 (DSR(54)
  0,96/0,99), pero su esperanza es 0,010-0,012 R por operación en el bloque de
  desarrollo y 0,0026-0,0066 R en 2025-2026: entre 4 y 19 veces por debajo del
  umbral de 0,05 R. Significativo no es desplegable.

**Límites.** Tres configuraciones son un espacio pobre: el PBO y el CPCV son
mucho más gruesos que con una rejilla, y por eso se reportan con su número de
particiones. El bloque 2020-2024 comparte con el desarrollo de H5 los parámetros
de la señal (7 días, z de 90) sobre otro universo, así que no es una muestra
independiente al 100 %. Y el DSR(54) es un umbral bajo nulos, no la dispersión
empírica del ledger de 54 ensayos, que no se guarda.

Estas tres métricas son diagnóstico de selección sobre familias ya archivadas:
no añaden ensayos, no cambian veredictos y no tocan el holdout.

## 4. Por qué falla la configuración fiel

Por geometría, no por señal. La esperanza de H5 se mide **por operación y en R**,
y R está fijado en 250 USD mientras el nocional por posición se divide entre `k`:

- H5 original: 4 por lado de 20 → 3.125 USD por posición → 0,0301 R por operación.
- Panel de H10, quintil: 9 por lado de 45 → 1.389 USD por posición → 0,0066 R.

Para llegar a 0,05 R con posiciones de 1.389 USD haría falta un 0,9 % semanal por
posición; el diferencial del quintil en 2025-2026 son 44-98 pb por semana. **La
puerta es inalcanzable en cuanto la amplitud baja el nocional**, sin importar la
calidad de la señal.

Esto no lo arregla la corrección del sesgo: los 20 majors no eran sólo una
muestra sesgada, eran también la geometría que hacía medible la puerta de H5.

## 5. La configuración que pasa y por qué no vale

Con 4 posiciones por lado de 3.125 USD sobre el panel filtrado, H5 pasa PF
(1,2409), esperanza (0,1331 R), coste y **el top-5 agregado** (+2.077). Mi primera
versión decía que fallaba top-5 con −7.161: eso era el motor semanal, y era
erróneo. Con el motor validado el agregado pasa, pero al desglosarlo por año:

| Año | Neto (patas) | Sin top-5 | Precio | Funding |
|---|---:|---:|---:|---:|
| 2025 | +30.074 | **−2.463** | +22.015 | +9.165 |
| 2026 | +8.796 | **−9.237** | −14.849 | +24.729 |

**Falla el top-5 en cada año por separado**, que es el estándar con el que se
archivó la variante raw de H5 («top-5 negativo en cada subperiodo»). En 2026 el
neto positivo depende de cinco operaciones que valen más que el año entero, con
el precio relativo perdiendo 14.849 USD y el funding salvando la cuenta.

Y no es la geometría de H5: 4 de 45 elegibles es el 9 % de cada cola, no el
quintil del 20 %. Es una apuesta al extremo del panel con el tamaño de posición
de H5 — una hipótesis distinta, elegida **después** de ver que el quintil no
llegaba, sobre una ventana ya gastada.

## 6. Lo que sí cambia con el panel

- **El sesgo de supervivencia no era la causa del fallo.** Corregido, el quintil
  amplio gana más dólares en total: **20.260 compuesto** frente a los 6.086 de H5
  en su OOS (o 15.594 de patas frente a 6.029), una ventaja de 14.174 USD con el
  criterio contable del laboratorio. La versión anterior de esta frase restaba
  15.594 de patas a 6.086 compuesto y publicaba 9.508: eran unidades distintas.
  Con cualquiera de las dos medidas, sigue sin llegar a la puerta por operación.
- **En el tramo largo el funding manda.** En la configuración concentrada el
  funding aporta 33.894 USD y el precio 7.166 (83 % del bruto), cuando en H5 el
  precio era el 89 %. En **esa** configuración el diagnóstico «no es carry, es
  momentum disfrazado» no se reproduce. Pero no es H5: 4 de 45 elegibles es el
  9 % de cada cola, no su quintil, y es una cartera distinta. En **H5** la
  permutación del motor confirmó lo contrario de lo que sugiere esta sección:
  con precios constantes su pata de funding pierde sola (ver
  `docs/ARCHIVO-H5.md`). El carry aparece concentrado en pocas semanas, y ahí
  falla.
- Es lo mismo que dijo el cribado de la regla 10 —80,51 pb capturados frente a
  240 exigidos—, ahora con P&L.

## 7. ¿Merece la pena?

**Como resurrección, no.** La ventana está gastada, así que ningún resultado
positivo sería admisible; la configuración fiel falla por 7,6×, y la que pasa las
puertas simples falla el top-5 por año y no es la geometría de H5.

**Como información, sí, y ya está pagada.** Cierra la duda del sesgo de
supervivencia y deja medido que el problema del tramo largo es de **escala y
concentración**, no de falta de funding.

**Lo único que deja abierto** es una familia nueva, no H5: el extremo del panel
con tamaño de posición fijo, que pasa PF, esperanza y coste y falla por
concentración. Probaría con datos posteriores al 2026-10-31 y con pre-registro
propio, contando el ensayo. No se reserva ahora ni se prueba sobre el holdout.

## 8. Contabilidad

Tres configuraciones medidas (más las cinco corridas de validación, que no son
variantes de estrategia sino el mismo motor con convenciones distintas).
`docs/TRIALS.md` pasa de **50 a 53** ensayos. Ninguna es promocionable, pero
contarlas evita que un día se elija la configuración que pasó PF sin decir que se
probaron tres.

## 9. Artefactos

- Motor de la re-medición: `scripts/h5_on_h10_panel.py` (episodios semanales; se
  conserva por trazabilidad, **sus números quedan sustituidos** por los de abajo).
- Validación y motor persistente: `scripts/validate_h5_engine.py`.
- Salidas: `data/h10/validation_h5.json` y `.log`; `data/h10/h5_on_h10.json`.
- Reglas originales: `docs/PRE-REGISTRO-H5.md`; archivo: `docs/ARCHIVO-H5.md`.
- Panel: `docs/ARCHIVO-H10.md`.
