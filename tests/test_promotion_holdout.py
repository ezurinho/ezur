from __future__ import annotations

import json

import pytest

from server import holdout, promotion
from server.confirmatory import canonical_hash, file_hash
from server.config import Settings
from server.holdout import (
    HOLDOUT_END_EXCLUSIVE,
    HOLDOUT_START,
    begin_study,
    consume_study,
    holdout_config,
    strategy_payload,
)
from server.strategy.null_strategy import NullStrategy

EVIDENCE = {
    "strategy": {"id": "null", "version": "0.0.0"},
    "dataset": "data/BTC_1h_binance.csv",
    "split": {"out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    "metrics": {"trades": 169, "fees": 3802.5},
    "risk_budget": 250.0,
    "execution": {
        "commission_per_unit_side": 0.62,
        "tick_size": 0.25,
        "tick_value": 0.5,
    },
    "cost_per_trade_r": 0.09,
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {
    "pbo": {"pbo": 0.11},
    "dsr": {"dsr": 0.97},
    "strategy": {"id": "null", "version": "0.0.0"},
    "candidate": "null",
    "inputs": {"dataset": {"path": "data/BTC_1h_binance.csv"}},
    "universe": [{"name": "null", "timeframe": "1h"}],
}
EXECUTION = EVIDENCE["execution"]


@pytest.fixture
def holdout_promotion(tmp_path, monkeypatch):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    dataset = tmp_path / "holdout.csv"
    dataset.write_text("ts,symbol\n", encoding="utf-8")
    settings = Settings()
    strategy = NullStrategy()
    holdout.seal_run(dataset, settings, strategy)
    permit = begin_study(
        surface="runner",
        dataset_path=dataset,
        dataset_id=file_hash(dataset),
        settings=settings,
        strategy=strategy,
        window=(HOLDOUT_START, HOLDOUT_END_EXCLUSIVE),
    )
    return dataset, settings, strategy, permit


def _consumed(evidence: dict, fixture) -> dict:
    dataset, settings, strategy, permit = fixture
    payload = {
        key: value
        for key, value in evidence.items()
        if key not in {"holdout", "dataset_id"}
    }
    payload["dataset_id"] = file_hash(dataset)
    block = consume_study(permit.permit_id, payload)
    return {**payload, "holdout": block}


def _hashes(fixture):
    dataset, settings, strategy, permit = fixture
    return (
        canonical_hash(holdout_config(settings)),
        canonical_hash(strategy_payload(strategy)),
    )


def _evaluate(evidence, fixture, **overrides):
    study_hash, strategy_hash = _hashes(fixture)
    return promotion.evaluate(
        evidence,
        STRESS,
        CYCLE,
        execution=EXECUTION,
        require_holdout=True,
        study_hash=study_hash,
        strategy_hash=strategy_hash,
        **overrides,
    )


def test_sin_holdout_la_promocion_no_pasa(holdout_promotion):
    verdict = _evaluate({**EVIDENCE, "strategy": {"id": "null", "version": "0.0.0"}}, holdout_promotion)

    assert verdict["passed"] is False
    assert "holdout_consumido" in verdict["failed"]
    assert verdict["holdout"]["state"] is None
    assert verdict["holdout"]["checks"]["holdout_consumido"] is False


def test_con_holdout_consumido_y_atestacion_valida_promueve(holdout_promotion):
    evidence = _consumed(
        {**EVIDENCE, "strategy": {"id": "null", "version": "0.0.0"}},
        holdout_promotion,
    )

    verdict = _evaluate(evidence, holdout_promotion)

    assert verdict["passed"] is True, verdict["reason"]
    assert verdict["holdout"]["state"] == "CONSUMED"
    assert all(verdict["holdout"]["checks"].values())
    assert verdict["holdout"]["attestation"]


def test_una_evidencia_manipulada_no_pasa(holdout_promotion):
    evidence = _consumed(
        {**EVIDENCE, "strategy": {"id": "null", "version": "0.0.0"}},
        holdout_promotion,
    )
    evidence["metrics"]["fees"] = 1.0

    verdict = _evaluate(evidence, holdout_promotion)

    assert verdict["passed"] is False
    assert verdict["holdout"]["checks"]["holdout_atestacion"] is False


def test_otro_estudio_no_pasa(holdout_promotion):
    evidence = _consumed(
        {**EVIDENCE, "strategy": {"id": "null", "version": "0.0.0"}},
        holdout_promotion,
    )
    study_hash, strategy_hash = _hashes(holdout_promotion)

    verdict = promotion.evaluate(
        evidence,
        STRESS,
        CYCLE,
        execution=EXECUTION,
        require_holdout=True,
        study_hash="0" * 64,
        strategy_hash=strategy_hash,
    )

    assert verdict["passed"] is False
    assert verdict["holdout"]["checks"]["holdout_identidad"] is False


def test_el_cli_sale_con_dos_si_falta_el_holdout(tmp_path, holdout_promotion):
    evidence = tmp_path / "bt.json"
    evidence.write_text(json.dumps(EVIDENCE), encoding="utf-8")
    profile = Settings.model_validate(
        {
            "promotion": {
                "required": True,
                "evidence": str(evidence),
            }
        }
    )
    config = tmp_path / "config.json"
    config.write_text(profile.model_dump_json(), encoding="utf-8")

    code = promotion.main(
        [
            "--config",
            str(config),
            "--evidence",
            str(evidence),
        ]
    )

    assert code == 2


def test_el_cli_y_el_arranque_exigen_el_holdout(tmp_path, monkeypatch, holdout_promotion):
    path = tmp_path / "bt.json"
    stress_path = tmp_path / "bt2x.json"
    stress_path.write_text(json.dumps(STRESS), encoding="utf-8")
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(json.dumps(CYCLE), encoding="utf-8")
    profile = Settings.model_validate(
        {
            "promotion": {
                "required": True,
                "evidence": str(path),
                "stress_evidence": str(stress_path),
                "cycle": str(cycle_path),
            }
        }
    )
    from server.backtest import config_fingerprint

    evidence = _consumed(
        {
            **EVIDENCE,
            "strategy": {"id": "null", "version": "0.0.0"},
            "config_hash": config_fingerprint(profile),
        },
        holdout_promotion,
    )
    path.write_text(json.dumps(evidence), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(profile.model_dump_json(), encoding="utf-8")

    effective, verdict = promotion.effective_settings_and_verdict(
        profile, config_hash=config_fingerprint(profile)
    )
    code = promotion.main(
        [
            "--config",
            str(config),
            "--evidence",
            str(path),
            "--stress",
            str(stress_path),
            "--cycle",
            str(cycle_path),
        ]
    )

    assert verdict is not None and verdict["passed"] is True, verdict["reason"]
    assert code == 0
    assert effective.risk.risk_per_trade_pct == profile.risk.risk_per_trade_pct
