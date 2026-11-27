# Revisión de diseño H7-H9 → decisión de H10

**Fecha:** 2026-11-27
**Adelanta** la revisión que la regla 2 del plan exige tras tres familias
consecutivas fallidas (H7, H8, H9), prevista para el 2027-01-08.
**Decisión:** **H10 no es on-chain.** Es la extensión de universo de H5 al tramo
largo de perpetuos. Las diez puertas no se tocan y no se reserva H11.
**Alcance:** no se descarga, no se mide y no se añaden variantes. `TRIALS.md`
sigue en 50.

## 1. Qué se decide aquí y qué no

Esta revisión no elige la variante que hay que probar: decide **qué familia se
pre-registra**, con qué condiciones de viabilidad y qué se descarta. El
pre-registro con las cinco variantes congeladas es un documento aparte y no se
escribe antes del 2026-12-11, cuando termina la pausa de dos semanas.

No se ejecutó ningún backtest para escribir esto. Todo lo que sigue sale de
`ARCHIVO-H7.md`, `ARCHIVO-H8.md`, `ARCHIVO-H9.md`, `TRIALS.md` y la aritmética
de sus propias cifras.

## 2. La aritmética que comparten los tres fallos

| | H7 flujo de taker | H8 spread entre venues | H9 basis spot-perp |
|---|---:|---:|---:|
| Ventana OOS | 1,83 a | 1,83 a | 1,83 a |
| Operaciones | 2.652 | 34 | 44 |
| Episodios | — | 17 | 22 |
| Episodios por mes | — | 0,77 | 1,00 |
| Bruto (USD) | negativo | +199,10 | +140,76 |
| Costes (USD) | 0,0075 R/op | 119,00 | 192,50 |
| Neto (USD) | −2.224 precio | +80,10 | −51,74 |
| Neto (%) | −27,33 | +0,32 | −0,21 |
| Anual sobre 25.000 | −15,9 % | +0,18 % | −0,11 % |

La misma cuenta por episodio, que es donde se ve la causa:

| | H8 spread | H9 basis |
|---|---:|---:|
| Bruto por episodio | 46,8 pb | 20,5 pb |
| Coste por episodio | 28 pb | 28 pb |
| Neto por episodio | +18,8 pb | −7,5 pb |
| Bruto / coste | 1,67 | 0,73 |
| Episodios para 50 (100 ops) | 65 meses | 50 meses |

Y el carry realizado de H9 frente a su punto de equilibrio:

- Coste de ida y vuelta: 4 lados × 7 pb = **28 pb** por episodio.
- Permanencia media: 15,6 días → **1,79 pb/día = 6,55 % anualizado** sólo para
  empatar.
- Funding cobrado: 122,37 / (22 × 3.125) = 17,8 pb en 15,6 días →
  **1,14 pb/día = 4,16 % anualizado**.
- Basis (precio): +18,39 USD en 68.750 USD-nocional-episodio = 2,7 pb. Ruido.

**Aun con coste cero, el 4,16 % de H9 no bate una letra del Tesoro.** Ése es el
dato que cambia la lectura del laboratorio: en las tres últimas familias el
problema no fue la implementación, ni el coste, ni el tamaño de la muestra.

## 3. Tres causas distintas, un mismo diagnóstico

- **H7 — dato nuevo, horizonte equivocado.** Tenía la muestra más grande de
  todas (2.652 operaciones) y el coste más bajo (0,0075 R). El bruto ya era
  negativo. El flujo de taker explica el precio de forma contemporánea; a tres
  días se invierte o se desvanece. Ninguna rejilla de z arregla eso.
- **H8 — la prima era real y era rara.** 12-41 % anualizado de spread, +199 USD
  brutos, 1,67 veces el coste. Pero 0,77 episodios al mes: para 100 operaciones
  hacían falta 65 meses. La puerta de muestra era inalcanzable por construcción.
