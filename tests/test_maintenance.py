from __future__ import annotations

import json
from pathlib import Path

from server.config import Settings, save_settings
from server.db import Store
from server.diagnostics import diagnose
from server.migrations import CURRENT_VERSION
from server.reset import plan_reset, run_reset


def test_diagnose_missing_database(tmp_path):
    report = diagnose(tmp_path / "nope.db")
    assert report["exists"] is False
    assert report["errors"]


def test_diagnose_reports_schema_and_counts(tmp_path):
    path = tmp_path / "terminal.db"
    store = Store(path)
    store.insert_event("info", "test", "hola")
    store.close()

    report = diagnose(path)
    assert report["exists"] is True
    assert report["schema_version"] == CURRENT_VERSION
    assert report["journal_mode"] == "wal"
    assert report["integrity"] == "ok"
    assert report["tables"]["events"] == 1
    assert report["missing_tables"] == []
    assert report["ledger"]["impossible"] == []


def test_diagnose_does_not_write(tmp_path):
    path = tmp_path / "terminal.db"
    Store(path).close()
    before = path.stat().st_size
    diagnose(path)
    assert path.stat().st_size == before


def test_reset_plan_lists_existing_files(tmp_path):
    db = tmp_path / "data" / "terminal.db"
    db.parent.mkdir(parents=True)
    Store(db).close()
    config = db.parent / "config.json"
    save_settings(Settings(), config)

    plan = plan_reset(db, config, tmp_path / "backups")
    assert plan["empty"] is False
    assert any(item.endswith("terminal.db") for item in plan["files"])
    assert any(item.endswith("config.json") for item in plan["files"])
    assert Path(plan["destination"]).exists() is False


def test_reset_without_confirm_does_nothing(tmp_path):
    db = tmp_path / "data" / "terminal.db"
    db.parent.mkdir(parents=True)
    Store(db).close()
    result = run_reset(db, db.parent / "config.json", tmp_path / "backups")
    assert result["executed"] is False
    assert db.exists()


def test_reset_moves_files_and_leaves_clean_state(tmp_path):
    db = tmp_path / "data" / "terminal.db"
    db.parent.mkdir(parents=True)
    Store(db).close()
    config = db.parent / "config.json"
    save_settings(Settings(), config)

    result = run_reset(db, config, tmp_path / "backups", confirm=True)
    assert result["executed"] is True
    assert db.exists() is False
    assert config.exists() is False
    assert Path(result["destination"]).is_dir()
    assert (Path(result["destination"]) / "config.json").exists()

    settings = json.loads((Path(result["destination"]) / "config.json").read_text())
    assert settings["risk"]["risk_per_trade_pct"] == 1.0


def test_reset_on_empty_state_is_a_noop(tmp_path):
    result = run_reset(tmp_path / "a.db", tmp_path / "b.json", tmp_path / "backups", confirm=True)
    assert result["empty"] is True
    assert result["executed"] is False


def test_reset_cli_dry_run_changes_nothing(tmp_path, monkeypatch, capsys):
    from server.db import Store
    from server import reset

    db = tmp_path / "terminal.db"
    store = Store(db)
    store.insert_event("info", "engine", "hola")
    store.close()

    monkeypatch.setattr(
        "sys.argv",
        ["reset", "--db", str(db), "--config", str(tmp_path / "config.json"),
         "--backups", str(tmp_path / "backups"), "--dry-run"],
    )
    reset.main()
    out = capsys.readouterr().out
    assert "Plan (nada modificado)" in out
    assert db.exists()


def test_reset_cli_archives_when_confirmed(tmp_path, monkeypatch, capsys):
    from server.db import Store
    from server import reset

    db = tmp_path / "terminal.db"
    store = Store(db)
    store.insert_event("info", "engine", "hola")
    store.close()

    monkeypatch.setattr(
        "sys.argv",
        ["reset", "--db", str(db), "--config", str(tmp_path / "config.json"),
         "--backups", str(tmp_path / "backups"), "--yes"],
    )
    reset.main()
    assert "Archivado en" in capsys.readouterr().out
    archived = list((tmp_path / "backups").rglob("terminal.db*"))
    assert archived


def test_diagnostics_cli_prints_json(tmp_path, monkeypatch, capsys):
    from server.db import Store
    from server import diagnostics

    db = tmp_path / "terminal.db"
    store = Store(db)
    store.insert_event("info", "engine", "hola")
    store.close()

    monkeypatch.setattr("sys.argv", ["diagnostics", "--db", str(db)])
    diagnostics.main()
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["exists"] is True
    assert payload["integrity"] == "ok"
    assert payload["missing_tables"] == []


def _seed_trade(store: Store, closed, pnl_net: float = 10.0):
    from datetime import datetime, timezone

    from server.models import TradeRecord

    trade = TradeRecord(
        symbol="BTC",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=110.0,
        opened_ts=datetime(2026, 11, 24, 1, 0, tzinfo=timezone.utc),
        closed_ts=closed,
        pnl_net=pnl_net,
    )
    return store.insert_trade_once(trade)


