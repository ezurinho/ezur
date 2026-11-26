"""Walk-forward con el ganador congelado y PBO/DSR sobre la serie OOS unida."""

import numpy as np
import pandas as pd

from server.selection import walk_forward


def _log(seed: int, edge: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range("2025-01-01", periods=120, freq="D", tz="UTC")
    returns = np.repeat(rng.normal(edge, 1.0, len(days)), 2)
    return pd.DataFrame({"ts": np.repeat(days, 2), "r_net": returns})


def test_el_walk_forward_congela_y_reporta_pbo_dsr_oos():
    universe = {
        "fuerte": _log(1, 0.20),
        "plano": _log(2, 0.00),
        "debil": _log(3, -0.10),
    }

    report = walk_forward(universe, folds=3, min_is_trades=3, warmup=0.30)

    assert report["frozen_selection"] is True
    chosen = [fold for fold in report["folds"] if fold["chosen"]]
    assert chosen
    assert all(fold["chosen_frozen"] is True for fold in chosen)
    assert all(fold["oos_rank_pct"] is not None for fold in chosen)
    assert report["pbo_folds"] is not None
    assert 0.0 <= report["pbo_folds"] <= 1.0
    assert "dsr" in report["dsr_oos"]
    assert report["pbo_oos_matrix"]["pbo"] is not None
    assert report["oos_daily_days"] >= 30
