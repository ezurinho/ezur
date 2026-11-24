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


def test_un_artefacto_sin_benchmark_no_rompe_la_nota(tmp_path):
    bare = {key: value for key, value in ARTIFACT.items() if key not in ("benchmark", "stress", "costs")}

    out = _vault(tmp_path, [bare])
    note = (out / "specs" / "BTC-X-v1.0.0.md").read_text(encoding="utf-8")

    assert "CAGR de la estrategia: —" in note
    assert vault.lint_vault(out) == []
