from __future__ import annotations

from server.experiments import build_record, find, load, record, summary


def _record(tmp_path, **overrides):
    payload = dict(
        kind="backtest",
        strategy_id="reference",
        strategy_version="0.1.0",
        dataset_id="d" * 64,
        config={"risk": {"risk_per_trade_pct": 1.0}},
        metrics={"trades": 10, "profit_factor": 1.2},
        verdict="RECHAZADA",
        notes="",
    )
    payload.update(overrides)
    return record(tmp_path / "ledger.jsonl", **payload)


def test_record_appends_jsonl(tmp_path):
    entry = _record(tmp_path)
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert entry["experiment_id"] in lines[0]
    assert len(entry["config_sha256"]) == 64


def test_identity_is_stable_for_same_payload(tmp_path):
    first = _record(tmp_path)
    same = build_record(
        kind="backtest",
        strategy_id="reference",
        strategy_version="0.1.0",
        dataset_id="d" * 64,
        config={"risk": {"risk_per_trade_pct": 1.0}},
        metrics={"trades": 10, "profit_factor": 1.2},
        verdict="RECHAZADA",
    )
    assert first["experiment_id"] == same["experiment_id"]


def test_different_metrics_change_identity(tmp_path):
    first = _record(tmp_path)
    second = _record(tmp_path, metrics={"trades": 11, "profit_factor": 1.2})
    assert first["experiment_id"] != second["experiment_id"]
    assert len(load(tmp_path / "ledger.jsonl")) == 2


def test_find_and_summary(tmp_path):
    first = _record(tmp_path)
    _record(tmp_path, verdict="INCONCLUSO")
    assert find(first["experiment_id"], tmp_path / "ledger.jsonl") == first

    report = summary(tmp_path / "ledger.jsonl")
    assert report["experiments"] == 2
    assert report["unique_ids"] == 2
    assert report["verdicts"] == {"RECHAZADA": 1, "INCONCLUSO": 1}


def test_missing_ledger_is_empty(tmp_path):
    assert load(tmp_path / "nope.jsonl") == []
    assert summary(tmp_path / "nope.jsonl")["experiments"] == 0


def test_corrupt_line_is_skipped(tmp_path):
    target = tmp_path / "ledger.jsonl"
    target.write_text('{"a": 1}\nnot json\n', encoding="utf-8")
    assert len(load(target)) == 1


def test_cli_prints_the_ledger(tmp_path, capsys):
    from server.experiments import main

    path = tmp_path / "ledger.jsonl"
    record(
        path,
        kind="backtest",
        strategy_id="reference",
        strategy_version="0.1.0",
        dataset_id="e" * 64,
        config={},
        metrics={"trades": 3},
        verdict="RECHAZADA",
    )
    assert main(["--ledger", str(path)]) == 0
    out = capsys.readouterr().out
    assert "reference@0.1.0" in out
    assert "1 experimento(s)" in out


def test_cli_finds_one_experiment(tmp_path, capsys):
    from server.experiments import main

    path = tmp_path / "ledger.jsonl"
    entry = _record(tmp_path)
    assert main(["--ledger", str(path), "--find", entry["experiment_id"]]) == 0
    assert entry["experiment_id"] in capsys.readouterr().out


def test_cli_reports_a_missing_experiment(tmp_path, capsys):
    from server.experiments import main

    assert main(["--ledger", str(tmp_path / "none.jsonl"), "--find", "abc"]) == 1
    assert "No existe" in capsys.readouterr().out


def test_cli_json_summary(tmp_path, capsys):
    from server.experiments import main

    path = tmp_path / "ledger.jsonl"
    _record(tmp_path)
    assert main(["--ledger", str(path), "--json"]) == 0
    assert '"experiments": 1' in capsys.readouterr().out
