# Entrega — auditoría del prompt «Elite Quant V3» + versión corregida

## Archivos

| Archivo | Qué es |
|---|---|
| `INFORME_AUDITORIA.md` | Auditoría completa: 20 errores, tabla de veredictos, resultados reales, puertas de aprobación, fórmulas y 36 fuentes con URL. |
| `PROMPT_V4.md` | System prompt corregido, listo para usar. Spec-first, contrato con runner determinista, puertas numéricas, dry-run con criterio estadístico. |
| `resumen.html` | Página con los gráficos y la tabla de puertas (se renderiza en el chat). |
| `research/load_data.py` | Descarga y valida BTCUSDT 5m desde `data.binance.vision`. |
| `research/study_costs.py` | Motor + 17 configuraciones en 5m, escenarios de coste, PBO/DSR. |
| `research/funding_study.py` | 4h/1d con funding real, PBO/DSR/MinBTL, walk-forward, desglose anual. |
| `research/export_charts.py` | Curvas mensuales e IC del PF por block bootstrap. |
| `research/build_registry_seed.py` | Genera la semilla del registro (`registry_seed.json`) desde las corridas reales. |
| `research/cache/*.json` | Resultados de todas las corridas (evidencia citada en el informe). |
| `runner/strategy_spec.schema.json` | JSON Schema (2020-12) del `strategy_spec` de `PROMPT_V4` §1.1. |
| `runner/run_strategy.py` | Runner determinista: valida la spec, ejecuta el backtest, evalúa las 12 puertas y escribe `result.json`. |
| `runner/selection_cycle.py` | Ciclo de selección: PBO (CSCV), DSR, MinBTL y walk-forward sobre un universo de specs. |
| `runner/verify_registry.py` | Re-ejecuta cada corrida registrada desde sus parámetros y compara con lo almacenado. |
| `runner/verify_all.py` | Gate único: sintaxis, tests, reproducción, puertas y coherencia del ciclo. |
| `runner/validation/*.json` | Mediciones del ciclo, citables; el runner las consume. |
| `runner/validation/sensitivity/` | Prueba con las 19 corridas como universo; documental, no canónica. |
| `runner/test_runner.py` | 66 tests deterministas del motor, las métricas, el ciclo y el verificador. |
| `runner/specs/*.json` | Specs ejecutables de referencia (1d/4h Donchian, 5m EMA) que reproducen las corridas registradas. |
| `runner/out/*.json` | `result.json` por spec, citables con rutas (`result.json#/metrics/oos/...`). |
| `app/server.py` | Interfaz gráfica: servidor HTTP + SQLite append-only, solo stdlib. |
| `app/ui/` | Frontend vanilla (`index.html`, `app.js`, `style.css`), sin build. |
| `app/registry.db` | Registro local; se siembra solo en el primer arranque. |

## Reproducir

```bash
cd research
python load_data.py         # ~82 ficheros mensuales, 718.848 barras, 0 gaps
python study_costs.py       # tabla 5m + PBO/DSR (taker, maker, stress)
python funding_study.py     # 4h/1d neto de fees + funding, WFA
python export_charts.py     # datos de la página resumen
```

Requiere `numpy`, `pandas` (probado con 2.5.5 / 3.1.1, Python 3.14). Semilla 7 en las simulaciones.

## Runner determinista (la IA no calcula métricas)

`PROMPT_V4` prohíbe que el modelo produzca números: los produce el runner y la IA solo los cita.
Este runner implementa ese contrato.

```bash
python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json
python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json --dry-run
python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json \
    --register http://127.0.0.1:8787     # además hace POST /api/runs
```

Qué hace, en orden:

1. Valida la spec contra `runner/strategy_spec.schema.json` (tipos, enums, patrones, campos obligatorios).
2. Comprueba la integridad del dataset congelado y anota `data_hash` (sha256 del 5m).
3. Resamplea al `timeframe_signal` (nunca usa datos que no estén en el original).
4. Genera señales con barras cerradas y aplica el modelo de ejecución de §3: fill en `open[t+1]`,
   stop-first intrabar, gap al `open`, time stop, coste y funding en R.
