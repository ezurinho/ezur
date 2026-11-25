"""El patrón de la CLI del motor: plantilla, ledger, veredictos y subcomandos."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from server import research


def _home(tmp_path: Path, specs: dict | None = None) -> Path:
    home = tmp_path / "motor"
    (home / "runner" / "specs").mkdir(parents=True, exist_ok=True)
    (home / "runner" / "run_strategy.py").write_text("print('ok')\n", encoding="utf-8")
    for name, document in (specs or {"a": {"id": "A", "family": "trend", "timeframe_signal": "1d"}}).items():
        (home / "runner" / "specs" / f"{name}.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
    return home


def _template(tmp_path: Path) -> dict:
    return {
        "id": "BTC-X",
        "name": "x",
        "version": "1.0.0",
        "label": "x",
        "family": "trend",
        "hypothesis": "h",
        "instrument": "BTCUSDT_PERP",
        "timeframe_signal": "1d",
        "entry": {"rule": "donchian_breakout"},
        "exit": {"time_stop_bars": 1},
        "params": {"N": 40},
        "validation": {"trials_declared": 3},
    }


# --- intérprete -------------------------------------------------------------


def test_el_interprete_respeta_la_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EZUR_RESEARCH_PYTHON", "/raro/python")

    assert research.interpreter(tmp_path) == "/raro/python"


def test_el_interprete_prefiere_el_venv_del_motor(tmp_path, monkeypatch):
    monkeypatch.delenv("EZUR_RESEARCH_PYTHON", raising=False)
    venv = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv.parent.mkdir(parents=True)
    venv.write_text("", encoding="utf-8")

    assert research.interpreter(tmp_path) == str(venv)


def test_sin_venv_usa_el_python_actual(tmp_path, monkeypatch):
    monkeypatch.delenv("EZUR_RESEARCH_PYTHON", raising=False)

    assert research.interpreter(tmp_path) == sys.executable


# --- plantilla y semillas ---------------------------------------------------


def test_la_plantilla_prefiere_la_spec_de_tendencia(tmp_path):
    home = _home(tmp_path, {"otra": {"id": "OTRA"}, "btc-trend-1d-donchian-40": {"id": "DONCH"}})

    assert research._base_template(home)["id"] == "DONCH"


def test_la_plantilla_sin_la_preferida_usa_la_primera_ordenada(tmp_path):
    home = _home(tmp_path, {"zeta": {"id": "ZETA"}, "alfa": {"id": "ALFA"}})

    assert research._base_template(home)["id"] == "ALFA"


def test_un_motor_sin_specs_lo_dice(tmp_path):
    home = tmp_path / "vacio"
    (home / "runner" / "specs").mkdir(parents=True)

    with pytest.raises(research.ResearchUnavailable, match="no hay specs"):
        research._base_template(home)


# --- escritura y ledger -----------------------------------------------------


def test_write_variants_corrige_una_spec_vieja(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"id": "X", "extra": true}', encoding="utf-8")

    written, skipped = research.write_variants([{"id": "X"}], tmp_path)

    assert (written, skipped) == (1, 0)
    assert json.loads(path.read_text(encoding="utf-8")) == {"id": "X"}


def test_load_ledger_tolera_lineas_vacias_y_rotas(tmp_path):
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text('{"a": 1}\n\nno es json\n{"b": 2}\n', encoding="utf-8")

    assert research.load_ledger(ledger) == [{"a": 1}, {"b": 2}]
    assert research.load_ledger(tmp_path / "no-existe.jsonl") == []


def test_measured_se_queda_con_el_ultimo_veredicto(tmp_path):
    records = [
        {"fingerprint": "f", "verdict": "REJECTED"},
        {"fingerprint": "f", "verdict": None},
        {"fingerprint": "g", "verdict": "APPROVED"},
    ]

    done = research.measured(records)

    assert set(done) == {"f", "g"}
    assert done["f"]["verdict"] == "REJECTED"


def test_append_crea_el_directorio_y_anade_una_linea(tmp_path):
    ledger = tmp_path / "sub" / "runs.jsonl"

    research._append({"id": "A"}, ledger)
    research._append({"id": "B"}, ledger)

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["A", "B"]


def test_pending_ignora_ficheros_ilegibles(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "GENERATED", tmp_path / "sin-generadas")
    home = _home(tmp_path)
    (home / "runner" / "specs" / "roto.json").write_text("{", encoding="utf-8")

    assert [path.stem for path in research.pending(home, [])] == ["a"]


# --- veredictos -------------------------------------------------------------


def test_parse_verdict_lee_la_ultima_linea_util():
    assert research._parse_verdict("ruido\nVERDICT APPROVED\n") == "APPROVED"
    assert research._parse_verdict("  VERDICT REJECTED  ") == "REJECTED"
    assert research._parse_verdict("VERDICT ") is None
    assert research._parse_verdict("sin veredicto") is None


def test_artifact_path_usa_id_y_version(tmp_path):
    path = research._artifact_path(tmp_path, {"id": "BTC-X", "version": "1.2.3"})

    assert path.name == "BTC-X-v1.2.3.json"
    assert path.parent == tmp_path.resolve()


def test_el_artefacto_con_otro_hash_no_vale(tmp_path, monkeypatch):
    spec = {"id": "BTC-X", "version": "1.0.0"}
    artifact = tmp_path / "BTC-X-v1.0.0.json"
    artifact.write_text(
        json.dumps({"verdict": "APPROVED", "artifacts": {"spec_hash": "sha256:otro"}}),
        encoding="utf-8",
    )

    assert research._verdict_from_artifact(tmp_path, spec, 0.0) is None


def test_el_artefacto_con_el_hash_de_la_spec_vale(tmp_path):
    spec = {"id": "BTC-X", "version": "1.0.0"}
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    artifact = tmp_path / "BTC-X-v1.0.0.json"
    artifact.write_text(
        json.dumps({"verdict": "APPROVED", "artifacts": {"spec_hash": f"sha256:{digest}"}}),
        encoding="utf-8",
    )

    assert research._verdict_from_artifact(tmp_path, spec, 0.0) == "APPROVED"


def test_un_artefacto_roto_no_da_veredicto(tmp_path):
    artifact = tmp_path / "BTC-X-v1.0.0.json"
    artifact.write_text("{", encoding="utf-8")

    assert research._verdict_from_artifact(tmp_path, {"id": "BTC-X", "version": "1.0.0"}, 0.0) is None


def test_spec_by_id_encuentra_por_nombre_y_salta_rotos(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "GENERATED", tmp_path / "sin-generadas")
    home = _home(tmp_path, {"a": {"id": "A"}})
    (home / "runner" / "specs" / "roto.json").write_text("{", encoding="utf-8")

    assert research.spec_by_id(home, "A").name == "a.json"
    assert research.spec_by_id(home, "NO-EXISTE") is None


# --- timeouts ---------------------------------------------------------------


def test_run_spec_registra_el_timeout(tmp_path, monkeypatch):
    home = _home(tmp_path)
    spec = home / "runner" / "specs" / "a.json"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5, output="parcial")

    monkeypatch.setattr(research.subprocess, "run", timeout)

    record = research.run_spec(home, "python", spec, out_dir=tmp_path / "out", timeout=5)

    assert record["returncode"] == -9
    assert "timeout" in record["error"]
    assert record["output"] == "parcial"


def test_run_cycle_registra_el_timeout_y_un_artefacto_ilegible(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.chdir(tmp_path)
    cycles = tmp_path / "data" / "research" / "cycles"
    cycles.mkdir(parents=True)
    (cycles / "CYCLE-X.json").write_text("{", encoding="utf-8")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(research.subprocess, "run", timeout)

    record = research.run_cycle(
        home, "python", home / "runner" / "specs" / "a.json", cycle="CYCLE-X"
    )

    assert record["returncode"] == -9
    assert "timeout" in record["error"]
    assert record["pbo"] is None and record["universe_size"] is None


# --- subcomandos ------------------------------------------------------------


def test_sin_motor_el_cli_sale_con_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(research, "DEFAULT_HOME", tmp_path / "no-hay")
    monkeypatch.delenv("EZUR_RESEARCH_HOME", raising=False)

    code = research.main(["--home", str(tmp_path / "tampoco"), "--list"])

    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_el_cli_sin_accion_imprime_la_ayuda(tmp_path, capsys):
    home = _home(tmp_path)

    code = research.main(["--home", str(home)])

    assert code == 0
    assert "Puente único" in capsys.readouterr().out


def test_el_cli_siembra_en_el_motor(tmp_path, capsys):
    home = _home(tmp_path)

    code = research.main(["--home", str(home), "--seeds"])

    assert code == 0
    assert "semillas:" in capsys.readouterr().out
    assert len(list((home / "runner" / "specs").glob("*.json"))) > 1


def test_el_cli_genera_variantes(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path, {"a": {"id": "A", "label": "a", "version": "1.0.0", "params": {"N": 40}}})
    # La carpeta por defecto se fija al importar el módulo: se cambia el cwd.
    monkeypatch.chdir(tmp_path)

    code = research.main(["--home", str(home), "--generate"])

    assert code == 0
    assert "variantes:" in capsys.readouterr().out
    assert list((tmp_path / "data" / "research" / "specs").glob("*.json"))


def test_el_cli_lista_las_specs_y_su_estado(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(research, "GENERATED", tmp_path / "sin-generadas")
    home = _home(tmp_path)
    ledger = tmp_path / "runs.jsonl"

    code = research.main(["--home", str(home), "--list", "--ledger", str(ledger)])

    out = capsys.readouterr().out
    assert code == 0
    assert "pendiente" in out
    assert "motor" in out and "0 corridas" in out


def test_el_cli_cycle_sin_spec_base_devuelve_1(tmp_path, capsys, monkeypatch):
    from server import vault

    home = _home(tmp_path)
    monkeypatch.setattr(vault, "read_artifacts", lambda *a, **k: [])

    code = research.main(["--home", str(home), "--cycle"])

    assert code == 1
    assert "no encuentro la spec base" in capsys.readouterr().out


def test_el_cli_cycle_resume_lo_medido(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(
        research,
        "run_cycle",
        lambda *a, **k: {
            "cycle": "C1",
            "path": "data/research/cycles/C1.json",
            "returncode": 0,
            "seconds": 1.0,
            "error": None,
            "output": None,
            "pbo": 0.1,
            "dsr": 0.97,
            "minbtl_years": 3.0,
            "universe_size": 9,
        },
    )

    code = research.main(["--home", str(home), "--cycle", "--cycle-spec", "A"])

    out = capsys.readouterr().out
    assert code == 0
    assert "9 configuraciones" in out
    assert "--once --validation" in out


def test_el_cli_cycle_fallido_devuelve_1(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(
        research,
        "run_cycle",
        lambda *a, **k: {
            "cycle": "C1",
            "path": "x",
            "returncode": 1,
            "seconds": 1.0,
            "error": "boom",
            "output": None,
            "pbo": None,
            "dsr": None,
            "minbtl_years": None,
            "universe_size": None,
        },
    )

    code = research.main(["--home", str(home), "--cycle", "--cycle-spec", "A"])

    assert code == 1
    assert "el ciclo falló" in capsys.readouterr().out


def test_el_cli_rank_sin_artefactos(tmp_path, capsys, monkeypatch):
    from server import vault

    home = _home(tmp_path)
    monkeypatch.setattr(vault, "read_artifacts", lambda *a, **k: [])

    code = research.main(["--home", str(home), "--rank"])

    assert code == 0
    assert "sin artefactos" in capsys.readouterr().out


def test_el_cli_vault_lint_informa(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(research, "lint_vault", lambda path: ["nota huérfana"])

    code = research.main(["--home", str(home), "--vault-lint", "--vault-dir", str(tmp_path)])

    assert code == 1
    assert "nota huérfana" in capsys.readouterr().out


def test_el_cli_vault_escribe_la_memoria(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(
        research,
        "write_vault",
        lambda out_dir: {"notes": 2, "specs": 1, "families": 1, "frames": 1, "links": 3},
    )

    code = research.main(["--home", str(home), "--vault", "--vault-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "2 notas" in out
