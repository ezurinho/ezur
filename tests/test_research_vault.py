"""El vault es memoria navegable: si miente o se rompe, no sirve."""
from __future__ import annotations

import json
from pathlib import Path

from server import vault

ARTIFACT = {
    "spec_id": "BTC-X",
    "version": "1.0.0",
    "name": "Prueba de nota",
    "family": "trend",
    "verdict": "REJECTED",
    "generated_at": "2026-11-23T00:00:00+00:00",
    "data": {
        "timeframe_signal": "1d",
        "bars_signal": 100,
        "start": "2020-01-01",
        "end": "2021-01-01",
    },
    "metrics": {
        "all": {"n": 10, "pf_net": 0.817, "win": 0.367, "exp_net_r": -0.1122},
        "oos": {"n": 3, "pf_net": 0.71},
    },
    "gates": {
        "pbo": {"value": 0.2381, "threshold": 0.2, "op": "≤", "pass": False},
        "data_integrity": {"value": 0, "threshold": 0, "op": "==", "pass": True},
    },
    "costs": {"rt_bps": 10.14, "cost_r_mean": 0.0237},
    "benchmark": {"strategy_cagr": -0.0115, "bh_cagr": 0.9698, "alpha_annual": -0.811},
    "stress": {"breakeven_rt_bps": None},
    "artifacts": {"spec_path": "runner/specs/x.json"},
}

RECORD = {
    "ts": "2026-11-23T21:26:00+00:00",
    "id": "BTC-X",
    "family": "trend",
    "timeframe": "1d",
    "verdict": "REJECTED",
    "seconds": 7.2,
}


