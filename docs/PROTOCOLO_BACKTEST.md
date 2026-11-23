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

G8 y G2 se **miden**, no se estiman: `server/stress.py` re-ejecuta el backtest con
el doble de costes y dos veces con los mismos parámetros. En `POST /api/backtest/run`
vienen activadas por defecto (`stress: true`) y en la simulación se controlan con
`--no-stress`.

Declaradas como **no medibles** en una ejecución concreta:

| ID | Por qué | Cómo se mide |
|---|---|---|
| G1/G3/G14 | Integridad de dataset, rolls y duplicados | Validador de CSV + hash del dataset |
| H1-H5 | Holdout | Sellado con `confirmatory.seal_holdout` |

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
