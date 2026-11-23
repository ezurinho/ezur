from __future__ import annotations

import json
from pathlib import Path

from server.config import Settings, save_settings
from server.db import Store
from server.diagnostics import diagnose
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
    assert report["schema_version"] == 1
    assert report["journal_mode"] == "wal"
    assert report["integrity"] == "ok"
    assert report["tables"]["events"] == 1
    assert report["missing_tables"] == []


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
