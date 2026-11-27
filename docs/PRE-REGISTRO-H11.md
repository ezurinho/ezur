# Pre-registro H11 — extremo del panel con tamaño de posición fijo

**Fecha:** 2026-11-27
**Estado:** congelado antes de descargar un solo día posterior al 2026-10-31 y
antes de medir nada. No se ha ejecutado ningún simulador para esta familia.
**Ensayo:** **54**. La cuenta del laboratorio pasa de 53 a 54 en cuanto esta
familia se mida; ver `docs/TRIALS.md`.

## Hipótesis

La prima de funding no está en el quintil del panel sino en su extremo. Con
cuatro posiciones por lado sobre los elegibles filtrados, la dispersión entre
colas es lo bastante grande para pagar 0,05 R por operación con el nocional fijo
de H5 (3.125 USD), y el resultado no depende de cinco operaciones.

## De dónde sale, y qué no se puede concluir

Sale de la re-medición de H5 sobre el panel de H10
(`docs/MEDICION-H5-PANEL-H10.md` §5): con k = 4 sobre el panel filtrado, la
configuración pasó PF (1,2409), esperanza (0,1331 R) y coste, y el top-5 agregado
(+2.077) — pero falló el top-5 **en cada año por separado** (−2.463 en 2025,
−9.237 en 2026).

Esa ventana (2025-01/2026-10) está gastada y la configuración se eligió **después**
de ver fallar el quintil. Nada de allí confirma esta hipótesis: es una familia
nueva con su propio ensayo, no una resurrección de H5. Lo único que aporta la
medición anterior es el tamaño del efecto que hace falta batir y el modo de
fallo que hay que vigilar.

## Qué se hereda y qué cambia

| Elemento | H5 / H10 | H11 |
|---|---|---|
| Universo | panel congelado de H10, sin los 20 majors | **igual** |
| Señal | media de funding 7 d, z-score 90 d | **igual** |
| Cartera | dollar-neutral, cola larga y cola corta | **igual** |
| Exposición | 25.000 USD de bruto | **igual** |
| Rebalanceo | lunes al cierre UTC, posición persistente | **igual** |
| Funding | se devenga desde t+1; el corto cobra el positivo | **igual** |
| R | 250 USD (1 % del capital) | **igual** |
| Tamaño por lado | `k = round(n/5)`, nocional = bruto / (2k) | **k fijo = 4, nocional fijo = 3.125 USD** |
| Coste | 6 pb (H5) / 10 pb (H10) | **10 pb por posición y lado** |

Dos cambios, y sólo dos: el tamaño de la posición deja de diluirse con la
amplitud del panel, y el coste se queda en el 10 pb que H10 ya había declarado
para nombres ilíquidos. La medición que motivó la familia usó 6 pb; a 10 pb la
esperanza de esa misma ventana era 0,1328 R (`docs/MEDICION-COSTE.md`), así que
el listón no se está bajando.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo | panel congelado de H10 (887 símbolos, punto en tiempo, con deslistados), excluidos los 20 majors |
| Elegibilidad | ≥ 90 días de funding y de velas; ADV de 30 días ≥ 5 M USD (mediana, desplazada un día); precio no nulo el día de ejecución |
| Mínimo operable | 20 elegibles; con menos no se opera y se mantiene la cartera anterior |
| Señal | media del funding diario de 7 días, estandarizada contra su media y desviación de 90 días; ≥ 80 % de días no nulos en la ventana de 7 |
| Cartera | largo de las 4 señales más bajas, corto de las 4 más altas, **nocional fijo de 3.125 USD por posición** |
| Exposición | 25.000 USD de bruto (12.500 / 12.500), dollar-neutral; sin apalancamiento |
| Rebalanceo | lunes al cierre UTC con la señal del domingo; la posición se mantiene mientras siga en cartera |
| Deslistados | se cierran al último cierre disponible y pagan coste de salida; no se extrapola |
| Costes | 10 pb por posición y lado: 20 pb ida y vuelta = 6,25 USD; 3,125 USD por operación = **0,0125 R** |
| Capital | 25.000 USD |
| R | 250 USD por operación (un episodio son dos operaciones) |

El tamaño fijo es la hipótesis, no un detalle: con 4 posiciones por lado de 3.125
USD la puerta de 0,05 R por operación es alcanzable; con el nocional diluido del
quintil (1.389 USD) no lo era ni con una señal perfecta (§4 del documento de la
re-medición).

## Cribado económico previo (regla 10), sin estrategia

Antes de escribir el simulador se comprueba que la oportunidad existe en la
magnitud que la puerta exige. Sobre el panel y **sólo con funding**: en ventanas
no solapadas de 7 días, media de la cola inferior (4 por lado, 9 %) menos la
superior, con la misma elegibilidad que la cartera. Se publican mediana, p25 y
proporción de ventanas que superan el umbral. **El criterio es la mediana.**