- **H9 — la prima estaba donde se buscaba, pero ya no paga.** El score de
  entrada cayó de 10,8 a 4,9 pb/día entre desarrollo y OOS; el funding por
  episodio (5,56 USD) quedó por debajo del coste (8,75 USD). Bajar el umbral
  sólo repartió el mismo coste entre un carry menor.

**Diagnóstico común.** Las tres cobran una prima de carry en nombres líquidos y
esas primas están, tras 2024-2026, en el tipo libre de riesgo o por debajo de la
fricción. Diez familias y 50 variantes después, la conclusión no es «falta el
parámetro»: es «el sitio donde buscábamos ya no paga».

## 4. Lo que el laboratorio tiene que corregir (y no es la hipótesis)

1. **Una sola ventana OOS y un solo régimen.** El desarrollo ya no informa: H9
   pasa de PF 8,24 a 0,1356 y H7 de +328,7 % a −27,3 %. El tramo 2020-2024
   premia cualquier señal que compre riesgo; 2025-2026 no.
2. **Diversificación falsa.** El quintil superior de H9 fue BNB en 13 de 22
   episodios; en H5 el 78 % del P&L era precio y no funding; en H7 la cesta
   dollar-neutral de alts siguió siendo beta. «20 nombres» no es una cartera.
3. **Puertas calibradas para H1/H3.** 100 operaciones en 22 meses son 2,3 al
   mes. Tres familias murieron ahí (H2 con 4, H8 con 17, H9 con 22) y dos de
   ellas con bruto positivo. **No se cambian las puertas**: si el tramo largo no
   da 100 operaciones, se archiva como las demás.
4. **El coste no es el enemigo.** H9 pagó 0,0175 R por operación, catorce veces
   por debajo del límite de 0,25 R. Bajar el peaje no crea una prima.

## 5. Por qué H10 no sigue siendo on-chain

Era la propuesta del ranking. Se descarta como **familia** por cuatro razones,
en este orden:

1. **No es falsable con nuestras puertas.** Un long BTC/cash con señal semanal:
   (i) no llega a 100 operaciones en 22 meses —los cambios de régimen se cuentan
   por decenas, no por centenas—; (ii) un DD ≤ 2,5 % es imposible manteniendo
   BTC; (iii) si se queda fuera del mercado la mayor parte del tiempo para
   proteger el DD, falla el benchmark de batir a BTC en neto. La familia no
   puede pasar ni fallar: produce un informe que no decide nada, y el
   laboratorio ya sabe lo que es eso (H2: +2,35 % con 4 episodios).
2. **No es dato nuevo, es beta con otro nombre.** La oferta de stablecoins crece
   con el colateral y el apalancamiento, que crecen con el precio. Es
   coincidente o retardada. H6 ya enseñó el coste de confundir beta con prima:
   +148× en desarrollo y −40,8 % en OOS con peor drawdown que BTC.
3. **Endogeneidad y revisiones.** Las series por cadena de DefiLlama se
   reconstruyen (quiebre de UST en 2022, cambios de supply puenteado). Un
   crecimiento a 7/30 días es sensible a esas revisiones.
4. **La evidencia citada no usa el dato gratis.** El paper de reservas de
   exchange (JBF 2022) usa clustering propietario de CryptoQuant; la parte
   gratuita —oferta agregada y TVL— es justo la que el paper no midió.

**Conclusión:** on-chain queda como posible **filtro de régimen** de otra
estrategia, nunca como familia propia. No se pre-registra.

## 6. Las alternativas, con los criterios del propio ranking

