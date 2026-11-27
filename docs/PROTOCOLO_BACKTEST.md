# Protocolo de validación (pre-registro)

> **Estado: BORRADOR.** Los umbrales están implementados en `server/gates.py` y
> el sellado del holdout en `server/confirmatory.py`. Este documento se congela
> (`PROTOCOLO_BACKTEST.lock.json`) solo cuando los siete ADR de
> `docs/DECISIONES.md` estén cerrados. Un holdout evaluado con criterios que
> después cambian no es un holdout.

## 1. Secuencia

```
ADR (P0) → DESARROLLO (W1-W6) → PUERTAS G → HOLDOUT (una vez) → DRY-RUN 30d → LIVE
```

Ningún paso se salta. Ningún umbral se ajusta después de ver resultados.

## 2. Ventanas

| Bloque | Uso |
|---|---|
| W1–W6 | Desarrollo: seis bloques consecutivos de igual duración |
| Holdout | Secreto hasta que todas las puertas duras de desarrollo pasen |

Los conteos de sesiones se derivan del calendario real, excluyendo sesiones de
roll. El dataset, su hash y la configuración deben quedar registrados en
`reports/experiments.jsonl` con cada ejecución.

La rejilla de parámetros se evalúa con `server/walkforward.py`:

```bash
python -m server.walkforward --strategy donchian --grid "channel=10,20,40"   --windows 3 --days 20 --out reports/backtest/walkforward-donchian.json
```

Devuelve una fila por combinación con expectativa media, peor ventana y
consistencia (fracción de ventanas positivas). **No elige ganador**: ordenar por
expectativa media y quedarse con el primero es exactamente cómo se sobreajusta
un desarrollo. La tabla sirve para descartar, no para coronar.

## 3. Puertas de desarrollo

Implementadas y medibles con `server/gates.py`:

| ID | Criterio | Umbral por defecto |
|---|---|---|
| G4 | Muestra | ≥ 80 operaciones y ≥ 20 por dirección |
| G5 | Edge | PF ≥ 1,25 y expectativa ≥ +0,10 R |
| G6 | Riesgo | DD ≤ 2 % del capital y peor racha ≤ 8 |
| G9/G10 | Concentración | P&L sin las 5 mejores > 0 y top-5 ≤ 50 % del bruto |
| G11 | Significancia | IC bootstrap 80 % inferior > 0 |
| G13 | Barras ambiguas | ≤ 5 % |
| G8 | Costes duplicados | Re-ejecución con comisión y slippage ×2: PF ≥ 1,0 y expectativa > 0 |
| G2 | Determinismo | Dos ejecuciones con el mismo fingerprint |
| G1/G3/G14 | Integridad del dataset | Validador sin errores + hash reproducible |

G8, G2 y G1/G3/G14 se **miden**, no se estiman: `server/stress.py` re-ejecuta el
backtest con el doble de costes y dos veces con los mismos parámetros, y
`server/integrity.py` valida el dataset y comprueba que su hash sea reproducible.
En `POST /api/backtest/run` vienen activadas por defecto (`stress: true`) y en la
simulación se controlan con `--no-stress`.

Límite explícito de G3: la continuidad de rolls solo se puede verificar con datos
de contratos reales. Sobre una serie continua el informe lo dice
("sin rolls que verificar en este dataset") en vez de dar por bueno algo que no
se comprobó.

Queda **una sola** fila no medible en un backtest completo:

| ID | Por qué | Cómo se mide |
|---|---|---|
| H1-H5 | Holdout | Sellado con `confirmatory.seal_holdout`, una sola vez |

## 4. Holdout

| ID | Criterio |
|---|---|
| H1 | Integridad del dataset del holdout |
| H2 | ≥ 18 operaciones |
| H3 | PF ≥ 1,00 y expectativa ≥ 0,00 R |
| H4 | DD ≤ 2,5 % del capital |
| H5 | Configuración, dataset y código idénticos a desarrollo |

Sellado:

```python
from server.confirmatory import seal_holdout, verify_seal, HoldoutAlreadySealed

seal_holdout(
    "docs/protocolo_backtest.lock.json",
    dataset_path="data/holdout.csv",
    config=settings.model_dump(mode="json"),
    strategy={"id": "…", "version": "…"},
    protocol="PROTOCOLO_BACKTEST v1",
)
```

Un segundo `seal_holdout` sobre el mismo lock lanza `HoldoutAlreadySealed`.
`verify_seal` detecta dataset, configuración o estrategia modificados después
del sellado, y también la edición manual del propio lock.

## 5. Veredicto

| Situación | Veredicto |
|---|---|
| Alguna puerta dura falla | `RECHAZADA` |
| Ninguna falla pero hay puertas no medibles | `INCONCLUSO` |
| Todas las puertas medidas pasan y el holdout pasa | `APROBADA` |

`APROBADA` no autoriza LIVE: habilita el dry-run. LIVE exige además adaptador
implementado, `live_enabled` y confirmación explícita.

## 6. Dry-run

Mínimo 30 días de calendario con datos reales y fills simulados.

| Control | Umbral |
|---|---|
| Desviación de slippage vs backtest | ≤ 10 % |
| Desviación de PF vs backtest | ≤ 10 % |
| Señales perdidas por fallo de feed | 0 no justificadas |
| Divergencia snapshot vs estado persistido | 0 |
| Uptime en horario operativo | ≥ 99 % |

## 7. Registro

Cada ejecución escribe una línea en `reports/experiments.jsonl`:

```json
{"experiment_id": "…", "kind": "backtest", "strategy": {"id": "…", "version": "…"},
 "dataset_id": "…", "config_sha256": "…", "metrics_sha256": "…",
 "verdict": "RECHAZADA", "ts": "…"}
```

Sin esa línea, el resultado es una descripción, no una validación.

## Auditoría de fills contra 1 m

Un backtest puede dar por bueno un precio que la vela de 1 m nunca ofreció. El
flag `--audit-candles` compara las dos patas de cada operación con la vela que
contiene su timestamp y añade `fill_audit` al JSON:

```
python -m server.backtest --dataset data/BTC_1m_2025.csv \
    --config profiles/okx/config.json --audit-candles data/BTC_1m_2025.csv
```

El audit solo es exacto si la corrida usa velas de 1 m: con 15 m, el timestamp
del fill es el inicio de la vela y la de 1 m no cubre todo su recorrido. La
tolerancia sale de `execution.max_slippage_ticks`; un precio fuera del OHLC pero
dentro de ese margen se cuenta como `tolerated`, no como imposible. Las
operaciones con un fill imposible se eliminan y se comparan `pf_before` y
`pf_after`; `pf_drop` mide cuánto baja el PF al quitarlas.

## Paridad backtest ↔ motor

`tests/test_parity.py` ejecuta el mismo CSV por los dos caminos: `run_backtest`
y el motor en modo `paper` consumiendo `CSVFeed`. Compara símbolo, lado, entrada,
salida, unidades, motivo y P&L neto de cada operación, y que el total cuadre al
centavo. Con dos estrategias distintas (referencia y donchian).

Si algún día la investigación y la operación divergen, este test es el que lo
dice. No mide rentabilidad: mide que lo medido sea lo mismo.

## Los umbrales viven fuera del código

Los números de estas puertas están en `config/gates.json`, sección `bot`. No se
escriben aquí ni en `server/gates.py`: un test de contrato
(`tests/test_gates_contract.py`) falla si el fichero y el modelo se separan, y el
motor de estrategias lee la misma sección `research` del mismo fichero. Un
veredicto no puede depender de qué copia se actualizó.
