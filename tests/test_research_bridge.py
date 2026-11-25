"""El puente al motor: descubre, ejecuta, deduplica y para cuando toca."""
from __future__ import annotations

import json
import sys
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


def test_pending_salta_lo_ya_medido(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "GENERATED", tmp_path / "sin-generadas")
    home = _fake_home(tmp_path)
    spec = json.loads((home / "runner" / "specs" / "a.json").read_text(encoding="utf-8"))
    records = [{"fingerprint": research.fingerprint(spec), "verdict": "APPROVED"}]

    queue = research.pending(home, records)

    assert [path.stem for path in queue] == ["b"]


def test_un_fallo_no_marca_la_spec_como_medida(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "GENERATED", tmp_path / "sin-generadas")
    home = _fake_home(tmp_path)
    spec = json.loads((home / "runner" / "specs" / "a.json").read_text(encoding="utf-8"))
    records = [{"fingerprint": research.fingerprint(spec), "verdict": None}]

    queue = research.pending(home, records)

    assert [path.stem for path in queue] == ["a", "b"]


def test_las_semillas_nuevas_cumplen_el_esquema():
    template = {
        "id": "BTC-X", "name": "x", "version": "1.0.0", "label": "x",
        "family": "trend", "hypothesis": "h", "instrument": "BTCUSDT_PERP",
        "timeframe_signal": "1d", "data_requirements": {"datasets": ["klines_5m"]},
        "entry": {"rule": "donchian_breakout"}, "exit": {"time_stop_bars": 1},
        "params": {"N": 40, "atr_k": 1.5, "tp_r": 2.0},
        "risk": {}, "costs": {}, "execution": {},
        "validation": {"trials_declared": 8}, "expected": {"turnover_per_year": 1.0},
    }

    blueprints = research.seed_blueprints()
    docs = research.seed_documents(template, blueprints)

    assert len(docs) == len(blueprints)
    assert len({doc["id"] for doc in docs}) == len(docs)
    for doc in docs:
        assert research.ID_PATTERN.fullmatch(doc["id"])
        assert research.LABEL_PATTERN.fullmatch(doc["label"])
        assert doc["validation"]["trials_declared"] == 1
        assert doc["params"] == blueprints[[b["id"] for b in blueprints].index(doc["id"])]["params"]
    # Sin cifras de rendimiento inventadas para una familia que nunca se midió.
    assert all("expected" not in doc for doc in docs)


def test_orb_solo_se_siembra_en_el_marco_que_el_motor_cierra():
    orb = [b for b in research.seed_blueprints() if b["rule"] == "orb_session"]

    assert orb
    # `_orb` cierra la sesión a 96 barras fijas: en 1h serían cuatro días. Y el
    # marco tiene que ser 5m porque pandas 3 rechaza los alias "15m"/"30m" que
    # el esquema del motor sí admite; el resample reventaría antes de medir.
    assert all(b["timeframe_signal"] == "5m" for b in orb)
    assert all(b["params"]["range_bars"] == 12 for b in orb)  # una hora de 5m


def test_las_sesiones_de_una_semilla_viajan_como_dato():
    docs = research.seed_documents({}, research.seed_blueprints())
    orb = next(doc for doc in docs if doc["id"] == "BTC-ORB-5M")

    assert orb["entry"]["sessions"] == ["00:00"]
    assert all("sessions" not in doc["entry"] for doc in docs if doc is not orb)


def test_las_variantes_declaran_los_intentos_de_verdad():
    spec = {
        "id": "BTC-X", "version": "1.0.0", "label": "x",
        "params": {"N": 40, "atr_k": 1.5, "tp_r": 4.0},
        "validation": {"trials_declared": 8},
    }

    out = research.variants(spec)

    assert all(doc["validation"]["trials_declared"] == len(out) + 1 for doc in out)


def test_las_variantes_no_repiten_la_semilla():
    spec = {"id": "BTC-X", "version": "1.4.0", "label": "1d_ens5_vt",
            "params": {"N": 40, "atr_k": 1.5, "tp_r": 4.0}}

    out = research.variants(spec)

    assert out
    assert not any(variant["params"] == spec["params"] for variant in out)
    assert len({variant["id"] for variant in out}) == len(out)
    assert all(research.ID_PATTERN.fullmatch(variant["id"]) for variant in out)
    assert all(research.LABEL_PATTERN.fullmatch(variant["label"]) for variant in out)
    assert all(variant["parent_version"] == "1.4.0" for variant in out)
    assert all(set(variant["params"]) == set(spec["params"]) for variant in out)
    # El esquema del motor prohíbe campos extra: solo estos pueden aparecer.
    assert all(
        set(variant) - set(spec) <= {"params", "id", "label", "parent_version"}
        for variant in out
    )