| Familia | Prima por episodio | ¿Falsable con las puertas? | ¿Desplegable? | Riesgo no medible | Veredicto |
|---|---|---:|---|---|---|
| Carry cross-sectional en el tramo largo (ext. H5) | Alta: la dispersión crece al bajar capitalización | Sí | Sí, sólo perpetuos | Deslistado, liquidez | **elegida (H10)** |
| Spread entre venues en el tramo largo | Alta | **No**: Hyperliquid no tiene historia de small caps | Sí | Venue | fuera por datos |
| Flujos on-chain de stablecoins | Beta, no prima | **No** | Sólo filtro | Endogeneidad | descartada como familia |
| Liquidez macro | Beta | Sí, pero es timing de un activo | Sí | Régimen | descartada (ya H6) |
| Prima de volatilidad de opciones | Real | **No**: sin superficie ejecutable gratis | No | Cola | descartada |
| Cascadas y open interest | Real | **No**: histórico truncado | No (minutos) | Latencia | descartada |
| Otra rejilla de precio/funding en majors | Ninguna | Sí | Sí | — | **prohibida** por el post-mortem |

No queda una familia con prima propia, test falsable y ejecución disponible que
no sea el tramo largo.

## 7. La decisión: H10 = H5 en el tramo largo

**Qué es.** El mismo motor cross-sectional de funding de H5 —dollar-neutral,
señal con datos hasta t-1, quintiles o deciles, coste por pata y lado— sobre un
universo de **30-60 perpetuos USD-M fuera de los 20 mayores**, con filtro de
liquidez calculado punto en tiempo y un panel que **incluye los símbolos
deslistados**.

**Por qué es legítimo y no «otra variante más».** El post-mortem admite tres
razones nuevas para volver a una familia: dato, universo o microestructura. Aquí
la razón es el universo, y la restricción que mató a H8 y H9 —prima por episodio
del orden del coste, un episodio al mes— es exactamente la que cambia al bajar de
capitalización: la dispersión de funding es mucho mayor y los extremos son
frecuentes. No se toca la construcción ni ningún umbral.

**Se declara como extensión de universo de H5**, no como familia nueva. El DSR
de H10 contará las 50 variantes anteriores, no cinco.

**Condición de viabilidad, antes de pre-registrar.** El panel tiene que incluir
los perpetuos que Binance deslistó, con su funding. Si Binance Vision no permite
reconstruir el funding de un contrato deslistado, H10 no se puede medir sin
sesgo de supervivencia —y el sesgo es justo el que hace que el tramo largo
parezca rentable— así que **no se pre-registra**: se escribe el informe de
cierre. Esta comprobación es de disponibilidad de datos, no una medida.

**Comprobado el 2026-11-27: la condición se cumple.**

Censo sobre el listado público de Binance Vision (`scripts/check_h10_funding_coverage.py`,
salida en `data/h10_coverage.json`): de los símbolos con `fundingRate` mensual,
**202 no tienen fichero de 2026-10** —deslistados o sin datos en octubre— y de
ellos **157 conservan 12 meses o más de funding y 73 conservan 24 o más**. La
muestra con más historia llega a 72 meses (ICXUSDT, STORJUSDT). Las velas
diarias del mismo símbolo también están en el archivo, así que hay precio y
volumen para el filtro de liquidez.

No basta con que el fichero exista: se descargaron seis ZIP del último mes de
cada símbolo y se verificaron contra su `.CHECKSUM`. Los seis pasan y traen
filas reales. La prueba de que la serie termina en la baja y no en un corte de
publicación es **SXPUSDT**: su último mes es 2025-12 y sólo tiene **14 filas**,
que acaban el 2025-12-05; un símbolo vivo no deja un mes truncado. ICXUSDT y
STORJUSDT acaban el 2026-08-27, también a mitad de mes.

**Consecuencia:** el panel de H10 se puede construir punto en tiempo con los
deslistados dentro. El sesgo de supervivencia del tramo largo —el que habría
hecho parecer rentable la familia por construcción— queda cerrado por
disponibilidad de datos, no por una suposición.

Lo que la comprobación **no** resuelve, y el pre-registro debe declarar:

- El universo de cada fecha se reconstruye con el primer y el último mes de cada
  símbolo, no con el `exchangeInfo` de hoy, que sólo lista lo que cotiza.
- Los meses de alta y de baja están truncados; se descartan o se prorratean, y
  la regla se fija antes de medir.