5. Calcula métricas por tramo (todos / IS 60% / OOS 20% / reserva 20%), IC95% del PF por
   bootstrap de bloques, stress 2×, break-even de coste, plateau ±10/±20% y alpha vs BTC.
6. Evalúa las 12 puertas de §6. Las que necesitan el ciclo completo de selección (PBO, DSR,
   MinBTL, WFA) quedan en `null` y se listan en `missing_artifacts`: el veredicto baja a
   `INCONCLUSIVE`, nunca se inventa la cifra.
7. Escribe `runner/out/<id>-v<version>.json` con `spec_hash`, `data_hash`, `code_sha`, `seed`.

Reglas soportadas por el motor: `donchian_breakout`, `ema_state`, `zscore_fade`, `orb_session`.
Añadir una regla es un cambio de código y por tanto un bump de versión.

### Reproducibilidad verificada

Los tres specs de referencia reproducen exactamente las corridas ya registradas en SQLite
(nº de trades y PF neto al tercer decimal):

| Spec | Trades | PF neto | IC95% PF | MDD | Verificado contra |
|---|---|---|---|---|---|
| `btc-trend-1d-donchian-40` | 58 | 1,683 | 0,912–2,685 | −4,6% | `BTC-TREND-1D-v1.0.0-1d_40` |
| `btc-trend-4h-donchian-24` | 524 | 1,055 | 0,843–1,276 | −15,3% | `BTC-TREND-4H-v1.0.0-4h_24` |
| `btc-mom-5m-ema-12-48` | 15.102 | 0,490 | 0,472–0,509 | −100,0% | `BTC-MOM-5M-v1.0.0-ema_12_48` |

### Hallazgo de la verificación

Al reproducir las corridas, el runner detectó que el registro declara `params.atr_k = 2.0` para
las variantes 4h/1d, pero el motor `sc.run_trades` toma la distancia de stop de la entrada e
**ignora** `Exit.k_atr`: todas las corridas del estudio usaron **1,5 × ATR(14)**. Las métricas
del registro son correctas (son las de 1,5); el metadato era el que no coincidía. Corregido en
`build_registry_seed.py` y anotado en el log del registro.

### Veredicto del registro y del runner

El runner evalúa 12 puertas; el registro solo puede evaluar las que están en la tabla `runs`
(PF, IC, t, trades, coste 2×, MDD, funding). Cuando `POST /api/runs` recibe `alpha_annual` y
`plateau_pass`, el servidor añade esas dos puertas y recalcula el veredicto con la misma regla
que el runner, de modo que ambos coinciden.

Si el veredicto enviado (`runner_verdict`) difiere del recalculado, el servidor **no lo oculta**:
responde con `conflict` y escribe un evento `audit` en el log. Las tres corridas históricas
anteriores al runner conservan su veredicto original (registro append-only) y la vista Runner
marca la discrepancia — hoy solo en `BTC-TREND-1D-v1.0.0-1d_40`, que el registro dejó en
`INCONCLUSIVE` porque no podía ver el alpha de −72,8 %.

### Ciclo de selección (PBO / DSR / MinBTL / WFA)

Estas cuatro puertas no se pueden calcular con una sola spec: describen una **selección**. Las
produce `runner/selection_cycle.py`, que ejecuta un universo declarado de configuraciones y
escribe `runner/validation/<CYCLE>.json`.

```bash
python runner/selection_cycle.py                       # universo por defecto (15 configs)
python runner/selection_cycle.py --register http://127.0.0.1:8787   # además POST /api/cycles
python runner/selection_cycle.py --spec runner/specs/btc-trend-1d-donchian-40.json --param N
```

Método:

| Puerta | Cómo se calcula |
|---|---|
| PBO | CSCV (Bailey, Borwein, López de Prado, Zhu 2015): matriz de retornos diarios, 10 bloques contiguos, las 252 particiones de 5+5, config ganadora in-sample y su rango out-of-sample. PBO = fracción con logit ≤ 0. |
| DSR | Deflated Sharpe (Bailey & López de Prado 2014) contra el máximo Sharpe esperado de N trials, ajustado por skew y kurtosis. Se calcula **dentro del grupo de variantes de cada hipótesis**, que es el espacio de búsqueda real. |
| MinBTL | `2·ln(N)/SR²` en años, comparado con la cobertura del dataset. |
| WFA | 5 folds con 30 % de calentamiento, ventana expansiva: en cada fold se elige la config con mejor PF in-sample y se mide su PF y su número de trades out-of-sample. |

El runner las consume automáticamente desde el artefacto más reciente (`--validation` para fijar
uno concreto) y las publica en `result.json#/validation`. Si el artefacto se calculó con otro
dataset (`data_hash` distinto), el runner lo descarta en vez de mezclar.

Resultado del ciclo registrado (`CYCLE-2026-11-selection`):

| Puerta | Valor | Umbral | Resultado |
|---|---|---|---|
| PBO | 0,238 | ≤ 0,20 | falla |
| DSR | 0,792 | ≥ 0,95 | falla |
| MinBTL | 14,6 años | ≤ 6,8 disponibles | falla |
| Trades/fold (WFA) | 6 | ≥ 30 | falla |

Con las 12 puertas ya evaluadas, los tres specs pasan de `INCONCLUSIVE` a `REJECTED` con razones
medidas. El mejor Sharpe del universo (1d Donchian 40, 0,61 anual) necesita 14,6 años para
distinguirse del ruido de 15 configuraciones, y solo hay 6,8.

## El registro entero se reproduce

El registro almacena métricas; el motor las produce. Son dos piezas independientes, y nada
garantiza que coincidan. `verify_registry.py` cierra esa brecha: reconstruye cada corrida desde
sus propios `params`, la re-ejecuta y compara.

```bash
python runner/verify_registry.py                 # las 19 corridas
python runner/verify_registry.py --id BTC-MR     # un subconjunto
python runner/verify_registry.py --json out.json # informe para máquinas
python runner/verify_registry.py --record http://127.0.0.1:8787   # anexa la medición al log
```

```
19/19 corridas reproducen al dígito
```

| Familia | Corridas | PF neto |
|---|---|---|
| Donchian | 10 | 0,643 – 1,683 |
| EMA | 3 | 0,490 – 0,530 |
| Reversión z=2 | 3 | 0,478 – 0,537 |
| ORB | 3 | 0,624 – 0,746 |

Conteo de trades exacto; PF, MDD y t-stat con tolerancia de 0,0015 (el registro redondea a tres
decimales). El verificador **no** lee `runner/out/` ni el artefacto del ciclo: parte de la base de
datos y del motor, que es lo que hace la comprobación significativa.

De paso confirma el diagnóstico E15: el motor siempre ejecutó `1.5·ATR`, aunque el metadato de
4h/1d declare `2.0`. El verificador usa el valor ejecutado y lo deja explícito en el informe
(`atr_k_executed`).

### ¿Alguna bate a comprar y mantener?

No. El verificador mide el exceso de retorno fuera de muestra contra buy & hold:

```
0 baten · 6 sin concluir · 13 pierden
a igual riesgo: 0 baten · 7 sin concluir · 12 pierden
```

| Configuración | α anual | α con vol igualada |
|---|---|---|
| 1d Donchian 55 | −63,1% | −28,6% (×17,5) |
| 1d Donchian 40 | −72,8% | −71,0% |
| 4h Donchian 24 | −76,8% | −64,7% |
| EMA 12/48 | −558,4% | −652,4% |

La segunda columna escala la serie diaria por σ(B&H)/σ(estrategia): responde a la pregunta honesta
—al mismo riesgo, ¿la regla bate al activo?— en vez de castigar a la estrategia por arriesgar 0,5%
por operación. Aun así no hay ninguna que apruebe.

