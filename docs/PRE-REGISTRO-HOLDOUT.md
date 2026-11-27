# Pre-registro del test de holdout

**Fecha:** 2026-11-27
**Estado:** congelado. No se ha leído una sola fila del holdout ni se ha medido
nada para escribir este documento.
**Ventana:** 2026-12-01 / 2027-05-31 (sellada hasta que se cumpla la condición de
apertura).

## Qué abre el 2027-06-01, y qué no

Esa fecha **no** libera el holdout: sólo deja de ser futuro. El candado sigue
echado y este documento fija cuándo y cómo se abre.

El holdout **no es la ventana primaria de nadie**. H11 tiene la suya
(2027-06-01 / 2028-05-31, `docs/PRE-REGISTRO-H11.md`) precisamente para no
tocarlo. Leer el holdout primero sería medir la muestra más antigua antes que la
decisión y convertirla en la que manda; además obligaría a enmendar un
pre-registro congelado, que es lo que el laboratorio no hace.

Su papel es el de una **segunda muestra independiente de confirmación**, y sólo
se lee cuando ya existe un candidato que ha pasado sus propias puertas.

## Familia elegible

**H11, y sólo H11.** Es la única familia pre-registrada y sin medir. Las diez
archivadas no son elegibles: ya gastaron su ventana, su veredicto está cerrado y
reabrirlas en el holdout sería la pesca que el DSR de 54 ensayos existe para
castigar.

Condición de apertura, las dos a la vez:

1. H11 se midió en su ventana primaria con el pre-registro congelado.
2. Pasó **todas** las puertas duras de esa ventana, sin excepción y sin
   recalcular ninguna después de ver el resultado.

Si H11 falla cualquiera, **el holdout no se abre** y se retira sin usar en este
ciclo. Un holdout que se abre porque el candidato falló no es un holdout, es una
segunda oportunidad.

## Configuración congelada

La de `docs/PRE-REGISTRO-H11.md`, sin un solo cambio: universo del panel de H10
sin los 20 majors, señal de funding 7 d con z-score de 90, k = 4 por lado,
nocional fijo de 3.125 USD, 25.000 de bruto, rebalanceo semanal persistente,
coste 10 pb por posición y lado, R = 250 USD. Ningún parámetro se re-elige
mirando el holdout: si algo se cambia, es otra familia y otro ensayo, y este
documento deja de aplicar.

## Datos y candado

| Elemento | Regla |
|---|---|
| Ventana | 2026-12-01 / 2027-05-31, 26 semanas |
| Fuente | Binance Vision, los mismos ficheros mensuales que el panel de H10 |
| Construcción | idéntica a `docs/PRE-REGISTRO-H10.md` §Universo, punto en tiempo |
| Congelación | SHA-256 de cada serie en `data/holdout/freeze.json` **antes** de simular |
| Candado | `scripts/holdout_guard.py` |

El candado ya está implementado y no se toca para esta lectura: `guard()` aborta
cualquier frame con filas dentro del tramo, y sólo lo abre con
`EZUR_HOLDOUT_UNSEAL=1` **y** un `data/holdout/PREREGISTRO.sha256` que contenga el
SHA-256 de este documento.

Ese fichero se escribe en el momento de la lectura, no antes, y en el mismo
commit que el resultado. El documento no se edita después: cualquier cambio
cambia su hash e invalida la apertura.

**Una sola lectura.** El resultado se escribe con hash y no se vuelve a ejecutar.
Si el proceso falla a medias, se publica el fallo y se decide con lo que haya; no
se reintenta hasta que salga bonito.

## Estadístico exacto

Se calcula sobre el holdout, con la configuración congelada, **una vez**:

| Estadístico | Definición |
|---|---|
| Operaciones | `2 × episodios` cerrados dentro de la ventana |
| PF | ganancias brutas / pérdidas brutas de los episodios |
| Esperanza | P&L neto / operaciones, en R (250 USD) |
| Coste | coste total / operaciones, en R |
| Top-5 | P&L neto menos los cinco mejores episodios |
| Desglose | precio, funding y costes por separado, y beta residual contra BTC |
| Neto | curva diaria compuesta y suma de patas, las dos, etiquetadas |

**No se calculan**: DSR (ya se calculó en la primaria con denominador de 54
ensayos), PBO (una sola configuración no tiene selección que sobreajustar),
intervalos de confianza (el umbral es puntual y está fijado aquí; añadirlos
después sería otra prueba), ni desglose por símbolo, semana o subperiodo. No hay
subgrupos porque cualquier subgrupo que se mire se convierte en una hipótesis
nueva sin pre-registro.

## Regla de decisión

**PASA** si y sólo si se cumplen las cinco:

| Criterio | Umbral |
|---|---:|
| Operaciones | ≥ 100 |
| PF | > 1,10 |
| Esperanza | > 0,05 R por operación |
| Coste ponderado | < 0,25 R por operación |
| P&L sin top-5 | > 0 |

**Y el diagnóstico de carry**: si la pata de precio pierde más de lo que la de
funding gana y el neto sólo es positivo por el funding, la confirmación falla
aunque las cinco cifras pasen. Es el criterio con el que se archivó H5 y no se
relaja aquí.

**Si pasa**: la familia queda confirmada en dos muestras independientes y pasa a
paper trading con el tamaño que fije el techo de capacidad medido. No pasa a
live: el laboratorio es paper-only, y esa decisión no la toma este documento.

**Si falla cualquiera de las seis**: H11 se archiva de forma permanente. No hay
tercera muestra, no se re-mide con otro coste, no se cambia k para «ver si» y no
se usa el holdout para elegir entre variantes. Cualquier variante que el resultado
sugiera nace como **ensayo nuevo**, con su pre-registro y con datos posteriores al
2028-05-31; este holdout ya estará gastado.

## Contabilidad de ensayos

Esta lectura **no suma un ensayo**: no añade una configuración, es la
confirmación pre-declarada de la 54. El denominador del DSR sigue siendo 54 en la
ventana primaria, y el holdout se juzga con umbrales fijos, no con un estadístico
que dependa de cuántas pruebas se hicieron.

Lo que sí suma: cualquier configuración distinta que se derive del resultado, que
entra como ensayo 55 o superior, y cualquier familia futura que quisiera usar este
holdout, que ya no podrá.

## Qué no se hace

- No se abre el 2027-06-01 para mirar «cómo se comportó»: no hay candidato
  todavía y la mirada no sería inocua.
- No se lee si H11 falla su ventana primaria.
- No se publican cifras parciales del holdout antes de la lectura única.
- No se reejecuta con otro coste, otro k u otra permanencia.
- No se usa para elegir entre variantes ni para ajustar el tamaño.
- No se borra ni se modifica el panel: el candado impide el uso accidental, no
  esconde el dato.

## Firma

Al leer, `scripts/holdout_guard.py` exigirá:

```
EZUR_HOLDOUT_UNSEAL=1
data/holdout/PREREGISTRO.sha256 == sha256(docs/PRE-REGISTRO-HOLDOUT.md)
```

Ese hash se escribe en el commit de la lectura, junto al `freeze.json` del tramo
y al resultado. Antes de eso, este documento vive en `master` sin efecto: es una
promesa con fecha y con regla, no una llave.
