# Plan de investigación y mejora

Objetivo del ciclo: subir la calidad de la evidencia, no el número del veredicto. Un cambio que
mejore el PF y empeore la reproducibilidad es un retroceso.

Estado de partida: 24 corridas (21 reconstruibles + 3 con registro defectuoso documentado),
3 familias, 12 puertas, gate `runner/verify_all.py` en 5/5. Veredicto: 0 APPROVED.

Regla de trabajo: cada fase termina con el gate en verde y con su hallazgo escrito en
`INFORME_AUDITORIA.md`. Ninguna fase se declara hecha sin salida de comando que lo respalde.

---

## Fase 1 — Universo multi-activo  · HECHA

**Por qué.** El rechazo de la línea de tendencia no es por PF: el 1d tiene PF neto 1,50 con 311
trades. Es por potencia: t 1,66 frente al umbral 3,0, y MinBTL pide 14,6 años cuando hay 6,8.
Con un solo activo la única vía para subir el t-stat es esperar una década. Con cinco activos
correlacionados pero no idénticos, el mismo número de años produce más observaciones
independientes.

**Resultado.** 5 activos descargados y validados (`research/load_multi.py`): BTC, ETH, BNB, XRP,
SOL. 0 gaps y 0 duplicados en los cinco; los huecos de fin de mes de XRP y SOL se rellenaron desde
el archivo diario (7 días cada uno). Ventana común de 4 activos: 2020-02-10 → 2026-10-31, 6,72
años. Manifiesto con hash por fichero en `research/cache/multi_manifest.json`.

---

## Fase 2 — Motor multi-activo  · HECHA

`runner/run_universe.py`: corre la misma spec por activo con el mismo motor, agrega por fecha de
salida y divide el riesgo entre los activos que operan. Reporta métricas por activo, agregado,
stress 2×, y tres correlaciones distintas con el t-stat ajustado por la más conservadora.

---

## Fase 3 — ¿El edge de tendencia es transversal?  · HECHA, resultado negativo en potencia

**Hipótesis.** Si el momentum es un fenómeno de mercado y no de BTC, el Donchian debe tener PF > 1
en la mayoría de los activos.

**Resultado.** Se confirma el edge transversal (BTC 1,50 · ETH 1,78 · BNB 1,64 · XRP 1,00) y se
refuta la utilidad de la ampliación: con correlación de mercado 0,644 entre los cuatro, el t
agregado de 2,85 se queda en 1,67 al descontar la dependencia, prácticamente el 1,66 de BTC solo.
Detalle en E21 del informe.

**Consecuencia.** La vía de ganar potencia con más activos queda cerrada con evidencia. No se
repite con más símbolos: la correlación no baja por añadir primos de BTC.

---

## Fase 4 — Modelo de costes con microestructura  · HECHA, con un error propio corregido

`research/spread_study.py`: spread efectivo desde `aggTrades` con el estimador de Roll, en cuatro
días elegidos por régimen.

**Resultado.** El supuesto de 0,07 bp de medio spread es correcto en calma (medido 0,09-0,16) y se
queda 10 a 19 veces corto en los días de liquidación (hasta 1,30 bp el 2025-10-10). El impacto
sobre el veredicto está acotado a ~0,25 R sobre 146 R y no mueve ninguna puerta, pero el modelo de
costes no tiene término de crisis y el stress 2× no lo representa.

**Error propio.** La primera implementación medía desequilibrio de flujo y devolvía 808 bp. Se
corrigió al estimador de Roll y se añadió una cota de plausibilidad para que un estimador roto
falle en voz alta.

---

## Fase 5 — Métricas que faltaban  · HECHA

`time_in_market`, `trades_per_year` y `r_per_year` en el artefacto y en la ficha de corrida.
Justificación: el PF no distingue una estrategia que opera 3 días al año de una que opera siempre,
y esa diferencia decide si el capital está ocioso.

La primera versión de `time_in_market` sumaba las barras retenidas por cada componente del ensemble
y devolvía 1,0 por construcción; corregido a la unión de barras ocupadas (0,798 real). Quedaron
fuera Sortino, Calmar y turnover.

---

## Fase 6 — Interfaz y documentación  · PARCIAL

`universeCard()` en la vista Runner: tabla por activo con PF, Sharpe, t y MDD, más las tres
correlaciones y el t ajustado. `/api/results` sirve `universe` desde `runner/out-universe/`.
La ficha de corrida cruza el registro con el artefacto para mostrar las métricas nuevas sin que el
registro pierda prioridad.

**Dos defectos propios encontrados aquí.** (a) Las filas defectuosas del verificador no tienen
`diffs` y `verifyCard` hacía `r.diffs.join(...)`: la vista Runner entera se caía con 23 corridas.
Arreglado con `(r.diffs || [])` y estado `omite` para `ok === null`. (b) `.cc-row` usaba etiquetas
de 96 px con `nowrap` y las largas se pintaban encima del valor; añadida la variante `.cc-box.wide`.

**No hecho:** comparación de variantes v1.0.0→v1.4.0 y curva contra buy & hold en la UI.

---

## Estado del plan

| Fase | Estado | Resultado |
|---|---|---|
| 1 · Universo multi-activo | hecha | 5 activos, 0 gaps, ventana 6,72 a |
| 2 · Motor multi-activo | hecha | `run_universe.py`, riesgo repartido |
| 3 · ¿Edge transversal? | hecha | sí (3 de 4), pero **no compra potencia**: t 2,85 → 1,67 |
| 4 · Costes / microestructura | hecha | spread correcto en calma, ×19 en crisis; impacto 0,25 R |
| 5 · Métricas que faltaban | hecha | exposición 79,8% · 45,9 trades/año · 3,01 R/año |
| 6 · UI | parcial | card de universo; falta comparación de variantes |

**Gate:** 5 de 5 · 77 tests · 12 scripts · 23/23 corridas reproducen · 8 artefactos · 96 puertas.

**Veredicto sin cambios:** 0 APPROVED / 7 INCONCLUSIVE / 13 REJECTED. Las cuatro fases nuevas
midieron algo real y ninguna convirtió una estrategia rechazada en aprobada. Eso es el resultado,
no un fallo del proceso.

---

## Lo que este plan no hace

- No sube umbrales ni relaja puertas para que algo apruebe.
- No elige el método de validación que da el número favorable.
- No declara rentabilidad futura.