Umbral: **≥ 120 pb por episodio**, que es `0,1 R + 2 × coste de ida y vuelta`
(25 USD + 12,5 USD = 37,5 USD sobre 3.125).

Si la mediana no llega, **H11 se archiva sin ejecutar el simulador**. No se baja
el umbral, no se prueba el decil «porque la cola de 4 no daba» y no se alarga la
permanencia para maquillar el anualizado.

Este cribado usa datos ya gastados y por tanto no valida nada: sólo comprueba una
precondición económica antes de gastar la ventana buena.

## Puerta de potencia

`python scripts/power_gate.py --edge-bp 106 --available 100` con la dispersión
del cribado como sigma:

- sigma estimada de la oportunidad: **81,3 pb** (311 ventanas del cribado
  2020-2026; es una cota superior, una posición cubierta tiene menos varianza).
- Con el efecto medido en la ventana gastada (106 pb, optimista): **6,7
  episodios**.
- Con el suelo obligatorio de 40 pb por episodio: **47 episodios**.
- La ventana da unas 640 operaciones (≈ 320 episodios a 12,3 ops/semana).

Veredicto: **PASA** con margen en los dos escenarios. La puerta de 100
operaciones se alcanza en ~8 semanas; la ventana de un año da seis veces esa
muestra, que es lo que permite exigir el top-5 por bloque.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Reservado | 2026-11-01 / 2027-05-31 | **no se usa**: solapa el holdout desde el 2026-12-01 y el mes de noviembre solo no da muestra |
| Evaluación | 2027-06-01 / 2028-05-31 | una sola lectura al cerrar |
| Holdout | 2026-12-01 / 2027-05-31 | sellado; no se toca ni para cribar |

Una sola lectura al final de la ventana: **sin parada anticipada y sin
extensión**. Si al 2028-05-31 hay menos de 100 operaciones, se archiva por
muestra insuficiente. El motor debe rechazar cualquier fecha dentro del holdout;
si no lo hace, no se ejecuta.

## Puertas duras

| Criterio | Umbral |
|---|---:|
| Operaciones en la ventana | ≥ 100 |
| PF | > 1,10 |
| Esperanza por operación | > 0,05 R |
| Coste ponderado | < 0,25 R |
| P&L sin top-5, agregado | > 0 |
| P&L sin top-5, en cada bloque natural (2027 y 2028) | > 0 |
| Estrés 2× (20 pb por lado) | PF > 1,00 |
| DSR con **54 ensayos** | ≥ 0,95 |
| Entradas aleatorias (1.000 permutaciones) | p < 0,05 |
| PBO | no aplica: una sola configuración, no hay selección que sobreajustar |

El PBO no se calcula porque no hay un conjunto de configuraciones del que elegir;
el control de multiplicidad es el DSR con el denominador de 54 ensayos. Se
declara aquí para que nadie lo eche en falta después como si se hubiera olvidado.

## Diagnóstico obligatorio: precio frente a funding

Se publican por separado el P&L de precio, el de funding y los costes. Si el neto
positivo depende del funding pero el precio relativo pierde más de lo que el
funding paga, la familia no se acepta como carry aunque el PF salga alto. Es el
mismo diagnóstico que tumbó a H5 y el que separó el resultado de la cola de 4 en
2026 (funding +24.729, precio −14.849).

## Qué la mataría

- El cribado económico no llega a 120 pb de mediana.
- Top-5 negativo en el agregado o en cualquiera de los dos bloques naturales.
- Esperanza ≤ 0,05 R, PF ≤ 1,10 o coste ≥ 0,25 R.
- Que el neto positivo se sostenga en menos de cinco operaciones.
- Que el precio relativo se coma el funding y el neto sólo sobreviva por el
  funding de unas pocas semanas.

Cualquiera de ellas archiva la familia sin segunda lectura y sin cambiar k, coste
o permanencia.

## Lo que queda congelado

Reglas, umbral del cribado, ventana, puertas y número de ensayo. El código debe
aceptar el coste por lado como parámetro (hoy `scripts/validate_h5_engine.py` lo
tiene fijo en 6 pb) y revalidarse contra el control de H5 antes de medir. El panel
se reconstruye con los mismos ficheros y se publica su SHA-256 antes de la
primera ejecución. Cualquier cambio en lo anterior invalida este pre-registro y
suma un ensayo nuevo.

## Artefactos previstos

- Simulador: `scripts/h11_tail_panel.py` (o el motor validado con coste
  parametrizado).
- Congelación del panel: `data/h11/freeze.json` con hashes y cobertura.
- Cribado: `data/h11/screen.json`.
- Resultado y cierre: `docs/ARCHIVO-H11.md`.
