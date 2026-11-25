from __future__ import annotations

from server.gates import GateOutcome, evaluate_gates
from server.stress import cost_outcome, determinism_outcome, stressed_settings


def _stats(**closed) -> dict:
    base = {
        "trades": 100,
        "profit_factor": 1.6,
        "expectancy_r": 0.25,
        "max_drawdown": 100.0,
        "max_loss_streak": 3,
        "pnl_without_top5": 500.0,
        "top5_share": 0.2,
        "expectancy_ci80_low": 0.05,
        "ambiguous_trades": 0,
    }
    base.update(closed)
    return {"closed": base, "by_side": {"long": {"trades": 50}, "short": {"trades": 50}}}


def test_stressed_settings_doubles_costs(settings):
    clone = stressed_settings(settings, 2.0)
    assert clone.execution.commission_per_unit_side == settings.execution.commission_per_unit_side * 2
    assert clone.execution.slippage_ticks == settings.execution.slippage_ticks * 2
    # The original is not mutated.
    assert settings.execution.slippage_ticks == 1


def test_cost_gate_passes_when_the_edge_survives():
    outcome = cost_outcome(
        {"expectancy_r": 0.30, "profit_factor": 1.7},
        {"expectancy_r": 0.12, "profit_factor": 1.2},
    )
    assert outcome.status == "pass"
    assert outcome.id == "G8"


def test_cost_gate_fails_when_costs_eat_the_edge():
    outcome = cost_outcome(
        {"expectancy_r": 0.30, "profit_factor": 1.7},
        {"expectancy_r": -0.10, "profit_factor": 0.8},
    )
    assert outcome.status == "fail"


def test_determinism_gate_reports_both_ways():
    assert determinism_outcome(True).status == "pass"
    assert determinism_outcome(False).status == "fail"


def test_measured_gates_replace_the_placeholders():
    report = evaluate_gates(
        _stats(),
        measured={
            "G8": GateOutcome(id="G8", description="Costes duplicados", status="pass"),
            "G2": GateOutcome(id="G2", description="Determinismo", status="pass"),
        },
    )
    by_id = {outcome.id: outcome for outcome in report.outcomes}
    assert by_id["G8"].status == "pass"
    assert by_id["G2"].status == "pass"
    assert "G1/G3/G14" in report.not_measured
    assert report.verdict == "INCONCLUSO"


def test_without_measured_gates_nothing_is_invented():
    report = evaluate_gates(_stats())
    by_id = {outcome.id: outcome for outcome in report.outcomes}
    assert by_id["G8"].status == "not_measured"
    assert by_id["G2"].status == "not_measured"


def test_a_failing_measured_gate_rejects_the_strategy():
    report = evaluate_gates(
        _stats(),
        measured={"G8": GateOutcome(id="G8", description="Costes duplicados", status="fail")},
    )
    assert report.verdict == "RECHAZADA"
    assert "G8" in report.failed


def test_stress_runs_are_deterministic(settings, tmp_path, synthetic_csv):
    from server.stress import run_stress
    from server.strategy.reference import ReferenceStrategy

    path = synthetic_csv(tmp_path / "s.csv")
    strategy = ReferenceStrategy({})
    first = run_stress(settings, path, strategy)
    second = run_stress(settings, path, strategy)
    assert first.deterministic is True
    assert first.base == second.base
    assert first.base["fees"] > 0
    assert first.stressed["fees"] > first.base["fees"]
