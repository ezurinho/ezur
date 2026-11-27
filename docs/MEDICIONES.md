# Mediciones fuera de muestra

Cada fila sale de un backtest con `--split 2024-01-01` sobre datos Binance y de
la puerta de promoción (`python -m server.promotion`). Se guardan todas las
mediciones, incluidas las que pierden: si una idea se descarta, queda el número
que la descartó.

Regla de lectura: **ninguna configuración se promueve** hasta cumplir, a la vez,
PF fuera de muestra > 1 con 100+ operaciones, coste ponderado < 0,25 R
(fees totales / riesgo total), PF > 1 con coste duplicado, PBO ≤ 0,2 y
DSR ≥ 0,95 en su ciclo. PBO y DSR salen de `config/gates.json`, el mismo
fichero que lee el motor de estrategias.

El perfil que opera aplica además `risk.max_cost_r = 0,25`: una señal cuyo peaje
de ida y vuelta (comisión + spread) se coma más de un cuarto del riesgo no se
abre, aunque el backtest la hubiera dado por buena.

Las filas de 1 h y 1 d se midieron con el **coste nominal** de entonces
(fees / operaciones / presupuesto), no con el ponderado por riesgo real que
aplica hoy la puerta. El nominal subestima el coste cuando el stop real es más
estrecho que el presupuesto: 0,052 R nominal no es comparable con el 0,4635 R
ponderado del perfil de papel. Las conclusiones de esta tabla sobre coste son
históricas; para un veredicto actual hay que re-medir con `--split`.

## 1 h · BTC

| estrategia | config | IS ops | IS PF | OOS ops | OOS PF | OOS esp. | coste nominal |
|---|---|---|---|---|---|---|---|
| donchian | ch40 · sa1.5 · rr2.0 (la que opera) | 694 | 0.666 | 521 | 0.979 | −0.012 R | 0.025 R |
| donchian | ch20 · sa2.5 · rr1.5 | 675 | 0.701 | 508 | 1.014 | +0.018 R | 0.052 R |
| donchian | ch20 · sa1.5 · rr2.5 | 880 | 0.634 | 567 | 0.996 | +0.008 R | 0.057 R |
| donchian | ch20 · sa1.5 · rr1.5 | 973 | 0.509 | 377 | 0.941 | −0.026 R | 0.056 R |
| cruce + marea | fast9 · slow21 · marea100 | 672 | 0.531 | 406 | 0.859 | −0.099 R | — |
| cruce + marea | fast9 · slow21 · marea200 | 684 | 0.619 | 493 | 0.860 | −0.094 R | — |
| canal + tendencia | ch20 · marea200 | 761 | 0.620 | 554 | 0.969 | −0.019 R | — |
| canal + tendencia | ch40 · marea200 | 605 | 0.671 | 464 | 0.990 | +0.001 R | — |
| fade | p20 · s2.0 · sa1.5 | 1255 | 0.411 | 176 | 0.706 | −0.118 R | — |
| fade | p20 · s2.5 · sa1.5 | 1126 | 0.435 | 180 | 0.586 | −0.222 R | — |

El mejor candidato de 1 h (ch20 · sa2.5 · rr1.5) **no se promueve**. Salida
histórica de la puerta de entonces, que medía el coste nominal:

```
pf_fuera_de_muestra             1.014          > 1.0  si
operaciones_fuera_de_muestra        508         >= 100  si
coste_por_operacion             0.052       < 0.25 R  si
pf_con_coste_duplicado          0.915          > 1.0  NO
pbo_del_ciclo                   0.976         <= 0.2  NO
```

## 1 d · BTC

| config | IS ops | IS PF | OOS ops | OOS PF | OOS esp. | coste nominal |
|---|---|---|---|---|---|---|
| ch20 · sa1.5 · rr2.0 | 66 | 1.293 | 51 | 0.947 | −0.014 R | 0.030 R |
| ch40 · sa1.5 · rr2.0 | 52 | 1.141 | 36 | **1.134** | +0.069 R | 0.028 R |

El diario reduce el coste a la mitad y el PF fuera de muestra mejora, pero
**36 operaciones no demuestran nada** y el PBO del ciclo 1d es 0,976. La puerta
lo rechaza por muestra, no por rentabilidad: para juntar 100 operaciones fuera
de muestra en diario harían falta más de diez años.

