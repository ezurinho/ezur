---
name: trading-strategy-plugin
description: "Escribe, registra y prueba un plugin de estrategia para ezur sin tocar motor, snapshot ni React. Incluye la frontera con la IA y el marco de barras de la estrategia. Úsala cuando haya que añadir una estrategia nueva, cambiar su lógica o sus parámetros, emitir fases/métricas/zonas/marcadores, o revisar que un plugin cumple el contrato BaseStrategy."
version: 1.1.0
---

# Escribir un plugin de estrategia

## Cuándo usarla

Añadir `server/strategy/<nombre>.py`, cambiar `evaluate()`, añadir parámetros, emitir
señales o métricas nuevas, o revisar un plugin existente. Si el cambio toca el
snapshot o React, lee también la skill `trading-bot-ops`.

Si la estrategia nace de una spec de IA, el plugin sigue siendo determinista: el LLM
no entra en `evaluate` ni en el motor. La spec se valida y se mide con
`trading-ai-strategy-engine`; aquí solo se implementan sus reglas y se prueban.

## Lee antes de escribir

1. `server/strategy/base.py` — contrato y modelos.
2. `server/strategy/reference.py` — plugin completo y pequeño.
3. `server/strategy/registry.py` — resolución por `id`.
4. `docs/COMO_ESCRIBIR_UNA_ESTRATEGIA.md` — reglas del revisor.

## Contrato, en una tabla

| Pieza | Regla |
|---|---|
| `id`, `name`, `version` | estables; `version` sube si cambia la lógica |
| `params_model` | Pydantic con `extra="forbid"` y rangos `ge/le` |
| `warmup_requirements()` | `Warmup(bars={"*": n}, session_ready=bool)` |
| `evaluate(md)` | determinista; sin red, disco, reloj ni azar |
| `md.bars` | barras cerradas del marco `strategy.timeframe`; el motor agrega y descarta el cubo abierto; el plugin no resamplea |
| `StrategyOutput.phases` | 0..n; `status` del enum cerrado |
| `StrategyOutput.metrics` | clave → `Metric`; `format` y `tone` del enum |
| `StrategyOutput.signal` | `None` o `Signal` con `stop_price` positivo |
| `zones` / `markers` | opcionales; `kind` del enum cerrado |

El tiempo sale de `md.clock`, no de `datetime.now()`. Los símbolos salen de
`md.primary` y `md.bars`, nunca de una constante.

`md.bars` llega en el marco de la estrategia (`strategy.timeframe`), no en el marco
del feed. El motor agrupa por cubos cerrados y descarta el cubo abierto; no llames a
`resample` dentro del plugin ni mezcles marcos.

## Pasos

### 1. Modelo de parámetros

```python
from pydantic import BaseModel, ConfigDict, Field

class MyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: int = Field(default=20, ge=2, le=500)
    atr_k: float = Field(default=2.0, gt=0, le=10)
```

### 2. Clase

```python
from server.strategy.base import (
    BaseStrategy, MarketData, Metric, Phase, StrategyOutput, Warmup,
)

class MyStrategy(BaseStrategy):
    id = "my_strategy"
    name = "Mi estrategia"
    version = "0.1.0"
    params_model = MyParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = MyParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        return Warmup(bars={"*": self.params.period + 1}, session_ready=False)
```

### 3. `evaluate`

```python
    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        if len(bars) < self.params.period + 1:
            return StrategyOutput(
                state="warmup",
                state_label="Calentando",
                phases=[Phase(key="warmup", label="Calentamiento", status="active")],
            )
        last = bars[-1]
        return StrategyOutput(
            state="scanning",
            state_label="Buscando",
            phases=[Phase(key="scan", label="Escaneo", status="done", ts=last.t)],
            metrics={"close": Metric(label="Cierre", value=last.c, format="price")},
        )
```

Una señal, cuando toque:

```python
Signal(
    key=f"{md.session.id}:long:{last.t.isoformat()}",
    side="long",
    reason="cierre sobre la banda",
    ts=last.t,
    stop_price=last.c - self.params.atr_k * atr,
    valid_until=last.t + timedelta(minutes=5),
    strength=0.6,
)
```

`key` debe ser estable para la misma señal: el motor la usa para no ejecutar dos
veces la misma entrada. Sin `stop_price` válido la señal se rechaza.

### 4. Registro

En `server/strategy/registry.py`, importa la clase y añade una línea al dict:

```python
"my_strategy": lambda params: MyStrategy(params),
```

El motor, la API y React lo resuelven por `id`. No importes el plugin desde
`engine.py`, `api.py` ni `snapshot.py`.

### 5. Configuración

```json
"strategy": {"id": "my_strategy", "enabled": true, "version": "0.1.0", "params": {"period": 20}}
```

`PUT /api/config` lo cambia en caliente y valida contra `params_model`; un `422`
deja la estrategia anterior intacta.

## Tests que hay que dejar verdes

```powershell
python -m pytest tests/test_strategy_plugins.py tests/test_snapshot_contract.py tests/test_no_hardcoded_instruments.py tests/test_timeframe.py tests/test_resample.py -q
python -m pytest tests/test_parity.py -q
```

| Test | Qué fija |
|---|---|
| `test_strategy_plugins.py` | señales, warmup, params y determinismo |
| `test_snapshot_contract.py` | el snapshot sigue siendo v1 válido |
| `test_no_hardcoded_instruments.py` | ni tickers ni conceptos de estrategia en infra |
| `test_timeframe.py` | `md.bars` usa el marco de la estrategia y descarta el cubo abierto |
| `test_resample.py` | agregación OHLCV por cubos cerrados y rechazo de marcos inválidos |
| `test_parity.py` | backtest y motor real dan las mismas operaciones |

Para una estrategia nueva, añade al menos: warmup insuficiente, señal larga, señal
corta, stop inválido y dos ejecuciones con el mismo resultado.

## Frontera con IA

- Un LLM puede proponer la spec o revisar el código, pero el plugin que corre no
  importa SDK de LLM, red, disco, reloj ni azar.
- No calcules métricas de rendimiento dentro del plugin: las produce el backtest o el
  runner determinista. El plugin solo emite señal, fases, métricas de estado, zonas y
  marcadores.
- Un cambio generado por IA se revisa, se testea y sube `version`; no se promociona
  por la confianza del modelo.

## Validación rápida (no es promoción)

```powershell
python -m server.simulation --days 20 --strategy my_strategy --out reports/backtest/sim-my_strategy.json
python -m server.backtest --dataset data/dataset_1m.csv --strategy my_strategy --gates --split 2025-01-01
```

La simulación usa datos sintéticos: verifica el pipeline, no la rentabilidad. Para
decidir si la estrategia sirve, usa `trading-validation-pipeline`.

## Revisión final

- [ ] Sin `random`, `datetime.now()`, red, disco ni acceso a la base.
- [ ] Sin nombres de instrumento ni de sesión concretos.
- [ ] `len(bars)` comprobado antes de indexar.
- [ ] `params_model` con `extra="forbid"` y rangos.
- [ ] `stop_price` positivo y del lado correcto del precio.
- [ ] Una señal por barra como máximo.
- [ ] `version` subida si cambió la lógica.
- [ ] Registro en `registry.py` y config actualizada.
- [ ] Tests anteriores verdes.

## Fallos típicos

| Síntoma | Causa probable |
|---|---|
| El snapshot no llega al WebSocket | `Metric.format`, `Phase.status` o `Zone.kind` fuera del enum |
| Nunca emite señal | warmup mal declarado o `md.bars` sin el símbolo primario |
| `422` al guardar config | parámetro fuera de rango o `extra="forbid"` |
| Opera dos veces la misma entrada | `Signal.key` no es estable |
| El backtest y el motor divergen | el plugin usa estado oculto o mira `md.clock` distinto |