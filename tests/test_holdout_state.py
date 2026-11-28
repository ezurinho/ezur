from __future__ import annotations

import json

import pytest

from server import holdout
from server.confirmatory import canonical_hash, file_hash
from server.config import Settings
from server.holdout import (
    HOLDOUT_END_EXCLUSIVE,
    HOLDOUT_START,
    HoldoutSealed,
    begin_study,
    consume_study,
    fail_study,
    holdout_config,
    permit_from_id,
    status,
    strategy_payload,
    verify_consumed,
)
from server.strategy.null_strategy import NullStrategy


@pytest.fixture
def holdout_env(tmp_path, monkeypatch):
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
    return dataset, settings, strategy


def _begin(dataset, settings, strategy, *, surface="runner"):
    return begin_study(
        surface=surface,
        dataset_path=dataset,
        dataset_id=file_hash(dataset),
        settings=settings,
        strategy=strategy,
        window=(HOLDOUT_START, HOLDOUT_END_EXCLUSIVE),
    )


def _hashes(settings, strategy):
    return (
        canonical_hash(holdout_config(settings)),
        canonical_hash(strategy_payload(strategy)),
    )


def _rewrite_sealed_ts(lock_path, sealed_ts: str) -> None:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["sealed_ts"] = sealed_ts
    payload["seal_sha256"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "seal_sha256"}
    )
    lock_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_un_sello_posterior_no_abre_el_estudio(holdout_env):
    dataset, settings, strategy = holdout_env
    _rewrite_sealed_ts(holdout.LOCK_FILE, "2026-12-01T00:00:00+00:00")

    with pytest.raises(HoldoutSealed) as error:
        _begin(dataset, settings, strategy)

    assert error.value.code == "HO-003"
    assert "pre-registro" in str(error.value)


def test_la_atestacion_no_vale_con_un_sello_posterior(holdout_env):
    dataset, settings, strategy = holdout_env
    permit = _begin(dataset, settings, strategy)
    evidence = {"dataset_id": file_hash(dataset), "metrics": {"trades": 0}}
    evidence["holdout"] = consume_study(permit.permit_id, evidence)
    _rewrite_sealed_ts(holdout.LOCK_FILE, "2026-12-02T00:00:00+00:00")
    study_hash, strategy_hash = _hashes(settings, strategy)

    verified = verify_consumed(
        evidence,
        dataset_id=file_hash(dataset),
        study_hash=study_hash,
        strategy_hash=strategy_hash,
    )

    assert verified["ok"] is False
    assert verified["checks"]["holdout_atestacion"]["pass"] is False
    assert "pre-registro" in verified["reasons"][0]


def test_el_estudio_pasa_de_ready_a_running_y_se_consume_una_vez(holdout_env):
    dataset, settings, strategy = holdout_env
    assert status()["state"] == "READY"

    permit = _begin(dataset, settings, strategy)
    assert status()["state"] == "RUNNING"
    assert status()["permit"]["permit_id"] == permit.permit_id

    evidence = {"dataset_id": file_hash(dataset), "metrics": {"trades": 0}}
    block = consume_study(permit.permit_id, evidence)
    evidence["holdout"] = block

    assert status()["state"] == "CONSUMED"
    assert status()["promotion_blocked"] is False
    assert holdout.attestation_for(permit.permit_id)["evidence_sha256"] == block[
        "evidence_sha256"
    ]
    study_hash, strategy_hash = _hashes(settings, strategy)
    verified = verify_consumed(
        evidence,
        dataset_id=file_hash(dataset),
        study_hash=study_hash,
        strategy_hash=strategy_hash,
    )
    assert verified["ok"] is True, verified["reasons"]

    with pytest.raises(HoldoutSealed, match="consumido"):
        _begin(dataset, settings, strategy)
    with pytest.raises(HoldoutSealed, match="consumido"):
        permit_from_id(permit.permit_id)


def test_un_fallo_despues_de_reclamar_es_terminal(holdout_env):
    dataset, settings, strategy = holdout_env
    permit = _begin(dataset, settings, strategy)

    fail_study(permit.permit_id, "fallo de prueba")

    assert status()["state"] == "FAILED"
    with pytest.raises(HoldoutSealed, match="falló"):
        _begin(dataset, settings, strategy)


def test_un_ledger_roto_no_se_ignora(holdout_env):
    dataset, settings, strategy = holdout_env
    _begin(dataset, settings, strategy)
    holdout.EVENTS_FILE.write_text("no es json\n", encoding="utf-8")

    assert status()["state"] == "QUARANTINED"
    assert status()["ledger_ok"] is False
    with pytest.raises(HoldoutSealed, match="ledger"):
        _begin(dataset, settings, strategy)


def test_el_permiso_expirado_vuelve_a_ready(holdout_env, monkeypatch):
    dataset, settings, strategy = holdout_env
    monkeypatch.setattr(holdout, "PERMIT_TTL_SECONDS", 0)
    permit = _begin(dataset, settings, strategy)

    with pytest.raises(HoldoutSealed, match="expirado"):
        permit_from_id(permit.permit_id)

    assert status()["state"] == "READY"
    events = holdout._read_events()
    assert events[-1]["event"] == "expired"
    assert events[-1]["code"] == "HO-007"


def test_la_atestacion_no_valida_si_se_cambia_la_evidencia(holdout_env):
    dataset, settings, strategy = holdout_env
    permit = _begin(dataset, settings, strategy)
    evidence = {"dataset_id": file_hash(dataset), "metrics": {"trades": 0}}
    block = consume_study(permit.permit_id, evidence)
    evidence["holdout"] = block
    study_hash, strategy_hash = _hashes(settings, strategy)

    evidence["metrics"]["trades"] = 1
    verified = verify_consumed(
        evidence,
        dataset_id=file_hash(dataset),
        study_hash=study_hash,
        strategy_hash=strategy_hash,
    )

    assert verified["ok"] is False
    assert verified["checks"]["holdout_atestacion"]["pass"] is False


def test_el_ledger_encadena_eventos_y_no_guarda_precios(holdout_env):
    dataset, settings, strategy = holdout_env
    permit = _begin(dataset, settings, strategy)
    consume_study(permit.permit_id, {"dataset_id": file_hash(dataset)})

    events = [json.loads(line) for line in holdout.EVENTS_FILE.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == ["authorized", "claimed", "consumed"]
    assert all(event["chain_hash"] for event in events)
    assert all("price" not in json.dumps(event).lower() for event in events)
    assert events[-1]["consumed_at"]