def test_diagnose_audita_las_tres_copias_del_libro(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    closed = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
    _seed_trade(store, closed, pnl_net=10.0)
    store.kv_set("equity", 25_010.0)
    store.kv_set("peak_equity", 25_010.0)
    store.append_equity(25_010.0, closed)
    store.close()

    books = diagnose(path, 25_000.0)["books"]

    assert books["checked"] is True
    assert books["book_equity"] == 25_010.0
    assert books["consistent"] is True
    assert books["differences"] == {}


def test_diagnose_señala_la_copia_que_se_desvió(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    closed = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
    _seed_trade(store, closed, pnl_net=10.0)
    store.kv_set("equity", 24_990.0)
    store.kv_set("peak_equity", 25_010.0)
    store.append_equity(25_010.0, closed)
    store.close()

    books = diagnose(path, 25_000.0)["books"]

    assert books["consistent"] is False
    assert books["differences"]["state_vs_book"] == -20.0
    assert "curve_vs_book" not in books["differences"]


def test_diagnose_compara_instantes_y_no_texto(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    _seed_trade(store, datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc))
    # 05:00+02:00 son las 03:00Z: cierra antes de abrir. Como texto parecería
    # posterior a las 04:05Z y la comprobación antigua no lo veía.
    store.conn.execute(
        "UPDATE trades SET opened_ts = ?, closed_ts = ? WHERE id = 1",
        ("2026-11-24T04:05:00+00:00", "2026-11-24T05:00:00+02:00"),
    )
    store.conn.commit()
    store.close()

    ledger = diagnose(path)["ledger"]

    assert [row["id"] for row in ledger["impossible"]] == [1]

def test_diagnose_entiende_un_pico_reiniciado(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    _seed_trade(store, datetime(2026, 11, 24, 1, 30, tzinfo=timezone.utc), pnl_net=1000.0)
    _seed_trade(store, datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc), pnl_net=-990.0)
    store.kv_set("equity", 25_010.0)
    store.kv_set("peak_equity", 25_010.0)
    store.append_equity(26_000.0, datetime(2026, 11, 24, 1, 30, tzinfo=timezone.utc))
    store.append_equity(25_010.0, datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc))
    store.conn.execute(
        "INSERT INTO events (ts, level, category, message, meta) VALUES (?,?,?,?,?)",
        (
            "2026-11-24T03:00:00+00:00",
            "warn",
            "risk",
            "pico reiniciado a la equity del libro: 26000.0 -> 25010.0",
            json.dumps({"before": 26_000.0, "after": 25_010.0}),
        ),
    )
    store.conn.commit()
    store.close()

    books = diagnose(path, 25_000.0)["books"]

    assert books["peak_reset_at"] == "2026-11-24T03:00:00+00:00"
    assert books["peak_expected"] == 25_010.0
    assert books["differences"] == {}
    assert books["consistent"] is True

def _perfil(tmp_path, risk: dict) -> Path:
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps({"risk": risk}), encoding="utf-8"
    )
    return profile


def test_diagnose_avisa_cuando_la_parada_dura_esta_activa(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    closed = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
    _seed_trade(store, closed, pnl_net=-3_000.0)
    store.kv_set("equity", 22_000.0)
    store.kv_set("peak_equity", 25_000.0)
    store.append_equity(22_000.0, closed)
    store.close()

    books = diagnose(
        path,
        25_000.0,
        {"max_drawdown_pct": 5.0, "halt_multiple": 2.0, "soft_brakes": True},
    )["books"]

    assert books["drawdown_pct"] == 12.0
    assert books["halt_at_pct"] == 10.0
    assert books["halted"] is True


def test_diagnose_no_avisa_si_el_drawdown_esta_dentro(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    closed = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
    _seed_trade(store, closed, pnl_net=-500.0)
    store.kv_set("equity", 24_500.0)
    store.kv_set("peak_equity", 25_000.0)
    store.append_equity(24_500.0, closed)
    store.close()

    books = diagnose(
        path,
        25_000.0,
        {"max_drawdown_pct": 5.0, "halt_multiple": 2.0, "soft_brakes": True},
    )["books"]

    assert books["halted"] is False
    assert books["halt_at_pct"] == 10.0


def test_el_cli_lee_los_limites_del_perfil(tmp_path, capsys):
    from datetime import datetime, timezone

    path = tmp_path / "terminal.db"
    store = Store(path)
    closed = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
    _seed_trade(store, closed, pnl_net=-3_000.0)
    store.kv_set("equity", 22_000.0)
    store.kv_set("peak_equity", 25_000.0)
    store.append_equity(22_000.0, closed)
    store.close()
    from server import diagnostics

    profile = _perfil(
        tmp_path,
        {
            "initial_capital": 25_000.0,
            "max_drawdown_pct": 5.0,
            "soft_brake_halt_multiple": 2.0,
            "soft_brakes": True,
        },
    )

    assert diagnostics.main(["--db", str(path), "--profile", str(profile)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["books"]["halted"] is True
