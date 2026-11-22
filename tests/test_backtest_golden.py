from __future__ import annotations

import pytest

from server.backtest import fingerprint, run_backtest
from server.strategy.null_strategy import NullStrategy


def test_backtest_is_deterministic(settings, dataset_path):
    hashes = {
        fingerprint(run_backtest(settings, dataset_path, NullStrategy()))
        for _ in range(3)
    }
    assert len(hashes) == 1


def test_backtest_with_null_strategy_produces_no_trades(settings, dataset_path):
    result = run_backtest(settings, dataset_path, NullStrategy())
    assert result.trades == []
    assert result.metrics["trades"] == 0
    assert result.equity == []


def test_backtest_rejects_invalid_dataset(settings, tmp_path):
    path = tmp_path / "broken.csv"
    path.write_text("ts,symbol,o\n2026-01-15T14:30:00Z,PRIMARY,1\n", encoding="utf-8")
    try:
        run_backtest(settings, path, NullStrategy())
    except ValueError as error:
        assert "invalid dataset" in str(error)
    else:  # pragma: no cover
        raise AssertionError("invalid dataset must be rejected")


def test_backtest_records_dataset_identity(settings, dataset_path):
    result = run_backtest(settings, dataset_path, NullStrategy())
    assert len(result.dataset_id) == 64
    assert result.diagnostics["rows"] == 60
    assert result.diagnostics["dataset_sessions"] == 1


def _synthetic_csv(settings, path, day: str = "2026-01-15", bars: int = 390):
    import csv
    from datetime import date

    from server.market import synthetic
    from server.simulation import session_start_utc

    series = synthetic.generate_session(
        day,
        settings.instruments.primary,
        start=session_start_utc(settings, date.fromisoformat(day)),
        bars=bars,
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for bar in series:
            writer.writerow(
                [bar.t.isoformat(), settings.instruments.primary, bar.o, bar.h, bar.l, bar.c, bar.v]
            )
    return path


def test_reference_strategy_backtest_is_deterministic_and_trades(settings, tmp_path):
    from server.strategy.reference import ReferenceStrategy

    path = _synthetic_csv(settings, tmp_path / "synthetic.csv")
    first = run_backtest(settings, path, ReferenceStrategy({}))
    second = run_backtest(settings, path, ReferenceStrategy({}))

    assert len(first.trades) > 0
    assert fingerprint(first) == fingerprint(second)
    assert first.metrics["fees"] > 0
    assert first.equity and first.equity[-1] == pytest.approx(
        settings.risk.initial_capital + first.metrics["pnl_net"]
    )


def test_backtest_verdict_rejects_the_reference_strategy(settings, tmp_path):
    from server.gates import evaluate_gates
    from server.stats import aggregate
    from server.strategy.reference import ReferenceStrategy

    path = _synthetic_csv(settings, tmp_path / "single.csv", bars=120)
    result = run_backtest(settings, path, ReferenceStrategy({}))
    payload = aggregate(result.trades, settings.risk.initial_capital)
    report = evaluate_gates(payload, initial_capital=settings.risk.initial_capital)
    assert report.verdict == "RECHAZADA"