## 15 m · BTC · ciclo actual y candidato del perfil

El ciclo actual `CYCLE-BOT-15M` barre cinco variantes de `fast` (4, 5, 7, 10 y
14) sobre el universo de 15 m. Sus cifras actuales son:

- **PBO 0,782** para la selección sobre las cinco variantes.
- **DSR 0,020** para la mejor variante del ciclo (`fast5`). El perfil que opera
  es `fast7`, cuyo DSR específico es **0,0006**.
- **Estrés 2x 0,827** para `fast5`; para `fast7` es **0,7606**. Ninguna de las
  cinco variantes sobrevive al coste duplicado.

Fuente: `data/research/cycles/CYCLE-BOT-15M.json`. El PBO mide el universo; el
DSR y el estrés del perfil se miden sobre su candidato fijo, `fast7`.

### Ciclo extendido a 2026-11-24

El 2026-11-26 se repitió el ciclo con `data/btc_5m.pkl` hasta 2026-11-24
(`CYCLE-BOT-15M-2026-11-24`). El PBO baja a **0,7262** y el DSR de la mejor
variante (`fast5`) sube a **0,0161**, pero sigue lejos de 0,20/0,95; el estrés
2x de `fast5` es **0,8255**, el WFA agrega 501 operaciones OOS con PF **0,8581**
y el CPCV deja **82,22 %** de caminos OOS negativos. No cambia el veredicto.
Ese ciclo usa futuros (`btc_5m.pkl`) y su `candidate` es `null`; no debe
sustituir al ciclo activo sin emparejar estrategia y fuente.

El perfil actual `profiles/okx/config.json` es `reference v0.1.0` en 15 m,
`fast7`/`slow21`, stop 10 ATR, `rr 1.0`, con
`config_hash 6a599496fbf3a324`. Su evidencia activa es
`data/research/promotion/profile-15m-2026-11-24.json`; no es la corrida antigua
de 105 operaciones.

### Re-medida de la evidencia activa (2026-11-26)

La evidencia que usa la puerta se regeneró con las huellas nuevas, sin
promocionar nada. Primero se midió con el modelo de ejecución completo y
después se dejó el slippage por tamaño en 0 (ver más abajo); esta es la corrida
que queda activa:

```
python -m server.backtest --dataset data/BTC_15m_2025_20261124.csv \
    --config profiles/okx/config.json --split 2026-01-01 --gates \
    --out data/research/promotion/profile-15m-2026-11-24.json
```

- `research_hash 27cfe57836921488`, `profile_hash 01c86ce397b02642`,
  `config_hash bfebe1755b9d51a1`.
- 241 operaciones totales, PF 1,024; **109 OOS, PF 1,053, esperanza +0,0347 R,
  P&L +163,70, DD 440,66 y coste 0,047 R**. Las cifras son las mismas que con
  `slippage_ticks_per_100_units = 0.25`: a 1 unidad el término añadía 0,0025
  ticks (0,000025 USD), por debajo de la precisión del fill. El PF OOS baja
  frente a 1,068, pero esa caída no es atribuible al término por tamaño: con 0
  y con 0,25 sale la misma cifra. El bloque de noviembre ya documentado (10
  operaciones, PF 0,365) sigue siendo la explicación registrada del deterioro
  anterior; este cambio no añade una causa nueva.
- La puerta ya no rechaza por formato (`evidencia_de_la_configuracion` deja de
  fallar) y sigue **RECHAZADA** por rendimiento: PF con coste ×2 0,7606, PBO
  0,782 y DSR 0,0006. Modo `reduce` y factor 0,25 intactos.
- Cero rechazos por `max_trades_reached` y cero operaciones topadas por
  unidades.

El artefacto activo (`profile-15m-2026-11-24.json`) se sobrescribió con esta
corrida; la versión anterior a esta re-medida quedó en
`.build/evidence-backup/profile-15m-2026-11-24.pre-slippage0.json`, y la de la
re-medida previa, en
`.build/evidence-backup/profile-15m-2026-11-24.pre-remesa.json`.

### Modelo de ejecución: fees, spread, slippage por tamaño y funding

