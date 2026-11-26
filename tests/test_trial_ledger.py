from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from server import selection
from server.trial_ledger import (
    TrialLedger,
    TrialLedgerError,
    reconstruct_ledger,
)


DATASET = {
    "path": "data/btc_5m.pkl",
    "sha256": "sha256:abc",
    "rows": 60,
    "columns": ["ts", "o", "h", "l", "c", "v"],
    "first_ts": "2025-01-01T00:00:00+00:00",
    "last_ts": "2025-03-01T00:00:00+00:00",
    "window": {"from": "2025-01-01", "to": "2025-03-02"},
}


def _matrix(days: int = 60, configs: int = 4, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.DataFrame(
        rng.normal(0.0, 0.01, size=(days, configs)),
        index=index,
        columns=[f"cfg{i}" for i in range(configs)],
    )


def _spec(label: str) -> dict:
    return {
        "id": "BTC-TEST",
        "label": label,
        "version": "1.0.0",
        "group": "BTC-TEST",
        "seed": 7,
        "document": {"id": "BTC-TEST", "label": label},
    }


def _record_matrix(
    path,
    matrix: pd.DataFrame,
    *,
    blocks: int = 6,
    extra_discarded: bool = False,
) -> None:
    with TrialLedger(
        path, cycle_id="CYCLE-TEST", blocks=blocks, dataset=DATASET
    ) as ledger:
        for label in matrix.columns:
            ledger.record_trial(
                spec=_spec(label),
                dataset=DATASET,
                status="evaluated",
                seed=7,
                daily_returns=[
                    {"date": str(day.date()), "r_net": float(value)}
                    for day, value in matrix[label].items()
                ],
                metrics={"trades": 1, "pf_net": 1.0},
            )
        if extra_discarded:
            ledger.record_trial(
                spec=_spec("discarded"),
                dataset=DATASET,
                status="discarded",
                seed=7,
                daily_returns=[],
                metrics=None,
                discard_reason="sin_trades",
            )
        ledger.record_selection(
            selected=matrix.columns[0],
            not_selected=list(matrix.columns[1:]),
            discarded=[],
            pbo={"pbo": None},
            dsr={"dsr": None},
            dsr_config=matrix.columns[0],
        )


def test_reconstruye_pbo_y_dsr_exactos_desde_las_series(tmp_path):
    matrix = _matrix()
    path = tmp_path / "cycle.trials.jsonl"
    _record_matrix(path, matrix)

    report = reconstruct_ledger(path)

    expected_pbo = selection.cscv_pbo(matrix, blocks=6)
    sr_daily = {
        column: selection.sharpe_daily(matrix[column].to_numpy())
        for column in matrix.columns
    }
    best = max(sr_daily, key=sr_daily.get)
    expected_dsr = selection.deflated_sharpe(
        matrix[best].to_numpy(), np.array(list(sr_daily.values()))
    )

    assert report["pbo"]["pbo"] == expected_pbo["pbo"]
    assert report["pbo"]["n_splits"] == expected_pbo["n_splits"]
    assert report["dsr"]["dsr"] == expected_dsr["dsr"]
    assert report["dsr_config"] == best
    assert report["selected"] == best
    assert report["matrix"] == {"days": 60, "columns": 4}
    assert report["discarded"] == []


def test_el_ledger_conserva_dataset_semilla_y_descarte(tmp_path):
    matrix = _matrix()
    path = tmp_path / "cycle.trials.jsonl"
    _record_matrix(path, matrix, extra_discarded=True)

    report = reconstruct_ledger(path)
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    first_trial = next(entry for entry in raw if entry["kind"] == "trial")

    assert first_trial["seed"] == 7
    assert first_trial["dataset"]["sha256"] == DATASET["sha256"]
    assert first_trial["dataset"]["window"] == DATASET["window"]
    assert report["evaluated"] == 4
    assert report["discarded"] == [
        {"label": "discarded", "reason": "sin_trades", "error": None}
    ]


def test_una_linea_manipulada_rompe_la_cadena(tmp_path):
    matrix = _matrix()
    path = tmp_path / "cycle.trials.jsonl"
    _record_matrix(path, matrix)

    lines = path.read_text(encoding="utf-8").splitlines()
    trial = json.loads(lines[1])
    trial["daily_returns"][0]["r_net"] += 1.0
    lines[1] = json.dumps(trial, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(TrialLedgerError, match="cadena rota"):
        reconstruct_ledger(path)


def test_no_se_puede_reutilizar_el_ledger_de_un_ciclo(tmp_path):
    path = tmp_path / "cycle.trials.jsonl"
    with TrialLedger(path, cycle_id="CYCLE-TEST", blocks=6, dataset=DATASET):
        pass

    with pytest.raises(TrialLedgerError, match="ya existe"):
        TrialLedger(path, cycle_id="CYCLE-TEST", blocks=6, dataset=DATASET)
