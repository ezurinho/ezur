from __future__ import annotations

import json

import pytest

from server.confirmatory import (
    HoldoutAlreadySealed,
    canonical_hash,
    read_seal,
    seal_holdout,
    verify_seal,
)


def _seal(tmp_path, dataset, config=None, strategy=None):
    return seal_holdout(
        tmp_path / "lock.json",
        dataset_path=dataset,
        config=config or {"risk": {"risk_per_trade_pct": 1.0}},
        strategy=strategy or {"id": "reference", "version": "0.1.0"},
        protocol="PROTOCOLO_BACKTEST v1",
    )


def test_seal_writes_hashes(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("ts,symbol\n", encoding="utf-8")
    seal = _seal(tmp_path, dataset)

    assert len(seal["dataset_sha256"]) == 64
    assert len(seal["seal_sha256"]) == 64
    assert seal["protocol"] == "PROTOCOLO_BACKTEST v1"
    assert read_seal(tmp_path / "lock.json") == seal


def test_second_seal_is_refused(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("data", encoding="utf-8")
    _seal(tmp_path, dataset)
    with pytest.raises(HoldoutAlreadySealed):
        _seal(tmp_path, dataset)


def test_verify_passes_with_identical_inputs(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("data", encoding="utf-8")
    config = {"risk": {"risk_per_trade_pct": 1.0}}
    strategy = {"id": "reference", "version": "0.1.0"}
    _seal(tmp_path, dataset, config, strategy)

    result = verify_seal(
        tmp_path / "lock.json", dataset_path=dataset, config=config, strategy=strategy
    )
    assert result["ok"] is True
    assert result["reasons"] == []


def test_verify_detects_changed_dataset(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("data", encoding="utf-8")
    config = {"risk": {}}
    strategy = {"id": "x"}
    _seal(tmp_path, dataset, config, strategy)
    dataset.write_text("other data", encoding="utf-8")

    result = verify_seal(
        tmp_path / "lock.json", dataset_path=dataset, config=config, strategy=strategy
    )
    assert result["ok"] is False
    assert any("dataset" in reason for reason in result["reasons"])


def test_verify_detects_changed_config(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("data", encoding="utf-8")
    strategy = {"id": "x"}
    _seal(tmp_path, dataset, {"risk": {"a": 1}}, strategy)

    result = verify_seal(
        tmp_path / "lock.json",
        dataset_path=dataset,
        config={"risk": {"a": 2}},
        strategy=strategy,
    )
    assert result["ok"] is False
    assert any("configuration" in reason for reason in result["reasons"])


def test_verify_detects_edited_seal_file(tmp_path):
    dataset = tmp_path / "bars.csv"
    dataset.write_text("data", encoding="utf-8")
    _seal(tmp_path, dataset)

    lock = tmp_path / "lock.json"
    payload = json.loads(lock.read_text(encoding="utf-8"))
    payload["protocol"] = "otro protocolo"
    lock.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_seal(
        lock, dataset_path=dataset, config={"risk": {}}, strategy={"id": "reference", "version": "0.1.0"}
    )
    assert result["ok"] is False
    assert any("edited" in reason for reason in result["reasons"])


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
