from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from server.review import ReviewUnavailable, review_2025


def _artifact(*, pnl: float, drawdown: float, units: int, config_hash: str) -> dict:
    return {
        "metrics": {
            "trades": 4,
            "profit_factor": 1.25,
            "pnl_net": pnl,
            "fees": 10.0,
            "max_drawdown": drawdown,
        },
        "diagnostics": {
            "open_position": {
                "side": "long",
                "units": units,
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 110.0,
                "opened_ts": "2025-01-04T12:00:00Z",
                "entry_fees": 1.5,
            }
        },
        "dataset": "data/BTC.csv",
        "window": {"from": "2025-01-01", "to": "2025-01-05"},
        "config_hash": config_hash,
    }


def _write_fixture(tmp_path: Path) -> None:
    promotion = tmp_path / "data" / "research" / "promotion"
    promotion.mkdir(parents=True)
    (promotion / "profile-15m-2025.json").write_text(
        json.dumps(_artifact(pnl=1_000.0, drawdown=500.0, units=21, config_hash="profile-hash")),
        encoding="utf-8",
    )
    (promotion / "profile-15m-2025-cost2x.json").write_text(
        json.dumps(_artifact(pnl=-500.0, drawdown=1_000.0, units=20, config_hash="cost-hash")),
        encoding="utf-8",
    )

    dataset = tmp_path / "data" / "BTC.csv"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        # La última vela está fuera de la ventana y no debe alterar el corte.
        writer.writerows(
            [
                ["2025-01-01T00:00:00+00:00", "BTC", 100, 101, 99, 100, 1],
                ["2025-01-02T00:00:00+00:00", "BTC", 100, 121, 99, 120, 1],
                ["2025-01-03T00:00:00+00:00", "BTC", 120, 121, 89, 90, 1],
                ["2025-01-04T00:00:00+00:00", "BTC", 90, 111, 89, 110, 1],
                ["2025-01-05T00:00:00+00:00", "BTC", 110, 999, 110, 999, 1],
                ["2025-02-01T00:00:00+00:00", "BTC", 999, 999, 999, 999, 1],
            ]
        )


def test_compare_perfil_coste_y_btc(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    review = review_2025(tmp_path, initial_capital=10_000.0)

    assert review["window"] == {"from": "2025-01-01", "to": "2025-01-05"}
    assert review["initial_capital"] == 10_000.0
    profile, cost2x, btc = review["rows"]

    assert profile["id"] == "profile"
    assert profile["pnl_usd"] == pytest.approx(1_000.0)
    assert profile["return_pct"] == pytest.approx(0.10)
    assert profile["drawdown_usd"] == pytest.approx(500.0)
    assert profile["drawdown_pct"] == pytest.approx(-0.05)
    assert profile["open_position"]["units"] == 21

    assert cost2x["id"] == "cost2x"
    assert cost2x["pnl_usd"] == pytest.approx(-500.0)
    assert cost2x["return_pct"] == pytest.approx(-0.05)
    assert cost2x["drawdown_pct"] == pytest.approx(-0.10)
    assert cost2x["open_position"]["units"] == 20

    assert btc["id"] == "btc_bh"
    assert btc["return_pct"] == pytest.approx(0.10)
    assert btc["drawdown_pct"] == pytest.approx(-0.25)
    assert btc["open_position"]["kind"] == "spot"
    assert btc["open_position"]["entry_price"] == pytest.approx(100.0)
    assert review["benchmark"]["last_close"] == pytest.approx(110.0)
    assert review["benchmark"]["bars"] == 4
    assert review["benchmark"]["daily_closes"] == 4


def test_faltan_artefactos_no_se_inventa_la_vista(tmp_path: Path) -> None:
    with pytest.raises(ReviewUnavailable, match="profile-15m-2025.json"):
        review_2025(tmp_path)


def test_ventanas_distintas_se_rechazan(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    cost_path = tmp_path / "data" / "research" / "promotion" / "profile-15m-2025-cost2x.json"
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    cost["window"] = {"from": "2025-01-01", "to": "2025-01-04"}
    cost_path.write_text(json.dumps(cost), encoding="utf-8")

    with pytest.raises(ReviewUnavailable, match="misma ventana"):
        review_2025(tmp_path)
