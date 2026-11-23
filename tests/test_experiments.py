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


# --- hash chain (lección de ai-hedge-fund) --------------------------------
def _fill(path, n=3):
    from server import experiments

    for i in range(n):
        experiments.record(
            path,
            kind="backtest",
            strategy_id="reference",
            strategy_version="0.1.0",
            dataset_id=f"synthetic-{i}",
            config={"days": 20, "i": i},
            metrics={"profit_factor": 0.9 + i / 100},
            verdict="RECHAZADA",
        )


def test_chain_links_every_entry(tmp_path):
    from server import experiments

    path = tmp_path / "ledger.jsonl"
    _fill(path)
    entries = experiments.load(path)
    assert entries[0]["prev_hash"] == ""
    for previous, current in zip(entries, entries[1:]):
        assert current["prev_hash"] == previous["chain_hash"]
    assert experiments.verify_chain(path)["ok"] is True


def test_editing_the_middle_breaks_the_chain(tmp_path):
    from server import experiments

    path = tmp_path / "ledger.jsonl"
    _fill(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    # The attack that matters: turn a rejection into an approval.
    lines[1] = lines[1].replace('"verdict": "RECHAZADA"', '"verdict": "APROBADA"')
    assert "APROBADA" in lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = experiments.verify_chain(path)
    assert result["ok"] is False
    assert result["broken_at"] == 1
    assert "chain_hash" in result["reason"]


def test_deleting_a_line_breaks_the_chain(tmp_path):
    from server import experiments

    path = tmp_path / "ledger.jsonl"
    _fill(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = experiments.verify_chain(path)
    assert result["ok"] is False
    assert result["broken_at"] == 1
    assert "prev_hash" in result["reason"]


def test_appending_keeps_the_chain_valid(tmp_path):
    from server import experiments

    path = tmp_path / "ledger.jsonl"
    _fill(path, 2)
    _fill(path, 1)
    assert experiments.verify_chain(path)["ok"] is True


def test_legacy_ledger_without_chain_still_loads(tmp_path):
    import json

    from server import experiments

    path = tmp_path / "legacy.jsonl"
    legacy = {
        "kind": "backtest",
        "strategy": {"id": "reference", "version": "0.1.0"},
        "dataset_id": "synthetic",
        "config_sha256": "x",
        "metrics_sha256": "y",
        "verdict": "RECHAZADA",
        "notes": "",
        "experiment_id": "abc123",
        "ts": "2026-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    assert experiments.verify_chain(path)["ok"] is True
    assert experiments.summary(path)["experiments"] == 1