El perfil de papel cobra `commission_per_unit_side = 0.049` por lado (taker),
`half_spread_bps = 0.07` y un slippage de **1 tick base**, con tope de 5 ticks.
El componente por tamaño (`slippage_ticks_per_100_units`) está en **0**: no hay
profundidad histórica de OKX spot en el repo —la API pública solo sirve libro
vivo y el histórico L2 de OKX es para VIP y futuros/perpetuos—, así que 0,25
ticks/100 u era un supuesto sin calibrar. A 1 unidad aportaba 0,0025 ticks
(0,000025 USD), por debajo de la precisión del fill. Se activará solo cuando
exista un artefacto de calibración con tbbo/mbp-1 y tamaños comparables a los
del bot; hasta entonces, 0. El impacto de libro (`impact_model`) sigue en
`none`: sin profundidad medida, inventar una curva sería precisión falsa.

El funding de perpetuos ya se modela (`funding_rate_bps_8h`, positivo = el largo
paga) en cada frontera de 8 h UTC. El perfil activo es **spot**, así que
`funding = "none"` y tasa 0: no se cobra un funding que el instrumento no
tiene. Cuando se mida un perpetual, se activa sin tocar el resto. Los supuestos
están en el hash de investigación: cambiar cualquiera exige re-medir, no
re-interpretar.

### Histórico: 105 / 1,308 / 0,049 no es evidencia del perfil actual

La tabla siguiente es histórica. Sale de
`data/research/promotion/reference-15m-paper-regime-rr10-stop10.json`, medido
con el hash **`5b125857cfeb46f2`**, no con el perfil actual
(**`6a599496fbf3a324`**). La puerta evalúa
`evidencia_de_la_configuracion` y la rechaza por ese hash: **105 operaciones,
PF 1,308 y coste 0,049 R no son válidos para justificar el perfil actual** y no
se usan para promoverlo. Tampoco son la evidencia activa del panel.

Esa corrida antigua usaba `config/okx-15m-paper-regime.json`, no
`profiles/okx/config.json`:

| corrida | ops | acierto | PF | esperanza | P&L neto | P&L bruto | fees | DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| completa, 1× coste | 233 | 56,7 % | 1,204 | +0,092 R | +5.327,74 | +7.693,36 | 2.365,62 | 3.755,53 |
| fuera de muestra | 105 | — | 1,308 | +0,132 R | — | — | — | — |
| fuera de muestra, coste ×2 | 105 | — | 1,184 | — | — | — | — | — |

El histograma de resultados de esas 233 operaciones explica por qué el corte no
basta: caen en dos barras, 132 cerca de +0,95 R y 101 cerca de −1,03 R. Es una
apuesta 1:1 con un 56,7 % de acierto cuando el empate está en 52,6 % (coste
incluido); con 233 tiradas la diferencia es z ≈ 1,4, y el IC80 de la esperanza
(0,007 R) roza el cero. **No se distingue del ruido.**

Se reprodujo con el motor de entonces:

```
python -m server.backtest --dataset data/BTC_15m_2025.csv \
    --config config/okx-15m-paper-regime.json --split 2026-01-01 \
    --out data/research/promotion/reference-15m-paper-regime-rr10-stop10.json
```

Ese ciclo de selección solo se pudo medir en su propio marco cuando `bars_for`
aprendió a resamplear a 15 m (pandas 3 retiró el alias de minutos); antes no
existía. Su PBO 0,441 corresponde a una regeneración anterior del ciclo, no al
0,782 que manda hoy.

La evidencia activa del perfil (`profile-15m-2026-11-24.json`) tampoco está
promovida: tiene 109 operaciones OOS, PF 1,053 y coste 0,047 R (re-medida el
2026-11-26). Ya supera la
muestra mínima de 100, pero sigue rechazada por el PBO 0,782, el DSR 0,0006 y
el estrés 0,7606. El perfil usa
`"mode": "reduce"` con `"size_factor": 0.25`, no `"mode": "block"`; el bot corre
en paper con el riesgo reducido.

### Tope de 4 operaciones diarias: no recorta la muestra

