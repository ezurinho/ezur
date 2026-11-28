from __future__ import annotations

from server.experiments import build_record, load, record


def _common() -> dict:
    return {
        "kind": "backtest",
        "strategy_id": "reference",
        "strategy_version": "0.1.0",
        "dataset_id": "d" * 64,
        "config": {"risk": {"risk_per_trade_pct": 1.0}},
        "metrics": {"trades": 10, "profit_factor": 1.2},
        "verdict": "RECHAZADA",
    }


def test_el_asiento_guarda_la_autorizacion_del_holdout(tmp_path):
    trace = {
        "authorized": True,
        "state": "RUNNING",
        "permit_id": "hp_123",
        "study_id": "study_123",
        "sealed_ts": "2026-11-30T12:00:00+00:00",
        "window": [
            "2026-12-01T00:00:00+00:00",
            "2026-12-01T01:00:00+00:00",
        ],
        "expires_at": "2026-11-30T12:05:00+00:00",
        "overlaps": True,
    }

    entry = record(tmp_path / "ledger.jsonl", **_common(), holdout=trace)

    assert load(tmp_path / "ledger.jsonl") == [entry]
    assert entry["holdout"] == {
        key: value for key, value in trace.items() if key != "overlaps"
    }


def test_una_corrida_sin_holdout_conserva_el_asiento_sin_traza(tmp_path):
    entry = build_record(
        **_common(),
        holdout={"authorized": False, "overlaps": False, "window": None},
    )

    assert "holdout" not in entry