## Prueba de sensibilidad del universo

¿Y si el espacio de búsqueda no fueron 15 vecindades sino las 19 corridas registradas? Se puede
medir:

```bash
python runner/selection_cycle.py --from-registry --cycle CYCLE-2026-11-full \
  --out runner/validation/sensitivity
```

| Puerta | Canónico (15) | Registro (19) |
|---|---|---|
| PBO | 0,238 | 0,000 |
| DSR | 0,792 | 0,843 |
| SR₀ anual | 0,34 | 0,28 |
| MinBTL | 14,6 años | 15,8 años |

**El PBO de 0,000 es un artefacto, no robustez.** Nueve de las 19 configuraciones pierden en todos
los bloques, así que la ganadora in-sample gana también fuera de muestra por eliminación. El CSCV
necesita un universo homogéneo para informar; por eso el ciclo canónico mantiene vecindades
paramétricas y este artefacto vive en `runner/validation/sensitivity/`, fuera del glob que consume
el runner.

Lo que sí aporta es el DSR por grupo, que ordena los marcos temporales: 1d 0,843 · 4h 0,573 ·
5m 0,000 con Sharpe anual negativo en todas sus familias.

## Un comando que comprueba todo

Antes de citar cualquier cifra:

```bash
python runner/verify_all.py            # todo (~2 min)
python runner/verify_all.py --quick    # sin re-ejecutar las 19 corridas
```

```
  ok   sintaxis  9 py · 1 js
  ok   tests     66 tests, 1.964s OK
  ok   registro  19/19 corridas reproducen al dígito
  ok   puertas   3 artefactos · 36 puertas evaluadas
  ok   ciclo     CYCLE-2026-11-selection · data 80d6a6014eb92b23 · PBO 0.2381 · DSR 0.7917

5 de 5 comprobaciones pasan          # exit 0
```

Comprueba: que todo el Python y el JS compilen, que los tests pasen, que las 19 corridas
reproduzcan, que ningún artefacto tenga puertas sin evaluar, y que el ciclo citado por los
artefactos sea el mismo que el que se midió y sobre el mismo `data_hash`.

En su primera ejecución encontró tres defectos que los tests no podían ver: un script del proyecto
que no compilaba, artefactos que nombraban un ciclo distinto del que los juzgó, y un endpoint que
degradaba auditorías a notas cuando el campo `type` venía mal escrito. Los tres están corregidos y
anotados como E19 en el informe.

## Tests

```bash
cd runner && python test_runner.py      # 66 tests, sin red y sin base de datos
```

Cubren las piezas que producen los números publicados: cuantil normal, Sharpe desde sumas,
profit factor, modelo de fill (`open[t+1]`, stop-first, gap al open, sin solapes), PBO por CSCV
(0 con una config dominante, alto con ruido puro, 252 particiones con 10 bloques), DSR (baja con
más trials, sube con más señal, acotado a [0,1]), MinBTL (monótono en N y en SR, contrastado con
el ciclo semilla), walk-forward (sin folds vacíos, totales consistentes), vecindades de specs
(sin mutar el original), segmentación por regímenes (los tramos deben sumar los trades) y el
verificador (mapeo familia → regla, `atr_k` ejecutado vs declarado, tolerancias del comparador).

El test de regímenes existe porque un bug real pasó por alto el conteo: el tercer tramo usaba
`>= q1` en vez de `>= q2` y se llevaba dos tercios de la muestra.

## Interfaz gráfica (registro del proyecto)

```bash
python app/server.py --port 8787        # http://127.0.0.1:8787
```

Requisitos: Python 3.10+ y nada más (stdlib). La BD se crea en `app/registry.db` y se siembra la
primera vez desde `research/cache/registry_seed.json`; a partir de ahí la BD es la fuente de verdad.