def test_una_spec_sin_parametros_barribles_no_genera_nada():
    assert research.variants({"id": "Y", "params": {"fast": 12, "slow": 48}}) == []


def test_write_variants_es_idempotente(tmp_path):
    spec = {"id": "X", "params": {"N": 40, "atr_k": 1.5, "tp_r": 4.0}}
    generated = research.variants(spec)

    first = research.write_variants(generated, tmp_path)
    second = research.write_variants(generated, tmp_path)

    assert first == (len(generated), 0)
    assert second == (0, len(generated))


def test_las_variantes_entran_en_la_cola(tmp_path):
    home = _fake_home(tmp_path)
    generated = tmp_path / "generadas"
    generated.mkdir()
    (generated / "v.json").write_text(json.dumps({"id": "V", "params": {"N": 20}}), encoding="utf-8")

    names = {path.stem for path in research.spec_paths(home, generated=generated)}

    assert {"a", "b", "v"} <= names


def test_el_resumen_cuenta_por_familia_y_marco():
    records = [
        {"family": "trend", "timeframe": "1d", "verdict": "REJECTED"},
        {"family": "trend", "timeframe": "1d", "verdict": "APPROVED"},
        {"family": "momentum", "timeframe": "5m", "verdict": None},
    ]

    groups = research.summarize(records)

    assert groups[("trend", "1d")] == {
        "total": 2, "APPROVED": 1, "REJECTED": 1,
        "INCONCLUSIVE": 0, "sin veredicto": 0,
    }
    assert groups[("momentum", "5m")]["sin veredicto"] == 1


def test_el_informe_del_cli_lista_lo_no_rechazado(tmp_path, capsys, monkeypatch):
    home = _fake_home(tmp_path)
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({"family": "trend", "timeframe": "1d", "verdict": "REJECTED", "seconds": 3}),
                json.dumps({"id": "X", "family": "trend", "timeframe": "4h", "verdict": "APPROVED", "seconds": 7}),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    code = research.main(["--home", str(home), "--report", "--ledger", str(ledger)])

    assert code == 0
    out = capsys.readouterr().out
    assert "X 4h -> APPROVED" in out
    assert "2 corridas" in out


def test_el_informe_sin_ledger_no_falla(tmp_path, capsys, monkeypatch):
    home = _fake_home(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = research.main(["--home", str(home), "--report", "--ledger", str(tmp_path / "nada.jsonl")])

    assert code == 0
    assert "ledger vacío" in capsys.readouterr().out


def test_run_spec_lee_el_veredicto(tmp_path):
    home = _fake_home(tmp_path)
    spec = home / "runner" / "specs" / "a.json"

    record = research.run_spec(home, "python", spec, out_dir=tmp_path / "out", timeout=30)

    assert record["verdict"] == "APPROVED"
    assert record["id"] == "A"
    assert record["returncode"] == 0


def test_run_spec_no_acepta_un_artefacto_viejo(tmp_path):
    home = _fake_home(tmp_path)
    spec = home / "runner" / "specs" / "a.json"
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "A-vNone.json"
    stale.write_text(json.dumps({"verdict": "REJECTED"}), encoding="utf-8")

    record = research.run_spec(home, "python", spec, out_dir=out, timeout=30)

    assert record["verdict"] == "APPROVED"


def test_run_spec_pasa_una_ruta_absoluta(tmp_path, monkeypatch):
    """El runner corre en su árbol: el relativo del bot no le sirve."""
    body = (
        "import pathlib, sys\n"
        "spec = pathlib.Path(sys.argv[sys.argv.index('--spec') + 1])\n"
        "assert spec.is_file(), spec\n"
        "print('VERDICT APPROVED')\n"
    )
    home = _fake_home(tmp_path, body=body)
    monkeypatch.chdir(tmp_path)
    relative = home.relative_to(tmp_path) / "runner" / "specs" / "a.json"

    record = research.run_spec(home, sys.executable, relative, out_dir=tmp_path / "out", timeout=30)

    assert record["verdict"] == "APPROVED"


def test_run_spec_pasa_el_ciclo_de_validacion_explicito(tmp_path, monkeypatch):
    body = (
        "import sys\n"
        "assert '--validation' in sys.argv, sys.argv\n"
        "print('VERDICT APPROVED')\n"
    )
    home = _fake_home(tmp_path, body=body)
    monkeypatch.chdir(tmp_path)
    cycle = tmp_path / "cycle.json"
    cycle.write_text("{}", encoding="utf-8")

    record = research.run_spec(
        home, sys.executable, home / "runner" / "specs" / "a.json",
        out_dir=tmp_path / "out", timeout=30, validation=cycle,
    )

    assert record["verdict"] == "APPROVED"
    assert record["validation"] == str(cycle)


def test_run_cycle_escribe_el_artefacto_y_lee_sus_numeros(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    monkeypatch.chdir(tmp_path)  # los ciclos se guardan en el bot, no en el motor
    script = home / "runner" / "selection_cycle.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
        "name = sys.argv[sys.argv.index('--cycle') + 1]\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / f'{name}.json').write_text(json.dumps({\n"
        "    'inputs': {'universe_size': 5},\n"
        "    'pbo': {'pbo': 0.11},\n"
        "    'dsr': {'dsr': 0.96},\n"
        "    'minbtl': {'minbtl_years': 2.5},\n"
        "}))\n",
        encoding="utf-8",
    )

    record = research.run_cycle(
        home, sys.executable, home / "runner" / "specs" / "a.json", axis="N", cycle="CYCLE-TEST"
    )

    assert record["returncode"] == 0
    assert (tmp_path / "data" / "research" / "cycles" / "CYCLE-TEST.json").is_file()
    assert not (home / "runner" / "validation").exists()
    assert record["pbo"] == 0.11 and record["dsr"] == 0.96
    assert record["universe_size"] == 5 and record["minbtl_years"] == 2.5


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


# ---- el veredicto es un dato del artefacto, no una línea de log -------------


def _spec_with_version(tmp_path: Path, version: str = "1.0.0") -> Path:
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"id": "BTC-TEST", "version": version, "family": "trend",
                    "timeframe_signal": "1d"}),
        encoding="utf-8",
    )
    return spec


