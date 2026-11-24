"""Strategy registry.

Adding a strategy is one entry here plus one module in this package. The rest
of the application resolves strategies by id and never imports them directly.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import BaseStrategy
from .donchian import DonchianStrategy
from .fade import FadeStrategy
from .null_strategy import NullStrategy
from .reference import ReferenceStrategy
from .trend import TrendStrategy

_BUILDERS: dict[str, Callable[[dict[str, Any]], BaseStrategy]] = {
    "null": lambda params: NullStrategy(),
    "reference": lambda params: ReferenceStrategy(params),
    "donchian": lambda params: DonchianStrategy(params),
    "fade": lambda params: FadeStrategy(params),
    "trend": lambda params: TrendStrategy(params),
}


def available() -> list[str]:
    return sorted(_BUILDERS)


def resolve_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> BaseStrategy:
    try:
        builder = _BUILDERS[strategy_id]
    except KeyError:
        raise KeyError(f"unknown strategy {strategy_id!r}") from None
    strategy = builder(params or {})
    # Validate declared params against the plugin's own schema.
    strategy.params_model.model_validate(params or {})
    return strategy


def strategy_schema(strategy_id: str) -> dict[str, Any]:
    try:
        builder = _BUILDERS[strategy_id]
    except KeyError:
        raise KeyError(f"unknown strategy {strategy_id!r}") from None
    model = builder({}).params_model
    return {
        "id": strategy_id,
        "params_schema": model.model_json_schema(),
    }
