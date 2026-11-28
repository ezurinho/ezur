from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone

import pytest

from server import holdout
from server.backtest import main, run_backtest
from server.confirmatory import canonical_hash, file_hash
from server.stress import run_stress
from server.holdout import HoldoutSealed, guard_window, holdout_config, seal_run
from server.market import synthetic
from server.market.csv_data import validate_dataset
from server.simulation import session_start_utc
from server.strategy.null_strategy import NullStrategy


def _inside() -> tuple[datetime, datetime]:
    return (
        datetime(2026, 12, 1, tzinfo=timezone.utc),
        datetime(2026, 12, 1, 1, tzinfo=timezone.utc),
    )


def _guard(path, settings, first, last, **overrides):
    payload = {
        "start": None,
        "end": None,
        "dataset_path": path,
        "config": holdout_config(settings),
        "strategy": holdout.strategy_payload(NullStrategy()),
    }
    payload.update(overrides)
    return guard_window(first, last, **payload)


def _rewrite_sealed_ts(lock_path, sealed_ts: str) -> None:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["sealed_ts"] = sealed_ts
    payload["seal_sha256"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "seal_sha256"}
    )
    lock_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


@pytest.mark.parametrize(
    "sealed_ts",
    [
        "2026-12-01T00:00:00+00:00",
        "2026-12-01T00:00:01+00:00",
    ],
)
def test_un_sello_posterior_al_inicio_no_autoriza(
    tmp_path, settings, monkeypatch, sealed_ts
):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = tmp_path / "late-seal.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    strategy = NullStrategy()
    seal_run(path, settings, strategy)
    _rewrite_sealed_ts(holdout.LOCK_FILE, sealed_ts)

    with pytest.raises(HoldoutSealed) as error:
        _guard(path, settings, *_inside())

    assert error.value.code == "HO-003"
    assert "pre-registro" in str(error.value)


def test_un_sello_antes_del_inicio_sigue_autorizando(
    tmp_path, settings, monkeypatch
):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = tmp_path / "early-seal.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    strategy = NullStrategy()
    seal_run(path, settings, strategy)
    _rewrite_sealed_ts(holdout.LOCK_FILE, "2026-11-30T23:59:59+00:00")

    trace = _guard(path, settings, *_inside())

    assert trace["authorized"] is True
    assert trace["sealed_ts"] == "2026-11-30T23:59:59+00:00"


def test_holdout_is_not_touched_outside_its_window(tmp_path, settings, monkeypatch):
    monkeypatch.delenv(holdout.SEAL_ENV, raising=False)
    path = tmp_path / "outside.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    trace = _guard(
        path,
        settings,
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc),
    )
    assert trace["overlaps"] is False
    assert trace["authorized"] is False


def test_requested_end_is_exclusive_for_the_holdout(tmp_path, settings, monkeypatch):
    monkeypatch.delenv(holdout.SEAL_ENV, raising=False)
    path = tmp_path / "boundary.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    trace = _guard(
        path,
        settings,
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        datetime(2026, 12, 1, tzinfo=timezone.utc),
        end=datetime(2026, 12, 1, tzinfo=timezone.utc),
    )
    assert trace["overlaps"] is False


def test_holdout_without_unseal_is_rejected(tmp_path, settings, monkeypatch):
    monkeypatch.delenv(holdout.SEAL_ENV, raising=False)
    path = tmp_path / "sealed.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    with pytest.raises(HoldoutSealed, match="está sellado"):
        _guard(path, settings, *_inside())


def test_unseal_without_preregistration_is_rejected(tmp_path, settings, monkeypatch):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    path = tmp_path / "unsealed.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    with pytest.raises(HoldoutSealed, match="pre-registro"):
        _guard(path, settings, *_inside())


def test_a_valid_sello_authorizes_the_exact_run(tmp_path, settings, monkeypatch):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = tmp_path / "sealed.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    strategy = NullStrategy()

    seal_run(path, settings, strategy)
    trace = _guard(path, settings, *_inside())

    assert trace["overlaps"] is True
    assert trace["authorized"] is True
    assert trace["sealed_ts"]


def test_the_sello_rejects_a_changed_risk_profile(tmp_path, settings, monkeypatch):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = tmp_path / "changed.csv"
    path.write_text("ts,symbol\n", encoding="utf-8")
    seal_run(path, settings, NullStrategy())

    changed = settings.model_copy(deep=True)
    changed.risk.risk_per_trade_pct += 0.1
    with pytest.raises(HoldoutSealed, match="sello"):
        _guard(path, changed, *_inside())


