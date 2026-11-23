from __future__ import annotations

from server.backtest import Dataset
from server.gates import evaluate_gates
from server.integrity import integrity_outcome, measure_integrity
from server.market.csv_data import ValidationIssue, ValidationReport


def _report(ok: bool, errors: list[ValidationIssue] | None = None) -> ValidationReport:
    return ValidationReport(
        ok=ok,
        symbols=["PRIMARY"],
        rows=10,
        sessions=1,
        errors=errors or [],
    )


def test_integrity_passes_with_a_clean_and_stable_dataset():
    outcome = integrity_outcome(_report(True), "a" * 64, "a" * 64)
    assert outcome.status == "pass"
    assert "hash estable" in outcome.detail


def test_integrity_fails_when_the_validator_reports_errors():
    outcome = integrity_outcome(
        _report(False, [ValidationIssue("empty_symbol", "PRIMARY has no rows")]),
        "a" * 64,
        "a" * 64,
    )
    assert outcome.status == "fail"
    assert "empty_symbol" in outcome.detail


def test_integrity_fails_when_the_hash_is_not_reproducible():
    outcome = integrity_outcome(_report(True), "a" * 64, "b" * 64)
    assert outcome.status == "fail"
    assert "hash inestable" in outcome.detail


def test_measure_integrity_on_a_real_file(settings, tmp_path):
    from tests.test_backtest_golden import _synthetic_csv

    path = _synthetic_csv(settings, tmp_path / "ok.csv", bars=30)
    assert measure_integrity(path, settings.instruments.symbols).status == "pass"

    broken = tmp_path / "broken.csv"
    broken.write_text("ts,symbol\n", encoding="utf-8")
    outcome = measure_integrity(broken, settings.instruments.symbols)
    assert outcome.status == "fail"


def test_dataset_hash_is_stable(settings, tmp_path):
    from tests.test_backtest_golden import _synthetic_csv

    path = _synthetic_csv(settings, tmp_path / "ok.csv", bars=30)
    first = Dataset.load(path, settings.instruments.symbols)
    second = Dataset.load(path, settings.instruments.symbols)
    assert first.dataset_id == second.dataset_id


def test_a_measured_integrity_gate_leaves_only_the_holdout_open():
    from server.gates import GateOutcome

    stats = {
        "closed": {
            "trades": 100,
            "profit_factor": 1.6,
            "expectancy_r": 0.25,
            "max_drawdown": 100.0,
            "max_loss_streak": 3,
            "pnl_without_top5": 500.0,
            "top5_share": 0.2,
            "expectancy_ci80_low": 0.05,
            "ambiguous_trades": 0,
        },
        "by_side": {"long": {"trades": 50}, "short": {"trades": 50}},
    }
    measured = {
        "G1/G3/G14": GateOutcome(id="G1/G3/G14", description="d", status="pass"),
        "G8": GateOutcome(id="G8", description="d", status="pass"),
        "G2": GateOutcome(id="G2", description="d", status="pass"),
    }
    report = evaluate_gates(stats, measured=measured)
    assert report.not_measured == ["H1-H5"]
    assert report.verdict == "INCONCLUSO"