def _runner_that_writes(verdict: str | None, log: str = "") -> str:
    """Un runner falso que escribe el artefacto (y opcionalmente imprime)."""
    write = ""
    if verdict is not None:
        write = (
            "from pathlib import Path\n"
            "Path(out).mkdir(parents=True, exist_ok=True)\n"
            f"Path(out, f\"{{spec['id']}}-v{{spec['version']}}.json\").write_text("
            f"json.dumps({{'verdict': {verdict!r}}}))\n"
        )
    return (
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "out = args[args.index('--out') + 1]\n"
        "spec = json.loads(Path(args[args.index('--spec') + 1]).read_text())\n"
        + write
        + (f"print({log!r})\n" if log else "")
    )


def test_el_veredicto_sale_del_artefacto_aunque_no_haya_log(tmp_path):
    home = _fake_home(tmp_path, body=_runner_that_writes("REJECTED"))
    record = research.run_spec(
        home, sys.executable, _spec_with_version(tmp_path),
        out_dir=tmp_path / "out", timeout=60,
    )
    assert record["returncode"] == 0
    assert record["verdict"] == "REJECTED"


def test_el_artefacto_manda_sobre_el_log(tmp_path):
    home = _fake_home(
        tmp_path, body=_runner_that_writes("REJECTED", log="VERDICT APPROVED")
    )
    record = research.run_spec(
        home, sys.executable, _spec_with_version(tmp_path),
        out_dir=tmp_path / "out", timeout=60,
    )
    assert record["verdict"] == "REJECTED"


def test_sin_artefacto_se_lee_el_log_antiguo(tmp_path):
    home = _fake_home(tmp_path, body=_runner_that_writes(None, log="VERDICT APPROVED"))
    record = research.run_spec(
        home, sys.executable, _spec_with_version(tmp_path),
        out_dir=tmp_path / "out", timeout=60,
    )
    assert record["verdict"] == "APPROVED"


def test_un_fallo_no_lee_veredicto_ni_del_artefacto(tmp_path):
    body = _runner_that_writes("APPROVED") + "sys.exit(3)\n"
    home = _fake_home(tmp_path, body=body)
    record = research.run_spec(
        home, sys.executable, _spec_with_version(tmp_path),
        out_dir=tmp_path / "out", timeout=60,
    )
    assert record["returncode"] == 3
    assert record["verdict"] is None


def test_el_motor_por_defecto_es_el_del_repo(monkeypatch):
    monkeypatch.delenv("EZUR_RESEARCH_HOME", raising=False)
    assert research.DEFAULT_HOME == research.REPO_ROOT / "research_engine"
    assert (research.DEFAULT_HOME / research.RUNNER).is_file()
    assert research.research_home() == research.DEFAULT_HOME