- Hay símbolos con funding y sin velas, o al revés; el panel es la intersección.
- El funding de un contrato deslistado no dice nada de su liquidez en vida: el
  filtro se calcula con el volumen de sus propias velas, no con el de hoy.

**Coste declarado.** 10 pb por pata y lado (40 pb ida y vuelta), por encima de
los 7 pb de los majors, porque el spread es más ancho. Se declara en el
pre-registro, no se ajusta después de ver el resultado.

**Puertas.** Las diez del plan, sin cambios: ≥ 100 operaciones OOS, PF > 1,10,
esperanza > 0,05 R, coste < 0,25 R, P&L sin top-5 > 0, PBO ≤ 0,20, DSR ≥ 0,95,
estrés 2× con PF > 1,00, CPCV y entradas aleatorias.

### 7.1 Umbral mínimo de dispersión, fijado antes de medir

Este número se declara aquí, con el coste ya escrito y sin haber consultado un
solo día del panel. No es un filtro de entrada: es la condición económica que
H10 debe cumplir para que medirla tenga sentido. Si el panel no la cumple, la
familia se archiva **sin calcular P&L**.

**Unidad.** 25.000 USD brutos: 4 posiciones largas y 4 cortas de 3.125 USD cada
una. **Un episodio es una posición**, de entrada a salida, y son **dos
operaciones**; así las cuenta el simulador (`operations = 2 * len(episodes)`).
R = **250 USD**: `RISK_FRACTION = 0.01` sobre `CAPITAL = 25_000` en
`server/funding_xs.py`, constante que importa `server/basis_carry.py`.

Una posición paga 10 pb al abrir y 10 al cerrar: **20 pb = 6,25 USD** de ida y
vuelta. La puerta de esperanza pide 0,05 R **por operación** = 12,5 USD; un
episodio son dos operaciones, así que necesita **25 USD netos**, que sobre 3.125
de nocional son **80 pb**.

**Corrección del mismo día.** La primera versión decía R = 500 USD y 100 pb,
deducidos de dos atajos: dividir el coste del episodio de H9 entre R sin
repartirlo entre sus dos operaciones, y tratar el episodio como el par completo
(40 pb) cuando el simulador cuenta una posición (20 pb). Con el código delante,
8,75 / 2 / 250 = 0,0175 R, que es exactamente lo que publica H9. **El umbral
queda en 120 pb, no en 100.**

**De dónde sale el número.** Cada puerta impone un bruto mínimo distinto:

| Requisito | Coste por posición | Bruto mínimo | Neto que deja |
|---|---:|---:|---:|
| Supervivencia (break-even) | 20 pb | 20 pb | 0 |
| PF > 1,10 | 20 pb | 22 pb | 2 pb |
| Esperanza > 0,05 R/op | 20 pb | 100 pb | 80 pb = 25 USD |
| Estrés 2× (PF > 1,00) | 40 pb | 40 pb | 0 |
| **Estrés 2× con el mismo margen** | 40 pb | **120 pb** | 80 pb = 0,05 R/op |

**Umbral declarado: 120 pb de dispersión capturada por posición y episodio**,
37,50 USD. La regla que se lleva al pre-registro es una suma, no un múltiplo:

> bruto por posición ≥ 0,1 R + 2 × coste de ida y vuelta

Con R = 250 y 6,25 USD de coste: 25 + 12,5 = 37,50 USD = 120 pb sobre 3.125. El
coste duplicado ya está dentro de la fórmula, así que el umbral no es «lo mínimo
para empatar» sino lo mínimo para seguir cobrando 0,05 R por operación cuando el
peaje se duplica.

**Por qué no 100 pb.** 100 pb es justo el punto en que la esperanza toca 0,05 R
con coste normal: cero margen, y la puerta pide «>». Con 120 pb el margen
sobrevive al estrés 2×, que es la prueba que más debería exigir.

