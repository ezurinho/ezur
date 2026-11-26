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

El perfil actual `profiles/okx/config.json` es `reference v0.1.0` en 15 m,
`fast7`/`slow21`, stop 10 ATR, `rr 1.0`, con
`config_hash 6a599496fbf3a324`. Su evidencia activa es
`data/research/promotion/profile-15m-2026-11-24.json`; no es la corrida antigua
de 105 operaciones.

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

La evidencia activa del perfil (`profile-15m-2026-11-24.json`) tampoco está
promovida: tiene 109 operaciones OOS, PF 1,068 y coste 0,047 R. Ya supera la
muestra mínima de 100, pero sigue bloqueada por el PBO 0,782, el DSR 0,0006 y
el estrés 0,7606. El perfil usa
`"mode": "reduce"` con `"size_factor": 0.25`, no `"mode": "block"`; el bot corre
en paper con el riesgo reducido.

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
tiene 109 operaciones OOS, PF 1,068 y coste 0,047 R. Pasa la muestra mínima
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
dólares, que ya escala con el precio), `min_stop_ticks` a 0 y `soft_brakes: true,
que recorta el tamaño al tocar el drawdown (100 % → 25 % → parada dura al doble)
en vez de cerrar la puerta tras la primera pérdida.
