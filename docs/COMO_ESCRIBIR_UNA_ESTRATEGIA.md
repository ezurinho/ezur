# Cómo escribir una estrategia

Todo lo que una estrategia puede decir vive en `server/strategy/`. El motor, el
snapshot, la API y la interfaz no importan tu módulo: lo resuelven por `id`.

## Contrato

```python
class BaseStrategy(Protocol):
    id: str
    name: str
    version: str
    params_model: type[BaseModel]

    def warmup_requirements(self) -> Warmup: ...
    def evaluate(self, md: MarketData) -> StrategyOutput: ...
```

Tres obligaciones y ninguna libertad sobre el formato:

| Devolución | Regla |
|---|---|
| `Warmup.bars` | mínimo de velas por símbolo; `"*"` = todos los configurados |
| `StrategyOutput.phases` | 0..n fases con `status` del enum cerrado |
| `StrategyOutput.metrics` | diccionario clave → `Metric` con `format` y `tone` del enum |
| `StrategyOutput.signal` | `None` o una señal con `stop_price` obligatorio |
| `StrategyOutput.zones` / `markers` | opcionales, `kind` del enum cerrado |

Si un valor no encaja en un enum, no lo emitas: el snapshot rechaza el mensaje y
rompe el WebSocket. No hay texto libre en la parte visual.

## Ejemplo mínimo

```python
from pydantic import BaseModel, ConfigDict
from server.strategy.base import (
    BaseStrategy, MarketData, Marker, Metric, Phase, Signal, StrategyOutput, Warmup
)


class MyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: int = 20


class MyStrategy(BaseStrategy):
    id = "my_strategy"
    name = "Mi estrategia"
    version = "0.1.0"
    params_model = MyParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = MyParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        return Warmup(bars={"*": self.params.period + 1}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars[md.primary]
        if len(bars) < self.params.period + 1:
            return StrategyOutput(
                state="warmup",
                state_label="Calentando",
                phases=[Phase(key="warmup", label="Calentamiento", status="active")],
            )
        last = bars[-1]
        phases = [Phase(key="scan", label="Escaneo", status="done", ts=last.t)]
        metrics = {"close": Metric(label="Cierre", value=last.c, format="price")}
        return StrategyOutput(
            state="scanning", state_label="Buscando", phases=phases, metrics=metrics
        )
```

Registro en `server/strategy/registry.py`, una línea:

```python
from .my_strategy import MyStrategy

_BUILDERS = {
    ...,
    "my_strategy": lambda params: MyStrategy(params),
}
```

Nada más. `GET /api/strategy/schema` lo lista, la pestaña de configuración
muestra su esquema, `PUT /api/config` lo cambia en caliente y el gráfico dibuja
sus zonas y marcadores sin tocar el frontend.

## Reglas que el revisor va a comprobar

1. **Determinismo**: misma entrada, misma salida. Sin `random`, sin `now()`.
   El tiempo viene en `md.clock`.
2. **Sin estado oculto entre sesiones**: si guardas algo, límpialo cuando cambie
   `md.session.id`.
3. **Sin excepciones por datos cortos**: comprueba `len(bars)` antes de indexar.
4. **Parámetros validados**: `params_model` con `extra="forbid"` y rangos `ge/le`.
5. **Sin imports de infraestructura**: nada de `db`, `engine`, `api`. El plugin
   no sabe que existe SQLite.
6. **Costes asumidos**: la comisión y el slippage los aplica la ejecución; no los
   descuentes dentro de la señal.
7. **Stop obligatorio y positivo**: un stop al otro lado del precio es una señal
   inválida y se rechaza.
8. **Una señal por barra como máximo**, y una posición a la vez: el motor ignora
   señales mientras haya posición u orden pendiente.

## Probar

```bash
# unitarios del plugin: señales sobre barras construidas a mano
python -m pytest tests/test_strategy_plugins.py -q

# simulación determinista de 60 sesiones, con veredicto de puertas
python -m server.simulation --days 60 --bars 390 --strategy my_strategy \
  --out reports/backtest/simulation-60d-my_strategy.json

# el embudo de evaluación: qué entró y qué sobrevivió
python -m server.funnel
```

El resultado se registra en `reports/experiments.jsonl` con el hash del dataset
y de la configuración. Sin esa línea no hay evidencia, solo una anécdota.

## Lo que no debes hacer

- Optimizar parámetros contra el holdout. Se sella una vez y no se toca.
- Añadir un `if` con el nombre del instrumento. La terminal es agnóstica por
  diseño y hay un test que lo impone.
- Emitir métricas con `format` inventados: se rechazan.
- Suponer que la estrategia corre sola: con `auto_start: true` (lo normal) el
  motor evalúa desde el arranque; con `false`, alguien tiene que pulsar Iniciar.
