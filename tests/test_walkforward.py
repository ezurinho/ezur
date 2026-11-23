from __future__ import annotations

from datetime import date

import pytest

from server.walkforward import (
    _parse_grid,
    format_report,
    grid_combinations,
    run_walk_forward,
    split_windows,
)


def test_empty_grid_yields_one_empty_combination():
    assert grid_combinations({}) == [{}]


def test_grid_is_a_cartesian_product():
    combos = grid_combinations({"b": [1, 2], "a": [3, 4]})
    assert len(combos) == 4
    assert combos[0] == {"a": 3, "b": 1}
    assert {"a": 4, "b": 2} in combos


def test_split_windows_keeps_every_day():
    days = [date(2026, 11, 2) + __import__("datetime").timedelta(days=index) for index in range(10)]
    windows = split_windows(days, 3)
    assert [len(window) for window in windows] == [3, 3, 4]
    assert windows[0][0] == days[0]
    assert windows[-1][-1] == days[-1]
    assert sum(len(window) for window in windows) == len(days)


def test_split_windows_rejects_impossible_requests():
    days = [date(2026, 11, 2), date(2026, 11, 3)]
    with pytest.raises(ValueError):
        split_windows(days, 3)
    with pytest.raises(ValueError):
        split_windows(days, 0)


def test_walk_forward_reports_every_window_and_combination(settings):
    settings.strategy.id = "null"
    report = run_walk_forward(
        settings,
        strategy_id="null",
        grid={},
        windows=2,
        days_per_window=2,
        bars=60,
    )
    assert len(report["windows"]) == 2
    assert report["windows"][0]["days"] == 2
    assert report["combinations"][0]["windows"] == 2
    assert report["combinations"][0]["trades"] == 0
    assert "no elige ganador" in report["note"]


def test_walk_forward_is_deterministic(settings):
    settings.strategy.id = "reference"
    first = run_walk_forward(
        settings, strategy_id="reference", windows=2, days_per_window=2, bars=120
    )
    second = run_walk_forward(
        settings, strategy_id="reference", windows=2, days_per_window=2, bars=120
    )
    assert first["combinations"] == second["combinations"]


def test_walk_forward_records_one_experiment_per_run(settings, tmp_path):
    from server.experiments import load

    ledger = tmp_path / "ledger.jsonl"
    settings.strategy.id = "reference"
    report = run_walk_forward(
        settings,
        strategy_id="reference",
        grid={"fast": [5, 9]},
        windows=2,
        days_per_window=1,
        bars=60,
        ledger=ledger,
    )
    entries = load(ledger)
    assert len(entries) == 4  # 2 windows x 2 combinations
    assert len(report["experiments"]) == 4
    assert {entry["kind"] for entry in entries} == {"walkforward"}


def test_grid_parsing_accepts_numbers_and_strings():
    grid = _parse_grid("channel=10,20; mode=fast,slow; ratio=1.5")
    assert grid == {"channel": [10, 20], "mode": ["fast", "slow"], "ratio": [1.5]}


def test_grid_parsing_rejects_garbage():
    with pytest.raises(SystemExit):
        _parse_grid("channel")
    with pytest.raises(SystemExit):
        _parse_grid("channel=")


def test_report_is_readable(settings):
    settings.strategy.id = "null"
    report = run_walk_forward(
        settings, strategy_id="null", windows=2, days_per_window=1, bars=60
    )
    text = format_report(report)
    assert "Walk-forward null" in text
    assert "W1" in text


def test_cli_writes_the_report(settings, tmp_path, monkeypatch, capsys):
    from server import walkforward

    out = tmp_path / "wf.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "walkforward",
            "--strategy",
            "null",
            "--windows",
            "2",
            "--days",
            "1",
            "--bars",
            "60",
            "--out",
            str(out),
            "--no-ledger",
        ],
    )
    assert walkforward.main() == 0
    capsys.readouterr()
    assert out.exists()