def _vault(tmp_path: Path, artifacts: list[dict] | None = None) -> Path:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    for index, artifact in enumerate(artifacts or [ARTIFACT]):
        (artifacts_dir / f"spec-{index}.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text(json.dumps(RECORD) + "\n", encoding="utf-8")
    out = tmp_path / "vault"
    vault.write_vault(artifacts_dir=artifacts_dir, ledger=ledger, out_dir=out)
    return out


def test_una_nota_por_artefacto_con_sus_numeros(tmp_path):
    out = _vault(tmp_path)
    note = (out / "specs" / "BTC-X-v1.0.0.md").read_text(encoding="utf-8")

    assert "REJECTED" in note
    assert "pbo" in note and "0.238" in note
    assert "0.817" in note  # PF neto
    assert "runner/specs/x.json" in note  # procedencia


def test_el_indice_enlaza_familias_marcos_y_bitacora(tmp_path):
    out = _vault(tmp_path)
    index = (out / "index.md").read_text(encoding="utf-8")
    family = (out / "Familias" / "Familia - trend.md").read_text(encoding="utf-8")

    assert "[[Familia - trend]]" in index
    assert "[[Marco - 1d]]" in index
    assert "[[Bitacora - 2026-11-23]]" in index
    assert "[[BTC-X-v1.0.0]]" in family


def test_un_vault_recien_escrito_no_tiene_enlaces_rotos(tmp_path):
    out = _vault(tmp_path)

    assert vault.lint_vault(out) == []


def test_el_lint_ve_enlaces_rotos_y_huerfanas(tmp_path):
    out = _vault(tmp_path)
    (out / "suelta.md").write_text("# suelta\n\n[[no-existe]]\n", encoding="utf-8")

    problems = vault.lint_vault(out)

    assert any("enlace roto" in problem and "no-existe" in problem for problem in problems)
    assert any("nota huérfana" in problem and "suelta" in problem for problem in problems)


def test_el_margen_de_una_puerta_respeta_su_operador():
    assert vault.gate_margin({"value": 0.24, "threshold": 0.2, "op": "≤"}) > 0
    assert vault.gate_margin({"value": 0.18, "threshold": 0.2, "op": "≤"}) < 0
    assert vault.gate_margin({"value": 0.79, "threshold": 0.95, "op": "≥"}) > 0
    assert vault.gate_margin({"value": 0, "threshold": 0, "op": "=="}) == 0
    assert vault.gate_margin({"value": None, "threshold": 0.2, "op": "≤"}) is None


def test_el_ranking_ordena_por_puertas_falladas_y_luego_margen():
    def spec(ident, pbo):
        return {
            "spec_id": ident, "version": "1.0.0", "family": "trend", "verdict": "REJECTED",
            "data": {"timeframe_signal": "1d"},
            "metrics": {"all": {"pf_net": 0.9, "n": 10}},
            "gates": {
                "ok": {"value": 0, "threshold": 0, "op": "==", "pass": True},
                "pbo": {"value": pbo, "threshold": 0.2, "op": "≤", "pass": False},
                "dsr": {"value": 0.5, "threshold": 0.95, "op": "≥", "pass": False},
            },
        }

    # La puerta que más cerca queda manda: 0.05 por encima del umbral gana a 0.5.
    rows = vault.ranking([spec("A", 0.30), spec("B", 0.21)])

    assert [row["id"] for row in rows] == ["B", "A"]
    assert rows[0]["blocker"] == "pbo"
    assert abs(rows[0]["margin"] - 0.05) < 1e-9
    assert all(row["failed"] == 2 and row["passed"] == 1 for row in rows)


def test_el_ranking_agrupado_elige_la_mejor_de_cada_familia_y_marco():
    def spec(ident, family, frame, pbo):
        return {
            "spec_id": ident, "version": "1.0.0", "family": family, "verdict": "REJECTED",
            "data": {"timeframe_signal": frame},
            "metrics": {"all": {"pf_net": 0.9, "n": 10}},
            "gates": {"pbo": {"value": pbo, "threshold": 0.2, "op": "≤", "pass": False}},
        }

    rows = vault.ranking(
        [spec("A", "trend", "1d", 0.9), spec("B", "trend", "1d", 0.21), spec("C", "orb", "5m", 0.4)]
    )
    groups = vault.grouped_ranking(rows)

    assert [(group["family"], group["specs"]) for group in groups] == [("trend", 2), ("orb", 1)]
    assert groups[0]["best"]["id"] == "B"


def test_la_auditoria_marca_puertas_constantes_y_las_que_nunca_pasan():
    def spec(dsr, pbo, passed_pbo):
        return {
            "spec_id": "X", "verdict": "REJECTED",
            "gates": {
                "dsr": {"value": dsr, "threshold": 0.95, "op": "≥", "pass": False},
                "pbo": {"value": pbo, "threshold": 0.2, "op": "≤", "pass": passed_pbo},
            },
        }

    audit = vault.gate_audit([spec(0.79, 0.3, False), spec(0.79, 0.1, True)])

    assert [entry["gate"] for entry in audit] == ["dsr"]
    assert audit[0]["constant"] is True and audit[0]["never_passes"] is True
    assert vault.constant_gates([spec(0.79, 0.3, False), spec(0.79, 0.1, True)]) == {"dsr"}


def test_el_ranking_puede_dejar_fuera_una_puerta_constante():
    def spec(ident, pbo):
        return {
            "spec_id": ident, "version": "1.0.0", "family": "trend", "verdict": "REJECTED",
            "data": {"timeframe_signal": "1d"},
            "metrics": {"all": {"pf_net": 0.9, "n": 10}},
            "gates": {
                "dsr": {"value": 0.79, "threshold": 0.95, "op": "≥", "pass": False},
                "pbo": {"value": pbo, "threshold": 0.2, "op": "≤", "pass": False},
            },
        }

    artifacts = [spec("A", 0.5), spec("B", 0.21)]

    con_dsr = vault.ranking(artifacts)
    sin_dsr = vault.ranking(artifacts, ignore={"dsr"})

    # Con dsr: A está más cerca del dsr (0.17) que del pbo (1.5); B del pbo (0.05).
    assert {row["id"]: row["blocker"] for row in con_dsr} == {"A": "dsr", "B": "pbo"}
    assert all(row["blocker"] == "pbo" for row in sin_dsr)
    assert all(row["measured"] == 1 for row in sin_dsr)


def test_el_vault_escribe_el_ranking_y_lo_enlaza(tmp_path):
    out = _vault(tmp_path)

    assert (out / "Ranking.md").is_file()
    assert "[[Ranking]]" in (out / "index.md").read_text(encoding="utf-8")
    assert vault.lint_vault(out) == []


def test_un_artefacto_sin_benchmark_no_rompe_la_nota(tmp_path):
    bare = {key: value for key, value in ARTIFACT.items() if key not in ("benchmark", "stress", "costs")}

    out = _vault(tmp_path, [bare])
    note = (out / "specs" / "BTC-X-v1.0.0.md").read_text(encoding="utf-8")

    assert "CAGR de la estrategia: —" in note
    assert vault.lint_vault(out) == []


def test_al_regenerar_el_vault_no_quedan_notas_de_artefactos_borrados(tmp_path):
    out = _vault(tmp_path)
    assert (out / "specs" / "BTC-X-v1.0.0.md").is_file()

    artifacts_dir = tmp_path / "artifacts"
    for path in artifacts_dir.glob("*.json"):
        path.unlink()
    vault.write_vault(
        artifacts_dir=artifacts_dir,
        ledger=tmp_path / "runs.jsonl",
        out_dir=out,
    )

    assert not (out / "specs" / "BTC-X-v1.0.0.md").exists()
    assert not (out / "Familias" / "Familia - trend.md").exists()
    assert vault.lint_vault(out) == []
