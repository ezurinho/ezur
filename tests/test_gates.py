from __future__ import annotations

from server.gates import GateThresholds, evaluate_gates


def _payload(**overrides) -> dict:
    closed = {
        "trades": 120,
        "wins": 60,
        "losses": 60,
        "win_rate": 0.5,
        "profit_factor": 1.6,
        "expectancy_r": 0.25,
        "pnl_net": 5000.0,
        "max_drawdown": 300.0,
        "max_loss_streak": 4,
        "pnl_without_top5": 1500.0,
        "top5_share": 0.3,
        "ambiguous_trades": 0,
        "expectancy_ci80_low": 0.05,
    }
    closed.update(overrides.pop("closed", {}))
    payload = {
        "closed": closed,
        "by_side": {"long": {"trades": 60}, "short": {"trades": 60}},
    }
    payload.update(overrides)
    return payload


def test_all_measurable_gates_pass_but_verdict_is_inconclusive():
    report = evaluate_gates(_payload(), initial_capital=25_000.0)
    assert report.failed == []
    assert "G8" in report.not_measured
    assert "H1-H5" in report.not_measured
    assert report.verdict == "INCONCLUSO"


def test_edge_gate_rejects_a_losing_strategy():
    report = evaluate_gates(
        _payload(closed={"profit_factor": 0.9, "expectancy_r": -0.2}),
        initial_capital=25_000.0,
    )
    assert "G5" in report.failed
    assert report.verdict == "RECHAZADA"


def test_drawdown_gate_uses_percentage_of_capital():
    report = evaluate_gates(
        _payload(closed={"max_drawdown": 700.0}), initial_capital=25_000.0
    )
    assert "G6" in report.failed


def test_loss_streak_gate():
    report = evaluate_gates(
        _payload(closed={"max_loss_streak": 12}), initial_capital=25_000.0
    )
    assert "G6" in report.failed


def test_sample_gate_requires_minimum_per_side():
    report = evaluate_gates(
        _payload(
            closed={"trades": 40},
            by_side={"long": {"trades": 35}, "short": {"trades": 5}},
        ),
        initial_capital=25_000.0,
    )
    assert "G4" in report.failed


def test_concentration_gate():
    report = evaluate_gates(
        _payload(closed={"pnl_without_top5": -100.0, "top5_share": 0.8}),
        initial_capital=25_000.0,
    )
    assert "G9/G10" in report.failed


def test_bootstrap_gate():
    report = evaluate_gates(
        _payload(closed={"expectancy_ci80_low": -0.01}), initial_capital=25_000.0
    )
    assert "G11" in report.failed


def test_ambiguous_gate():
    report = evaluate_gates(
        _payload(closed={"trades": 100, "ambiguous_trades": 10}),
        initial_capital=25_000.0,
    )
    assert "G13" in report.failed


def test_thresholds_are_configurable():
    strict = GateThresholds(min_profit_factor=2.0)
    report = evaluate_gates(_payload(), initial_capital=25_000.0, thresholds=strict)
    assert "G5" in report.failed
    assert report.thresholds_version == "1.0"


def test_report_lists_every_gate_once():
    report = evaluate_gates(_payload())
    ids = [outcome.id for outcome in report.outcomes]
    assert len(ids) == len(set(ids))
    assert set(ids) >= {"G4", "G5", "G6", "G11", "G13"}
