from __future__ import annotations

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