def test_the_backtest_never_opens_the_holdout_without_authorization(
    settings, tmp_path, synthetic_csv, monkeypatch
):
    monkeypatch.delenv(holdout.SEAL_ENV, raising=False)
    path = synthetic_csv(tmp_path / "holdout.csv", day="2026-12-01", bars=60)

    with pytest.raises(HoldoutSealed, match="está sellado"):
        run_backtest(settings, path, NullStrategy())


def _aligned_holdout_csv(path, settings, *, bars=60):
    day = date(2026, 12, 1)
    symbols = settings.instruments.symbols
    series = {
        symbol: synthetic.generate_session(
            day.isoformat(),
            symbol,
            start=session_start_utc(settings, day),
            bars=bars,
        )
        for symbol in symbols
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for index in range(bars):
            for symbol in symbols:
                bar = series[symbol][index]
                writer.writerow(
                    [bar.t.isoformat(), symbol, bar.o, bar.h, bar.l, bar.c, bar.v]
                )
    return path


def test_end_to_end_autoriza_ejecuta_y_deja_la_traza_del_ledger(
    settings, tmp_path, monkeypatch
):
    """Sello creado, unseal activo y una corrida real dentro del holdout."""
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = _aligned_holdout_csv(tmp_path / "holdout.csv", settings)
    strategy = NullStrategy()
    seal_run(path, settings, strategy)

    result = run_backtest(settings, path, strategy)

    trace = result.diagnostics["holdout"]
    assert trace["authorized"] is True
    assert trace["state"] == "CONSUMED"
    assert trace["permit_id"]
    assert trace["sealed_ts"]
    assert result.dataset_id == file_hash(path)

    events = [
        json.loads(line)
        for line in holdout.EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event"] for event in events] == ["authorized", "claimed", "consumed"]
    assert events[0]["state_after"] == "AUTHORIZED"
    assert events[1]["state_after"] == "RUNNING"
    assert events[2]["state_after"] == "CONSUMED"
    assert all(event["permit_id"] == trace["permit_id"] for event in events)
    assert events[0]["dataset_id"] == result.dataset_id
    assert events[0]["surface"] == "runner"
    assert events[0]["prereg_sha256"] == "a" * 64
    assert events[0]["seal_sha256"] == file_hash(holdout.LOCK_FILE)
    assert holdout.status()["state"] == "CONSUMED"


def test_una_corrida_autorizada_consume_el_holdout_y_la_segunda_no_pasa(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = _aligned_holdout_csv(tmp_path / "holdout.csv", settings)
    strategy = NullStrategy()
    seal_run(path, settings, strategy)

    first = run_backtest(settings, path, strategy)

    assert first.diagnostics["holdout"]["state"] == "CONSUMED"
    assert first.diagnostics["holdout"]["permit_id"]
    assert holdout.status()["state"] == "CONSUMED"
    with pytest.raises(HoldoutSealed, match="consumido"):
        run_backtest(settings, path, strategy)


def test_el_estres_directo_comparte_un_solo_permiso(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = _aligned_holdout_csv(tmp_path / "holdout.csv", settings)
    strategy = NullStrategy()
    seal_run(path, settings, strategy)

    run_stress(settings, path, strategy)

    assert holdout.status()["state"] == "CONSUMED"
    with pytest.raises(holdout.HoldoutSealed) as error:
        run_stress(settings, path, strategy)
    assert error.value.code == "HO-005"


def test_el_cli_consume_el_holdout_y_la_segunda_corrida_sale_con_dos(
    settings, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = _aligned_holdout_csv(tmp_path / "holdout.csv", settings)
    strategy = NullStrategy()
    seal_run(path, settings, strategy)
    config = tmp_path / "config.json"
    config.write_text(settings.model_dump_json(), encoding="utf-8")
    target = tmp_path / "run.json"
    argv = [
        "backtest",
        "--config",
        str(config),
        "--dataset",
        str(path),
        "--gates",
        "--no-stress",
        "--out",
        str(target),
    ]
    monkeypatch.setattr("sys.argv", argv)

    main()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["holdout"]["state"] == "CONSUMED"
    assert payload["diagnostics"]["holdout"]["state"] == "CONSUMED"

    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "holdout" in capsys.readouterr().err


def test_el_validator_reports_the_dataset_span(
    settings, tmp_path, synthetic_csv
):
    path = synthetic_csv(tmp_path / "span.csv", day="2026-12-01", bars=30)
    report = validate_dataset(path, settings.instruments.symbols)

    assert report.ok is True
    assert report.first_ts is not None
    assert report.last_ts is not None
    assert report.first_ts.date().isoformat() == "2026-12-01"
    assert report.last_ts >= report.first_ts
    assert report.as_dict()["first_ts"].startswith("2026-12-01")
