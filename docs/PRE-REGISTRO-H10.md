# Pre-registro H10 — carry cross-sectional en el tramo largo

**Fecha:** 2026-11-27
**Estado:** congelado antes de descargar el panel y antes de medir.
**Hipótesis:** la prima de funding que ya no paga en los 20 mayores sigue
existiendo en los perpetuos pequeños, donde el capital de arbitraje no llega.
Una cartera dollar-neutral larga del quintil de funding más bajo y corta del más
alto cobra esa prima si el precio relativo no se mueve en contra más de lo que
paga el funding.

## Qué se hereda y qué cambia

H10 es la **extensión de universo de H5**, no una familia nueva. Se copia la
construcción de `docs/PRE-REGISTRO-H5.md` sin tocar nada y se cambian tres cosas:

| Elemento | H5 | H10 |
|---|---|---|
| Universo | 20 mayores, sólo vivos | 30-60 fuera de los mayores, **con deslistados** |
| Coste | 6 pb por posición y lado | **10 pb** por posición y lado |
| Panel | 20 nombres elegidos en 2026 | punto en tiempo, reconstruido por fecha |

El resto —señal, cartera, exposición, rebalanceo, ejecución, puertas— es
idéntico. Si H10 cambiara también la señal, no se podría atribuir una diferencia
al universo, que es la única razón declarada para volver a esta familia.

## Por qué existiría la ventaja

En los majors el funding de 2025-2026 rinde un 4 % anualizado frente a un 6,5 %
de punto de equilibrio (H9), y el spread entre venues aparece 0,77 veces al mes
(H8). Las dos primas existen y no pagan. En el tramo largo la mecánica es la
misma pero la magnitud no: el perpetuo de un token pequeño lo mueve una base de
traders apalancados mucho más estrecha, el creador de mercado cobra por el
riesgo de inventario y el capital que cerraría el basis no entra porque no cabe
o no quiere el riesgo de contraparte. Eso es exactamente un pago por iliquidez y
por riesgo de deslistado, no una ley de precios.

**Por qué no es H5 otra vez.** H5 midió la misma señal en nombres donde la
dispersión de funding ya está arbitrada; su variante que casi pasó tenía el 78 %
del P&L en precio, es decir, era momentum disfrazado. H10 fuerza la prueba al
sitio donde el funding tendría que ser la fuente, y la puerta de 120 pb está
puesta precisamente para que no pueda pasar por precio.

## Datos

Comprobado el 2026-11-27 (`scripts/check_h10_funding_coverage.py`): Binance
Vision conserva el funding de los perpetuos deslistados. De los símbolos con
`fundingRate` mensual, 202 no tienen fichero de 2026-10 (deslistados o sin datos
en octubre), **157 conservan 12 meses o más y 73 conservan 24 o más**. Seis ZIP
descargados del último mes de cada uno pasan su `.CHECKSUM` y traen filas; el
último mes de SXPUSDT tiene 14 filas y acaba el 2025-12-05, que es una baja y no
un corte de publicación.

| Dato | Fuente | Verificación |
|---|---|---|
| Funding | `futures/um/monthly/fundingRate/<SYM>` | `.CHECKSUM` mensual |
| Velas diarias | `futures/um/monthly/klines/<SYM>/1d` | `.CHECKSUM` mensual |
| Lista de símbolos | listado S3 de `data.binance.vision` | censo del 2026-11-27 |

El panel se construye **antes** de ejecutar el simulador y no cambia después de
ver resultados. `data/h10/freeze.json` guardará SHA-256 de cada serie, el conteo
de filas y la cobertura por símbolo y por mes.

## Universo y construcción del panel

**Universo elegible en cada fecha t:**

1. Perpetuos USD-M que **no** están en la lista de H5 (BTC, ETH, BNB, SOL, XRP,
   ADA, DOGE, AVAX, LINK, DOT, LTC, BCH, TRX, ATOM, NEAR, ETC, FIL, UNI, AAVE,
   SAND). Los majors se excluyen por construcción: ya se midieron.
2. Con al menos **90 días** de funding y de velas antes de t.
3. Con **volumen medio diario ≥ 5 M USD** en los 30 días anteriores a t, medido
   en `quote_volume` de sus propias velas. Es un filtro punto en tiempo: usa el
   volumen que el símbolo tenía entonces, no el de hoy.
4. Con precio y volumen **no nulos** el día de ejecución.