`config/okx-validation.json` y el perfil de papel fijan `max_trades_per_day = 4`.
La corrida de 15 m con ese perfil de validación da **109 operaciones OOS y
ningún rechazo `max_trades_reached`** en `diagnostics.rejections`: ninguna señal
se quedó fuera por el tope diario, así que el límite no truncó la muestra ni
explica su tamaño. Subirlo tampoco añade operaciones —con 8 al día salen las
mismas 109— y bajarlo solo recortaría días que hoy no existen. Quien quiera
mover este número debe traer una corrida que muestre rechazos por ese código;
hoy no hay ninguno.

Cuidado con el nombre: `trades_at_cap: 0`/`cap_rate: 0.0` **no** miden el tope
diario, sino las operaciones cuyo tamaño tocó `max_units_per_trade` (300
unidades). El artefacto de referencia
(`data/research/promotion/profile-15m-2025-2026-years.json`, `config_hash
6a599496fbf3a324`, sobre `data/BTC_15m_2025.csv`) también los deja en 0, pero eso
habla del tope de tamaño. El tope diario se expone como
`trades_blocked_by_daily_cap` y su cómputo se prueba con rechazos sintéticos,
sin depender de `data/`.

La caída del PF OOS de **1,18198 a 1,06750** se explica por las 10 operaciones
cerradas en noviembre: 3 ganadoras y 7 perdedoras, PF **0,3651**, esperanza
**−0,4578 R**, P&L **−276,23** y DD local **277,49**. El DD máximo OOS no cambia
(**440,16**): el bloque nuevo diluye el PF, no empeora el drawdown. Detalle:
`data/validation/profile-15m-2026-11-nov-trades.json`.

La puerta de promoción falla estrés, PBO y DSR. En el bloque OOS también fallan
G5, G9/G10 y G11. El G6 que aparece en el `gates` del artefacto es de la corrida
completa (DD 947,26), no del OOS (DD 440,16).

## El stop mínimo, medido en 1 m

`risk.min_stop_ticks` rechaza una señal cuyo stop quede más cerca que N ticks de
la entrada (0 = apagado, el valor por defecto). Sobre las velas de 1 m, con
15.000 ticks (150 $ con tick de 0,01):

| corrida | ops | acierto | PF | P&L neto | P&L bruto | fees | peor racha |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 m base | 5.149 | 42,2 % | 0,476 | −144.328,79 | +7.051,81 | 151.380,60 | 27 |
| 1 m con mínimo 15.000 ticks | 4.769 | 45,5 % | 0,512 | −139.734,55 | +474,05 | 140.208,60 | 11 |

El filtro quita las señales con el stop más pegado, que es justo lo que el ruido
barre, y mejora PF y racha. Pero **el coste sigue siendo la estrategia**: las
comisiones (151.381 y 140.209) se comen un bruto que era positivo. En 1 m no hay
borde que pague operar; el freno se queda como parámetro, no como rescate.
## Lo que dicen los números juntos

- El coste no es el asesino principal: bajarlo de 0,05 R a 0,03 R no cambia la
  conclusión.
- Ninguna familia de señal de precio probada gana fuera de muestra con muestra
  suficiente.
- Tocar parámetros sobre las mismas señales solo produce candidatos que mueren
  al duplicar el coste o al mirar su PBO.

La siguiente idea tendría que ser otra fuente de señal, no otra rejilla.

## La configuración que opera, medida

`profiles/okx/config.json` opera `reference v0.1.0` con **velas de 15 m**: el
feed de OKX llega en 1 m (`bar=1m`) y el motor lo agrupa antes de evaluar
(`strategy.timeframe`). El perfil **no está promovido**: su evidencia activa
tiene 109 operaciones OOS, PF 1,053 y coste 0,047 R (re-medida el 2026-11-26
con el modelo de ejecución actual). Pasa la muestra mínima
de 100, pero falla el PBO 0,782, el DSR 0,0006 y el estrés 0,7606. Por eso usa
`"mode": "reduce"` con `"size_factor": 0.25` y el bot corre en paper con el
riesgo reducido; no está en `"mode": "block"`. La medición con el perfil
anterior de 1 minuto:

| dataset | IS ops | IS PF | OOS ops | OOS PF | coste |
|---|---|---|---|---|---|
| BTC 1 m 2025-01..2026-10, corte 2026-01-01 | 234 | 0.447 | 0 | — | 0.038 R |
| el mismo con coste ×2 | 139 | 0.219 | 0 | — | 0.073 R |

