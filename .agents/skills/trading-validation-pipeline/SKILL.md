---
name: trading-validation-pipeline
description: "Recorre la escalera de validación de ezur: dataset, backtest con puertas, walk-forward, holdout sellado, coste duplicado, promoción y dry-run. Incluye la puerta por hash de configuración y el puente al motor IA de estrategias. Úsala para decidir si una estrategia sirve, preparar evidencia de promoción, interpretar un veredicto o revisar un protocolo de backtest."
version: 1.1.0
---

# Validación y promoción

## Cuándo usarla

Antes de decir que una estrategia «funciona»; antes de subir tamaño o pasar a dry-run;
cuando haya que interpretar `RECHAZADA`/`INCONCLUSO`/`APROBADA`; cuando se prepare el
JSON de evidencia para la puerta de promoción.

Para escribir el plugin, usa `trading-strategy-plugin`. Para operar, `trading-bot-ops`.
Para el motor de investigación con IA (spec, runner determinista, PBO/DSR/WFA), usa
`trading-ai-strategy-engine`; sus números y puertas no son los del bot.

## La escalera

```text
dataset validado → backtest con puertas → walk-forward (W1-W6) → holdout (una vez)
→ coste x2 + determinismo → promoción → dry-run 30d → LIVE
```

Ningún paso se salta. Ningún umbral se ajusta después de ver resultados. El holdout
se sella antes de mirarlo y no se vuelve a abrir.

## 0. Dataset

```powershell
python -m server.datasets list
python -m server.datasets pull --profile profiles/okx --bars 5000
python -m server.datasets resample --input data/dataset_1m.csv --output data/dataset_1h.csv --rule 1H
```

El CSV que vale es `ts,symbol,o,h,l,c,v`, ordenado y alineado. Un dataset sintético
sirve para probar el pipeline, no para validar rentabilidad. Guarda el SHA-256: la
evidencia y el holdout lo referencian.

## 1. Backtest con puertas

```powershell
python -m server.backtest --dataset data/dataset_1h.csv --config profiles/okx/config.json `
  --strategy my_strategy --params '{"period": 20}' --gates --split 2025-01-01 `
  --years --json --out reports/backtest/my_strategy-gates.json
```

`--split` marca el corte in-sample/out-of-sample. `--gates` evalúa G4-G13 y deja el
detalle por puerta en el JSON. `--years` enseña años perdedores que un total esconde.

Lee el veredicto y, sobre todo, las puertas **no medibles**: un `INCONCLUSO` no es un
aprobado. `tests/test_gates_contract.py` fija que los umbrales de `config/gates.json`
y el modelo no se separen.

## 2. Walk-forward

```powershell
python -m server.walkforward --strategy my_strategy --grid "period=10,20,40" `
  --windows 3 --days 20 --out reports/backtest/walkforward-my_strategy.json
```

Devuelve una fila por combinación con expectativa media, peor ventana y consistencia.
**No elige ganador**: ordenar por expectativa y quedarse con el primero es cómo se
sobreajusta. La tabla sirve para descartar, no para coronar.

## 3. Holdout: se sella una vez

```python
from server.confirmatory import seal_holdout, verify_seal, HoldoutAlreadySealed

seal_holdout(
    "docs/protocolo_backtest.lock.json",
    dataset_path="data/holdout.csv",
    config=settings.model_dump(mode="json"),
    strategy={"id": "my_strategy", "version": "0.1.0"},
    protocol="PROTOCOLO_BACKTEST v1",
)
```

El lock guarda hashes de dataset, configuración y estrategia. `verify_seal` detecta
cambios posteriores y también la edición manual del lock. Un segundo `seal_holdout`
lanza `HoldoutAlreadySealed`: no hay «segunda pasada» sin incidente registrado.

## 4. Coste duplicado y determinismo

```powershell
python -m server.simulation --days 60 --bars 390 --strategy my_strategy `
  --out reports/backtest/sim-60d.json
```

La simulación re-ejecuta por defecto para medir G8 (comisión y slippage x2) y G2
(mismo fingerprint). `--no-stress` lo apaga: no lo uses para promocionar.
`server/stress.py` hace la re-ejecución; `server/integrity.py` valida el dataset y su
hash.

## 5. Promoción

```powershell
python -m server.promotion --config profiles/okx/config.json `
  --evidence reports/backtest/my_strategy-oos.json `
  --stress reports/backtest/my_strategy-2x.json `
  --cycle reports/backtest/my_strategy-cycle.json `
  --strategy my_strategy@0.1.0 --json
```

| Criterio | Umbral |
|---|---|
| Evidencia de la estrategia | `id@version` coincide |
| PF fuera de muestra | > 1,0 |
| Operaciones OOS | >= 100 |
| Coste medio por operación | < 0,25 R, recalculado con la comisión y el `tick_value` del perfil |
| PF con coste duplicado | > 1,0 |
| PBO del ciclo | <= 0,2 |
| Hash de configuración | `config_hash` de la evidencia == `config_fingerprint(settings)` (16 hex) |

`--config` es obligatorio: el coste se mide con el perfil que va a operar. Una
evidencia que no declara su modelo de ejecución no pasa. Además, `config_hash` debe
coincidir con el fingerprint efectivo del perfil; una evidencia medida con otra
configuración no promociona aunque su PF sea bueno. El comando sale con 1 si no
está promovida; úsalo en CI o en un script, no lo ignores.

En el perfil:

```json
"promotion": {
  "required": true,
  "mode": "block",
  "evidence": "data/research/promotion/...json",
  "stress_evidence": "data/research/promotion/...-2x.json",
  "cycle": "data/research/promotion/...-cycle.json"
}
```

`mode: "block"` no arranca sin promoción; `"reduce"` arranca con el riesgo por
operación multiplicado por `size_factor`. Es una decisión del perfil, no del código.

## 6. Veredictos

| Situación | Veredicto | Qué hacer |
|---|---|---|
| Alguna puerta dura falla | `RECHAZADA` | no promocionar; documentar el fallo |
| Nada falla pero hay puertas no medibles | `INCONCLUSO` | medir lo que falta; no es aprobado |
| Todas las medidas pasan y el holdout pasa | `APROBADA` | habilita dry-run, **no** LIVE |

LIVE exige además adaptador implementado, `live_enabled` y confirmación explícita.

## 7. Dry-run

Mínimo 30 días de calendario con datos reales y fills simulados. Se compara contra el
backtest: slippage ≤10%, PF ≤10% de desviación, cero señales perdidas sin justificar,
cero divergencias snapshot/estado, uptime ≥99% en horario operativo.

## Registro y honestidad

Cada corrida escribe una línea en `reports/experiments.jsonl` con hashes de dataset y
configuración, estrategia y veredicto. Sin esa línea hay anécdota, no evidencia.

```powershell
python -m server.experiments --verify
python -m server.funnel
```

`--verify` comprueba la cadena de hashes; si se rompe, no promociones nada hasta
explicarlo. `funnel` enseña qué entró y qué sobrevivió.

Prohibido: optimizar contra el holdout, repetir el holdout, inventar métricas,
presentar una simulación sintética como validación, o tocar umbrales después de ver
resultados. El protocolo (`docs/PROTOCOLO_BACKTEST.md`) sigue en borrador hasta que
los ADR estén cerrados; no lo presentes como congelado.

## Estado actual del repo

Las estrategias incluidas (`reference`, `donchian`, `fade`, `trend`) están marcadas
como no validadas. No afirmes que alguna tiene edge sin pasar esta escalera y enseñar
el veredicto real.