**Punto en tiempo, con bajas.** Un símbolo entra en el panel en su primer mes con
datos y sale en el último. No se usa el `exchangeInfo` de hoy, que sólo lista lo
que cotiza. Los meses de alta y de baja están truncados: el mes incompleto se
descarta de la serie de señal, no se prorratea.

**Tamaño de la cartera.** `k = max(2, round(n/5))` posiciones por lado, con `k`
entre 2 y 8, donde `n` es el número de elegibles. Con `n < 10` no se opera y se
mantiene la cartera anterior, igual que en H5. Si un símbolo deja de tener precio
a mitad de semana, su posición se cierra a su **último cierre disponible** y
queda registrada; no se extrapola ni se rellena el hueco.

## Reglas exactas

| Campo | Regla |
|---|---|
| Señal | media del funding diario de los últimos 7 días, estandarizada contra su media y desviación de 90 días |
| Cobertura de señal | al menos 80 % de días no nulos en la ventana de 7 días |
| Cartera | largo del quintil inferior de señal, corto del superior, mismo notional por posición |
| Exposición | 25.000 USD de bruto (12.500 largo / 12.500 corto), dollar-neutral |
| Rebalanceo | lunes al cierre UTC; se mantiene una semana (variantes: diario o dos semanas) |
| Ejecución | al cierre del lunes, con la señal del domingo |
| Instrumento | sólo perpetuos: no hay préstamo de spot ni pata larga de contado |
| Funding | se cobra/paga en cada evento; el corto recibe funding positivo |
| Costes | **10 pb por posición y lado** (4,5 pb taker + 5,5 pb spread e impacto) |
| Capital | 25.000 USD; sin apalancamiento adicional |
| R | **250 USD** (1 % del capital) |

**Sobre R.** R = **250 USD**, verificado en el código y no deducido de una cifra
redondeada: `server/funding_xs.py` fija `RISK_FRACTION = 0.01` sobre
`CAPITAL = 25_000`, y `server/basis_carry.py` importa esa misma constante. Las
dos esperanzas y los dos costes publicados se expresan **por operación**, y cada
episodio de una posición cuenta **dos** operaciones (`operations = 2 * len(...)`).
Por eso los 8,75 USD de coste de H9 salen como 0,0175 R: 8,75 / 2 = 4,375 USD por
operación, y 4,375 / 250 = 0,0175. El pre-registro de H10 había escrito 500 USD
por no dividir entre dos; queda corregido aquí y en §7.1 de la revisión.

**Coste en R.** 10 pb por lado sobre una posición de 3.125 USD son 6,25 USD de
ida y vuelta (20 pb) y 3,125 USD por operación: **0,0125 R**, muy por debajo de
la puerta de 0,25 R.

Las dos patas se abren con el mismo notional. Una posición abierta al cierre t no
devenga el funding de t; empieza en t+1. El P&L separa precio, funding y costes,
y publica además la beta residual de la cartera contra BTC.

## Umbral mínimo de dispersión: 120 pb por episodio

Fijado según la **regla 10 de `docs/PLAN-2027.md`** (cribado económico previo) y
desarrollado en `docs/REVISION-DISENO-H10.md` §7.1, antes de tocar el panel, y no
se renegocia aquí. Un episodio es una posición: 20 pb de coste (6,25 USD) y dos
operaciones, así que la puerta de 0,05 R por operación pide 25 USD netos, que
sobre 3.125 son 80 pb:

| Requisito | Coste | Bruto mínimo |
|---|---:|---:|
| Esperanza > 0,05 R/op | 20 pb | 100 pb |
| Estrés 2× con el mismo margen | 40 pb | **120 pb** |

**Regla: bruto por posición ≥ 0,1 R + 2 × coste de ida y vuelta.** Con R = 250 y
6,25 USD de coste, 25 + 12,5 = 37,50 USD = **120 pb** sobre 3.125.

Con la permanencia de 7 días que fija este documento, 120 pb son **17,14 pb/día**
o **62,6 % anualizado** de diferencial entre el quintil superior y el inferior.
La fila de 7 días se añadió a la tabla de §7.1 al congelar la permanencia, antes
de descargar un solo día, por la misma razón por la que se publicó la tabla: que
nadie elija la duración después de ver el resultado.

**Cómo se comprueba, sin estrategia.** Sobre el panel congelado y sólo con
funding: en ventanas no solapadas de 7 días, media del quintil superior menos
media del quintil inferior, con la misma elegibilidad que la cartera. Se publican mediana, p25 y proporción de ventanas ≥ 120 pb. **El criterio es la
mediana**, no la media ni el máximo.

