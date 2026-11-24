"""El reset archiva, y si no puede mover un archivo lo dice sin mentir."""
from __future__ import annotations

import sys
from pathlib import Path

from server import reset


def test_run_reset_archiva_la_base_y_el_config(tmp_path):
    db = tmp_path / "terminal.db"
    db.write_text("base", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    result = reset.run_reset(db, config, tmp_path / "backups", confirm=True)

    assert result["executed"] is True
    destination = Path(result["destination"])
    assert (destination / "terminal.db").read_text(encoding="utf-8") == "base"
    assert (destination / "config.json").exists()
    assert not db.exists()


def test_run_reset_no_sigue_si_un_archivo_esta_abierto(tmp_path, monkeypatch):
    db = tmp_path / "terminal.db"
    db.write_text("base", encoding="utf-8")

    def locked(source, target):
        raise PermissionError(13, "el proceso no tiene acceso al archivo")

    monkeypatch.setattr(reset.shutil, "move", locked)

    result = reset.run_reset(db, tmp_path / "config.json", tmp_path / "backups", confirm=True)

    assert result["executed"] is False
    assert "no se pudo mover terminal.db" in result["error"]
    assert result["moved"] == []
    assert db.exists()


def test_main_avisa_y_sale_1_cuando_no_pudo_archivar(tmp_path, monkeypatch, capsys):
    db = tmp_path / "terminal.db"
    db.write_text("base", encoding="utf-8")

    def locked(source, target):
        raise PermissionError(13, "el proceso no tiene acceso al archivo")

    monkeypatch.setattr(reset.shutil, "move", locked)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reset",
            "--db",
            str(db),
            "--config",
            str(tmp_path / "config.json"),
            "--backups",
            str(tmp_path / "backups"),
            "--yes",
        ],
    )

    assert reset.main() == 1
    assert "Cierra el bot" in capsys.readouterr().err
