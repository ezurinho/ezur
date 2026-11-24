"""El puente al motor: descubre, ejecuta, deduplica y para cuando toca."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import research


def _fake_home(tmp_path: Path, body: str = 'print("VERDICT APPROVED")') -> Path:
    home = tmp_path / "motor"
    (home / "runner" / "specs").mkdir(parents=True)
    (home / "runner" / "run_strategy.py").write_text(body, encoding="utf-8")
    for name, tf in (("a", "1d"), ("b", "4h")):
        (home / "runner" / "specs" / f"{name}.json").write_text(
            json.dumps({"id": name.upper(), "family": "trend", "timeframe_signal": tf}),
            encoding="utf-8",
        )
    return home


def test_research_home_encuentra_el_runner(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    monkeypatch.delenv("EZUR_RESEARCH_HOME", raising=False)
    assert research.research_home(home) == home


def test_research_home_falla_con_mensaje_util(tmp_path, monkeypatch):
    monkeypatch.delenv("EZUR_RESEARCH_HOME", raising=False)
    monkeypatch.setattr(research, "DEFAULT_HOME", tmp_path / "sin-motor")
    with pytest.raises(research.ResearchUnavailable):
        research.research_home(tmp_path / "no-existe")


def test_la_huella_ignora_el_orden_de_las_claves():
    assert research.fingerprint({"a": 1, "b": 2}) == research.fingerprint({"b": 2, "a": 1})
    assert research.fingerprint({"a": 1}) != research.fingerprint({"a": 2})


def test_pending_salta_lo_ya_medido(tmp_path):
    home = _fake_home(tmp_path)
    spec = json.loads((home / "runner" / "specs" / "a.json").read_text(encoding="utf-8"))
    records = [{"fingerprint": research.fingerprint(spec), "verdict": "APPROVED"}]

    queue = research.pending(home, records)

    assert [path.stem for path in queue] == ["b"]


def test_un_fallo_no_marca_la_spec_como_medida(tmp_path):
    home = _fake_home(tmp_path)
    spec = json.loads((home / "runner" / "specs" / "a.json").read_text(encoding="utf-8"))
    records = [{"fingerprint": research.fingerprint(spec), "verdict": None}]

    queue = research.pending(home, records)

    assert [path.stem for path in queue] == ["a", "b"]


def test_run_spec_lee_el_veredicto(tmp_path):
    home = _fake_home(tmp_path)
    spec = home / "runner" / "specs" / "a.json"

    record = research.run_spec(home, "python", spec, out_dir=tmp_path / "out", timeout=30)

    assert record["verdict"] == "APPROVED"
    assert record["id"] == "A"
    assert record["returncode"] == 0


def test_run_spec_registra_el_fallo(tmp_path):
    home = _fake_home(tmp_path, body='import sys; print("boom", file=sys.stderr); sys.exit(3)')
    spec = home / "runner" / "specs" / "a.json"

    record = research.run_spec(home, "python", spec, out_dir=tmp_path / "out", timeout=30)

    assert record["verdict"] is None
    assert record["returncode"] == 3
    assert "boom" in (record["error"] or "")


def test_el_cli_una_vez_escribe_el_ledger(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    ledger = tmp_path / "runs.jsonl"
    monkeypatch.chdir(tmp_path)

    code = research.main(["--home", str(home), "--once", "--ledger", str(ledger)])

    assert code == 0
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["verdict"] == "APPROVED"


def test_el_bucle_respeta_max_runs(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    ledger = tmp_path / "runs.jsonl"
    monkeypatch.chdir(tmp_path)

    code = research.main(
        ["--home", str(home), "--loop", "--max-runs", "2", "--cooldown", "0",
         "--ledger", str(ledger)]
    )

    assert code == 0
    assert len(ledger.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_el_bucle_para_tras_tres_fallos(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, body='import sys; sys.exit(1)')
    ledger = tmp_path / "runs.jsonl"
    monkeypatch.chdir(tmp_path)

    code = research.main(
        ["--home", str(home), "--loop", "--cooldown", "0", "--ledger", str(ledger)]
    )

    assert code == 1
    assert len(ledger.read_text(encoding="utf-8").strip().splitlines()) == 3