Si la mediana no llega a 120 pb, **H10 se archiva sin ejecutar el simulador**. No
se baja el umbral, no se alarga la permanencia para maquillar el anualizado y no
se prueba el decil «porque el quintil no daba».

## Variantes pre-registradas (5)

| ID | Señal | Cartera | Rebalanceo | Permanencia |
|---|---|---|---:|---:|
| **H10-Q20-Z90-W** | z-score 90 d | quintil | semanal | 7 d |
| H10-Q20-RAW-W | funding medio 7 d, sin z | quintil | semanal | 7 d |
| H10-Q10-Z90-W | z-score 90 d | decil | semanal | 7 d |
| H10-Q20-Z90-D | z-score 90 d | quintil | diario | 1 d |
| H10-Q20-Z90-W2 | z-score 90 d | quintil | cada 2 semanas | 14 d |

La candidata es **H10-Q20-Z90-W**: la misma construcción que la candidata de H5,
para que la única diferencia sea el universo. Las otras cuatro prueban la
transformación de la señal (raw), la profundidad del corte (decil), la frecuencia
(diario) y el compromiso entre permanencia y muestra (dos semanas). Ninguna se
añade después de ver resultados.

**Muestra esperada.** 22 meses son 96 semanas: la candidata rebalancea 96 veces
con 8 posiciones, unas 768 operaciones OOS; el decil, unas 384; el diario, más de
5.000. La puerta de 100 operaciones se puede cumplir en las cinco, al contrario
que en H8 y H9.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Warmup | 2023-01-01 / 2023-07-01 | cubrir los 90 días de señal y el filtro de liquidez |
| Desarrollo | 2023-07-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez |
| Holdout | 2026-12-01 / 2027-05-31 | sellado, no se abre |

No se descarga ni se usa nada posterior al 2026-10-31.

## Puertas duras, en orden

| # | Criterio | Umbral |
|---|---|---:|
| 0 | Dispersión mediana por episodio | ≥ 120 pb |
| 0b | Símbolos elegibles por fecha | ≥ 20 en la mediana |
| 1 | Operaciones OOS | ≥ 100 |
| 2 | PF OOS | > 1,10 |
| 3 | Esperanza OOS | > 0,05 R |
| 4 | Coste ponderado | < 0,25 R |
| 5 | P&L sin top-5 | > 0 |
| 6 | PBO | ≤ 0,20 |
| 7 | DSR (55 ensayos) | ≥ 0,95 |
| 8 | Estrés 2× | PF > 1,00 |
| 9 | CPCV positivos | > 50 % |
| 10 | Entradas aleatorias | p < 0,05 |

Se aplican en orden. Las puertas 0 y 0b se evalúan **antes** de calcular P&L: si
fallan, no hay medida que discutir. Si fallan 1-5, se archiva sin gastar tiempo
en PBO/DSR y el archivo lo dice. Solo si pasan las simples se calculan las
restantes, con **55 ensayos** (50 previos + 5 de H10).

## Controles de robustez

- **PBO:** CSCV con 10 bloques sobre las cinco curvas diarias.
- **DSR:** Sharpe anualizado de la candidata contra las 55 pruebas declaradas.
- **CPCV:** bloques contiguos con purga de 7 días; fracción de caminos positivos.
- **Aleatorias:** mismas fechas, mismo número de posiciones y duración, símbolos
  elegidos al azar entre los elegibles de esa fecha; 1.000 réplicas.
- **Estrés:** duplicar los costes (20 pb por posición y lado) sobre el mismo OOS.
- **Benchmark:** efectivo (0 %) y BTC buy-and-hold.
- **Top-5 por subperiodo:** 2025 y 2026 por separado, no solo la ventana junta.

## Sesgos declarados

- **Baja a mitad de posición.** Un símbolo deslistado se cierra a su último
  cierre, no al precio de liquidación. Si la baja es desordenada, la pérdida real
  sería mayor: el sesgo favorece al test.
- **Supervivencia del precio.** El funding de los deslistados está, pero no se
  puede saber si su último mes se publicó completo; esos días se descartan.
- **Margen y liquidación.** No se modelan. Un short en un token pequeño puede
  sufrir un squeeze que en el backtest sólo aparece como pérdida de precio.
- **Topes de funding.** Binance recorta el funding en los extremos por intervalo,
  justo donde vive esta familia: la dispersión medida es un límite inferior.