**La cifra en pb no es universal.** 0,1 R son dólares fijos y el nocional por
posición no: con 2 posiciones por lado (6.250 cada una) los mismos 37,50 USD son
60 pb, y con 8 por lado (1.562,50) son 240 pb. Por eso el pre-registro fija el
umbral en **dólares por posición** y publica 120 pb como su equivalente para la
geometría de la candidata. Comparar variantes de distinta amplitud por bp sería
comparar dos cosas distintas; entre variantes se compara en R, como siempre.

**En el tiempo.** El umbral es por episodio; la permanencia la congela el
pre-registro. La conversión, publicada ahora para que nadie elija la permanencia
después de ver el resultado:

| Permanencia | pb por día | Anualizado | Ventanas no solapadas en 22 meses |
|---:|---:|---:|---:|
| 7 días | 17,14 | 62,6 % | 96 |
| 14 días | 8,57 | 31,3 % | 48 |
| 21 días | 5,71 | 20,9 % | 32 |
| 28 días | 4,29 | 15,6 % | 24 |
| 42 días | 2,86 | 10,4 % | 16 |

La última columna es la otra cara del umbral: cuanto más larga la permanencia,
menos ventanas independientes hay para calcular la mediana (96 con 7 días, 16
con 42) y más frágil es el cribado. La muestra de operaciones no limita en
ninguna: con 8 posiciones por rebalanceo, la puerta de 100 operaciones se cubre
en siete semanas.

La fila de 7 días se añadió el mismo 2026-11-27, al congelar la permanencia en
`docs/PRE-REGISTRO-H10.md`, y antes de descargar un solo día del panel. Se deja
anotado para que la tabla no parezca ajustada a posteriori: la fórmula no cambió,
sólo se publicó la fila que el pre-registro necesitaba.

**Cómo se mide, sin estrategia.** Sobre el panel congelado, sólo funding y sin
precios: en ventanas no solapadas de la permanencia declarada, la media de los `k`
nombres con señal más alta menos la de los `k` más baja. Se publican mediana, p25
y proporción de ventanas ≥ la barra de su geometría (`30 × k` pb: 120 con 4 por
lado, 240 con 8).

**El criterio es la mediana, no la media.** El gate de top-5 ya castiga la
concentración; usar la media aquí dejaría que una semana de 400 pb pagase
cuarenta planas. Si la mediana no llega, H10 no es viable aunque la media sí.

**Es dispersión de funding, no de precio.** Si el umbral sólo se alcanza cuando
se suma el precio, la familia es H5 otra vez y se archiva. El P&L de precio se
mide aparte y no cuenta para este número.

**Si no llega.** Se archiva. No se baja el umbral, no se alarga la permanencia
para mejorar el anualizado, no se cambia de decil y no se prueba un quintil
«porque el decil no daba muestra». Si llega a 60-99 pb, el resultado esperado es
el de H8 —positivo y por debajo de la puerta— y se archiva igual.

**Si el coste real sube.** La regla se aplica al coste declarado: a 15 pb por
pata y lado el coste por posición sería 9,375 USD y el umbral 43,75 USD = 140 pb.
El coste declarado no se revisa después de ver los fills de un backtest.

**Resultado del cribado (2026-11-27).** Se ejecutó sobre el panel congelado y
**no pasó**: 187 ventanas, mediana **80,51 pb**, p25 21,01, p75 187,61, 39,6 % de
ventanas por encima de la barra de su geometría (240 pb), margen mediano de
−159 pb. La media (149,30) sí pasaba, que es exactamente el
motivo por el que el criterio es la mediana. H10 quedó archivada sin backtest en
`docs/ARCHIVO-H10.md`.

**Qué pasa con las esperanzas ya publicadas.** Nada: no se recalculan. H5
(0,0301 R) y H9 (−0,0047 R) salieron del mismo código con R = 250 y por
operación, así que ya estaban bien. La comprobación cierra por los dos lados:
0,0301 × 250 × 800 operaciones ≈ 6.020 USD, frente a los 6.087 USD del +24,35 %
sobre 25.000 de H5; y −0,0047 × 250 × 44 = −51,7 USD, que es el neto de H9. El
error era mío en esta sección, no en los archivos.