```
python -m server.backtest --dataset data/BTC_1m_2025.csv   --config profiles/okx/config.json --split 2026-01-01   --out data/research/promotion/reference-1m-1x.json
```

No hay operaciones fuera de muestra porque **no llega**: el freno duro de
drawdown (5 % × 2 = 10 %) se dispara dentro de la muestra y, al no abrir más
operaciones, la equity no puede recuperarse. Quedan 51.858 rechazos por
`max_drawdown_reached` y la corrida termina ahí. En 1 h la config tampoco es
evaluable: el tope `max_stop_ticks 40000` (400 USD fijos, no escala con el
precio) rechaza 3.108 señales y deja 1 operación fuera de muestra.

Conclusión de aquella corrida: en 1 m la config perdía 0,404 R por operación y
el freno duro de drawdown necesitaba reiniciarse a mano con
`python -m server.equity --profile profiles/okx --reset-peak` (con copia y
evento), o el bot se quedaba parado para siempre en cuanto lo tocaba. El perfil
actual ataca las dos causas por otra vía: `max_stop_ticks` a 400.000 (cuatro mil
dólares, que ya escala con el precio), `min_stop_ticks` a 0 y `soft_brakes: true`,
que recorta el tamaño al tocar el drawdown (100 % → 25 % → parada dura al doble)
en vez de cerrar la puerta tras la primera pérdida.

## 2025 completo · el perfil de OKX, con la comisión cobrada una vez

Las mediciones anteriores de este documento tienen dos defectos de método: el
perfil de OKX pagaba la comisión de bolsa dos veces por lado (~10,6 pb en vez de
~5,6, ver ADR 0.16) y las corridas no registraban el intervalo ni los overrides,
así que no se podían repetir. Esta tabla se midió con el coste corregido y deja
las entradas por escrito.

Perfil `profiles/okx/config.json`, velas de Binance Vision 2025-01 → 2025-12,
corte IS/OOS 2025-07-01 y `strategy.timeframe` fijado en los overrides. Lanzada
con el workflow `backtest` el 25 nov 2026 sobre el commit `de56339b`.

| marco | ops | PF | bruto | fees | neto | DD | coste | IS ops | IS PF | OOS ops | OOS PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 m | 927 | 0,826 | +418,17 | 2.547,16 | −2.128,98 | 2.477,62 | 0,121 R | 490 | 0,867 | 437 | 0,724 |
| 15 m | 132 | 1,030 | +361,84 | 254,22 | +107,61 | 947,26 | 0,037 R | 67 | 0,786 | 65 | 1,451 |
| 1 h | 41 | 0,612 | −527,70 | 84,42 | −612,12 | 616,13 | 0,039 R | 19 | 0,691 | 22 | 0,544 |

Identidad de los datos (`dataset_id` del informe): 1 m
`4fbd7c9349d2e93f…`, 15 m `8b5808d2a4364da9…`, 1 h `46a740f54f7d8497…`.
Filas: 525.600, 35.040 y 8.760; 365 sesiones en los tres casos.

La comisión ya se cobra una vez: una unidad paga 0,0496 USD al entrar (0,049 de
comisión más medio spread), 5,6 pb sobre un nocional de 88.300 USD por unidad.
Antes pagaba 0,0941 USD, 10,6 pb.

**Qué dicen estas filas.**

- En 1 m las comisiones (2.547) multiplican por seis el bruto (418). Ningún
  arreglo de infraestructura cambia el signo: ese marco no paga el peaje.
- En 15 m el neto es positivo y el fuera de muestra también, pero son 65
  operaciones fuera de muestra con un PF dentro de muestra de 0,786. Es una
  corrida, no un candidato: faltan el PBO de su ciclo y el coste duplicado.
- En 1 h la muestra (41 operaciones) no permite concluir nada. El PF 0,612
  describe esta corrida.
- **Ninguna fila es comparable con las de arriba.** Aquellas no registraron
  overrides y el motor cambió desde entonces (tope de coste por operación,
  presupuesto de riesgo reaplicado al fill real). Que el PF de 1 h pase de
  1,183 a 0,612 no mide el efecto de la comisión: mide dos configuraciones
  distintas.
