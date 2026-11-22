from __future__ import annotations

from server.experiments import record
from server.funnel import build_funnel, format_funnel, load_funnel


def _entry(verdict: str, strategy_id: str = "reference", dataset: str = "a" * 64) -> dict:
    return {
        "kind": "backtest",
        "strategy": {"id": strategy_id, "version": "0.0.0"},
        "dataset_id": dataset,
        "verdict": verdict,
    }


def test_stages_count_every_verdict():
    report = build_funnel(
        [_entry("RECHAZADA"), _entry("INCONCLUSO"), _entry("APROBADA")]
    )
    assert report["stages"]["experiments"] == 3
    assert report["stages"]["rejected"] == 1
    assert report["stages"]["inconclusive"] == 1
    assert report["stages"]["approved"] == 1
    assert report["survival_rate"] == 1 / 3


def test_distinct_strategies_and_datasets_are_not_double_counted():
    report = build_funnel(
        [
            _entry("RECHAZADA", dataset="a" * 64),
            _entry("RECHAZADA", dataset="a" * 64),
            _entry("RECHAZADA", strategy_id="other", dataset="b" * 64),
        ]
    )
    assert report["stages"]["strategies"] == 2
    assert report["stages"]["datasets"] == 2
    assert report["by_strategy"]["reference@0.0.0"]["experiments"] == 2


def test_empty_ledger_has_zero_survival():
    report = build_funnel([])
    assert report["stages"]["experiments"] == 0
    assert report["survival_rate"] == 0.0


def test_unknown_verdict_is_kept_in_the_histogram():
    report = build_funnel([_entry("PENDIENTE")])
    assert report["verdicts"] == {"PENDIENTE": 1}
    assert report["stages"]["approved"] == 0


def test_report_is_readable_as_text():
    text = format_funnel(build_funnel([_entry("RECHAZADA")]))
    assert "Embudo" in text
    assert "reference@0.0.0" in text


def test_load_funnel_reads_a_real_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    record(
        ledger,
        kind="backtest",
        strategy_id="reference",
        strategy_version="0.0.0",
        dataset_id="c" * 64,
        config={},
        metrics={"trades": 1},
        verdict="RECHAZADA",
    )
    assert load_funnel(ledger)["stages"]["experiments"] == 1
