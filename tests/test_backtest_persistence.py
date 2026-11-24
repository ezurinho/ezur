"""Persistir el estado en cada vela solo tiene sentido si algo puede reiniciar."""
from __future__ import annotations

from server.backtest import run_backtest
from server.engine import TradingEngine
from server.strategy.null_strategy import NullStrategy


def test_el_backtest_no_escribe_estado_en_cada_vela(settings, dataset_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(TradingEngine, "_persist", lambda self: calls.append(1))

    result = run_backtest(settings, dataset_path, NullStrategy())

    # Una sola escritura, la del arranque; con 60 velas serían 61 si se
    # persistiera en cada una.
    assert len(calls) == 1
    assert result.metrics["trades"] == 0


def test_el_motor_en_vivo_sigue_persistiendo(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None)
    calls: list[int] = []
    monkeypatch.setattr(TradingEngine, "_persist", lambda self: calls.append(1))

    engine.start()

    assert calls
