"""El resumen de velas agrega aunque los símbolos vengan intercalados."""
from __future__ import annotations

import csv

from server.datasets import HEADER, resample


def _write(path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def test_resample_agrega_simbolos_intercalados(tmp_path):
    source = tmp_path / "1m.csv"
    _write(
        source,
        [
            ["2026-11-24T00:00:00+00:00", "BTC", 100, 101, 99, 100.5, 1],
            ["2026-11-24T00:00:00+00:00", "ETH", 10, 11, 9, 10.5, 2],
            ["2026-11-24T00:01:00+00:00", "BTC", 100.5, 102, 100, 101, 1],
            ["2026-11-24T00:01:00+00:00", "ETH", 10.5, 12, 10, 11, 2],
        ],
    )

    report = resample(source, tmp_path / "1h.csv", "1H")

    with (tmp_path / "1h.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert report["rows"] == 2
    by_symbol = {row["symbol"]: row for row in rows}
    assert (float(by_symbol["BTC"]["o"]), float(by_symbol["BTC"]["h"])) == (100.0, 102.0)
    assert (float(by_symbol["BTC"]["l"]), float(by_symbol["BTC"]["c"])) == (99.0, 101.0)
    assert float(by_symbol["BTC"]["v"]) == 2.0
    assert (float(by_symbol["ETH"]["h"]), float(by_symbol["ETH"]["l"])) == (12.0, 9.0)
    assert float(by_symbol["ETH"]["v"]) == 4.0