**Beta.** Se publica el P&L de precio y el de funding por separado, y la beta
residual de la cartera contra BTC. Si el neto es mayoritariamente precio, se
archiva: sería H5 otra vez, con más ruido.

**Qué la mataría.** Menos de 100 operaciones; supervivencia no resuelta; neto
explicado por precio; DSR por debajo de 0,95; top-5 que cambie el signo; y una
dispersión mediana por episodio por debajo de la barra de su geometría —240 pb con
8 por lado, 120 con 4— (§7.1).

**Qué significaría un éxito.** Que la prima del tramo largo existe y es el pago
por iliquidez y riesgo de deslistado. Eso es un riesgo que este backtest no
puede suscribir: el resultado se documenta como hallazgo y **tampoco va a
paper**. No se convierte un premium de iliquidez en una estrategia de 25.000 USD
sin haber medido ese riesgo, y no se mide con datos gratuitos.

## 8. Lo que no se hace en esta revisión

- No se abre el holdout 2026-12-01/2027-05-31.
- No se toca `live_enabled` (sigue en `false`).
- No se mide nada ni se añaden variantes: `TRIALS.md` sigue en 50.
- No se cambian las puertas, los costes ni los veredictos de H7-H9.
- No se reserva H11. Si H10 falla, no queda familia en el espacio permitido y
  la puerta del 2027-02-26 se resuelve con el informe de cierre.

## 9. Calendario

| Fecha | Hito | Entregable |
|---|---|---|
| **2026-11-27** | Esta revisión | `docs/REVISION-DISENO-H10.md` |
| ~~2026-12-11~~ **2026-11-27** | H10 pre-registrada (adelantada) | `docs/PRE-REGISTRO-H10.md`: 5 variantes y 120 pb congelados |
| ~~2026-12-18~~ **2026-11-27** | H10 archivada sin backtest | `docs/ARCHIVO-H10.md`; cribado 80,51 pb frente a 240 pb |
| **2027-02-26** | Puerta dura de investigación | sin cambios |

La pausa de dos semanas se cerró el **2026-11-27** al escribir el pre-registro,
por indicación explícita y no por conveniencia del calendario. Se mantiene lo
que la pausa protegía: la medida se hizo con las reglas ya congeladas y el panel
cerrado con hash antes de mirar ninguna dispersión, y entre el pre-registro y el
cribado no se tocó ningún umbral ni se añadieron variantes. Lo que no se mantuvo
fue la separación de fechas —las dos cayeron el mismo 2026-11-27, tres semanas
antes del 2026-12-18 previsto—; lo que se gana son semanas de margen antes de la
puerta dura, no semanas más de búsqueda.

## 10. Anexo — de dónde salen los números

- Coste de ida y vuelta de H9: 2 patas × 2 lados × 7 pb = 28 pb sobre 3.125 USD
  = 8,75 USD por episodio. 22 episodios × 8,75 = 192,50 USD, que coincide con
  el archivo.
- Punto de equilibrio: 28 pb / 15,6 días = 1,795 pb/día; × 365 = 6,55 %
  anualizado.
- Carry realizado: 122,37 USD / (22 × 3.125) = 17,8 pb en 15,6 días =
  1,14 pb/día = 4,16 % anualizado.
- H8: (179,90 + 19,20) / 17 = 11,71 USD por episodio sobre 2.500 USD por pata =
  46,8 pb; coste 119/17 = 7,00 USD = 28 pb.
- Anualización sobre capital: H8 +0,32 % / 1,83 a = +0,18 %/año; H9 −0,21 % /
  1,83 a = −0,11 %/año. El capital está ocioso la mayor parte del tiempo; el
  retorno por unidad de nocional desplegado es mejor que el del capital, y aun
  así H9 no cubre costes.
