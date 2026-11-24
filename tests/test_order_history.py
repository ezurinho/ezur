"""El histórico de órdenes se acota: viaja entero en cada snapshot."""
from __future__ import annotations

from datetime import datetime, timezone

from server.config import ExecutionConfig
from server.execution import MAX_ORDERS, ExecutionEngine
from server.models import RiskDecision
from server.strategy.base import Signal

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def test_el_historial_de_ordenes_se_acota_y_conserva_la_pendiente():
    engine = ExecutionEngine(ExecutionConfig(), {})
    decision = RiskDecision(approved=True, units=1, risk_per_unit=1.0)

    for index in range(MAX_ORDERS + 5):
        for order in engine.orders:
            if order.status == "pending":
                order.status = "filled"
        engine.arm(
            decision,
            Signal(
                key=f"k{index}",
                side="long",
                ts=NOW,
                stop_price=99.0,
                target_price=101.0,
            ),
            "BTC",
            100.0,
        )

    assert len(engine.orders) == MAX_ORDERS
    assert engine.orders[-1].status == "pending"