- **Coste estimado.** 10 pb por lado es un supuesto declarado, no una medición.
  No se revisa después de ver los fills de un backtest.
- **Un solo régimen de desarrollo.** 2023-07/2025-01 no incluye la manía de alts
  de 2021. Si la prima solo existe en manías, este test no la verá.
- **Capacidad.** 1.562 USD por posición es pequeño; el resultado no prueba que
  la prima aguante tamaño.

## Qué la mataría

Dispersión mediana por debajo de 120 pb; menos de 20 elegibles; menos de 100
operaciones; PF ≤ 1,10; esperanza ≤ 0,05 R; P&L sin top-5 ≤ 0; DSR < 0,95;
estrés 2× con PF ≤ 1,00; y —la más importante— que el neto sea mayoritariamente
precio y no funding, en cuyo caso es H5 con otro nombre y se archiva igual.

## Criterio de aceptación

Pre-registro en `master` antes de descargar el panel y medir; panel con hash;
reglas y variantes congeladas; ninguna ejecución hasta cerrar este documento. La
medida se hace el 2026-12-18, se archiva el mismo día y se actualiza
`docs/TRIALS.md` a 55 variantes. Si falla, H11 no se reserva: la puerta dura del
2027-02-26 se resuelve con el informe de cierre.

## Nota de cierre (2026-11-27) — k queda fijo en 4

Las reglas de arriba **no se reescriben**: son las que se congelaron y las que se
aplicaron. Esta nota sólo resuelve una contradicción que quedó dentro del
documento y que el cribado encontró al ejecutarse.

**k = 4 posiciones por lado.** Es el valor que hace coherente la tabla de reglas y
todo lo que depende de ella: 12.500 USD por lado entre 4 posiciones son los 3.125
USD de nocional que usan el coste (6,25 USD de ida y vuelta), los 37,50 USD de la
regla 10 y su traducción a 120 pb. Es también el número que da por supuesto el
párrafo de R.

**El problema de la fórmula.** `k = max(2, round(n/5))`, en «Tamaño de la
cartera», no puede convivir con ese nocional fijo. Con los 183 elegibles que
resultaron en el panel da `round(183/5) = 37`, y 37 posiciones por lado dejan el
nocional en 337,84 USD: entonces 37,50 USD por posición ya no son 120 pb sino
1.110, y el coste de ida y vuelta deja de ser 0,0125 R para ser 0,0014 R. El tope
«entre 2 y 8» tampoco lo salva, porque 8 tampoco es el 4 de la tabla. La fórmula
escala con `n` y el nocional no; las dos cosas no pueden ser ciertas a la vez.

**Qué se hizo.** El cribado se ejecutó con el tope de 8 por lado, que es la
lectura más generosa que admite el documento, y falló igual: mediana de 80,51 pb
frente a los 240 pb que exige su propia geometría. Los números, la sensibilidad
con k = 4 y k = 37, y la corrección del script para que la barra salga de la
geometría están en `docs/ARCHIVO-H10.md`.

**Fecha y registro.** El cribado se ejecutó el **2026-11-27**, no el 2026-12-18
que fija «Criterio de aceptación»: el panel estaba congelado con hash y las reglas
cerradas, así que adelantar la fecha no cambia nada de lo pre-registrado, sólo
acerca la respuesta. Y `docs/TRIALS.md` sigue en **50** variantes, no en las 55 que
anuncia ese mismo criterio, porque las cinco de H10 no llegaron a medirse y la
regla del registro es que sólo cuentan las variantes medidas. Las dos cifras del
criterio de aceptación quedan como estaban; esta nota es la que anota por qué el
resultado no las siguió.

**Lo que el resto del documento sigue diciendo.** Varios pasajes de arriba no
coinciden con lo ejecutado y se dejan **como están**, por ser texto congelado: la
puerta 0 pide «≥ 120 pb» y el párrafo de «Cómo se comprueba» habla de quintil y de
ventanas ≥ 120 pb, cuando el cribado usó 8 por lado y su barra de 240 pb; y la
puerta 7 (DSR), el párrafo de «cada variante» y el control de DSR dicen «55
ensayos», cuando el denominador real es **50**. Leídos con esta nota no hay
ambigüedad; reescritos, dejarían de ser el pre-registro que se congeló.

**Para la próxima familia.** O se fija `k` y el nocional, o el umbral se declara
en dólares por posición y se recalcula por geometría. Las dos cosas a la vez
producen un documento que se puede leer de dos maneras y un resultado que se puede
comparar con la barra equivocada.