| Vista | Contenido |
|---|---|
| Resumen | KPIs, ciclo vigente con sus puertas, pipeline de 12 pasos, familias y últimas corridas. |
| Estrategias | Hipótesis, reglas, riesgos y todas las corridas de cada estrategia. |
| Corridas | Tabla filtrable; detalle con puertas, métricas, parámetros, costes, artefactos y curva de capital. |
| Runner | Ciclo de selección (PBO/DSR/MinBTL/WFA con su universo y folds) y los artefactos de `runner/out`: puertas de §6, tramos IS/OOS/reserva, stress, break-even, plateau y alpha. |
| Log auditable | Eventos con timestamp; solo se anexan. |
| Proyecto | Dataset, gobernanza, hashes de los artefactos y contrato de la API. |

API: `GET /api/state`, `GET /api/health`, `GET /api/export`, `GET /api/results`, `POST /api/runs`, `POST /api/events`, `POST /api/cycles`.

`/api/health` no solo dice que el proceso vive: reporta si el registro se sigue reproduciendo. No
lanza ningún backtest — lee los artefactos ya escritos, así que se puede sondear sin coste.

```json
{
  "ok": true, "runs": 19,
  "integrity": {
    "verified": 19, "failures": 0,
    "data_hash": "80d6a6014eb92b23",
    "artifacts_unknown_gates": 0,
    "cycle_matches_artifacts": true,
    "cycle": "CYCLE-2026-11-selection"
  }
}
```

`POST /api/runs` recalcula puertas y veredicto en el servidor: el cliente no puede declarar
`APPROVED`. Si al ciclo le falla PBO o DSR, ninguna corrida puede quedar aprobada. Un `run_id`
repetido devuelve `409` (registro append-only). Métricas incompletas devuelven `400`. Cuando el
payload trae `alpha_annual`, `plateau_pass`, `pbo`, `dsr` y `wfa_min_trades`, el servidor añade
esas puertas y aplica la misma regla de rechazo que el runner; si el veredicto enviado difiere,
responde con `conflict` y escribe un evento `audit`.

`POST /api/cycles` registra una medición de ciclo y **no se cree las cifras**: exige el
`validation_ref` del artefacto y rechaza el alta con `409` si algún número no coincide con el
fichero citado.

```bash
curl -X POST http://127.0.0.1:8787/api/runs   -H "Content-Type: application/json" -d @run.json
```

## Salida verificada de `load_data.py`

```
rows=718,848  span=2020-01-01 00:00:00+00:00 -> 2026-10-31 23:55:00+00:00  dupes=0
expected_bars=718,848  missing_bars=0
gaps>5m: []
price_last=77,522.60  price_min=3,621.81  price_max=126,208.50
```

## Cifras clave (todas del estudio propio)

| Métrica | Valor |
|---|---|
| 5m, expectativa bruta de las 4 familias | ≈ 0 R |
| 5m, PF neto con taker 10,14 bp RT | 0,49–0,75 |
| Coste por trade en 5m (stop ATR 1,5×) | 0,18–0,36 R |
| 1d Donchian 40, PF bruto → fees → fees+funding | 1,877 → 1,833 → 1,683 |
| 1d Donchian 40, trades / Sharpe / t-stat | 58 / 0,61 / 1,60 |
| PBO (8 configuraciones) | 0,50 |
| DSR del mejor | 0,58 (umbral 0,95) |
| MinBTL vs. historia | 11,2 años vs. 6,8 |
| Trades OOS en walk-forward | 11 en 2 folds |
| Funding: media / % positivo / máximo anual | 0,0106% por 8h / 86% / +30,6% (2021) |
| BTC buy & hold | CAGR 41,7% · Sharpe 0,89 · MDD −76,7% |

## Advertencias

- No se ejecutó nada en vivo: `fapi.binance.com` devuelve HTTP 451 desde este entorno. Los datos son del archivo público.
- El estudio es un banco de pruebas de costes y potencia estadística, no una estrategia recomendada.
- El slippage por fill no se midió (no hay L2 completo del histórico); se modeló con tick, medio spread y ley de raíz cuadrada.
- Los resultados no se extrapolan a otros activos, exchanges ni periodos.
