"""Binance Vision y el resample: formato, unidades de tiempo y agregación.

Sin red: los ZIP se fabrican en memoria y el CSV de entrada es de tres líneas.
Lo que se prueba es la conversión, que es donde se rompió la primera vez.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from server import datasets
from server.market import binance_vision as bv


def test_months_recorre_el_rango_inclusive():
    assert bv.months("2020-01", "2020-03") == ["2020-01", "2020-02", "2020-03"]
    assert bv.months("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    assert bv.months("2026-10", "2026-10") == ["2026-10"]


def test_months_rechaza_un_rango_invertido_o_mal_escrito():
    with pytest.raises(ValueError):
        bv.months("2020-03", "2020-01")
    with pytest.raises(ValueError):
        bv.months("2020-13", "2021-01")


def test_url_apunta_al_fichero_mensual():
    assert bv.url_for("2020-01") == (
        "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/"
        "BTCUSDT-1m-2020-01.zip"
    )


def _zip_with(rows: list[str]) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    path = Path(handle.name)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("BTCUSDT-1m-2020-01.csv", "\n".join(rows) + "\n")
    return path


def test_rows_acepta_milisegundos_de_2020():
    path = _zip_with(
        [
            "open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_base,taker_quote,ignore",
            "1577836800000,7195.24,7196.25,7183.14,7186.68,51.64,1577836859999,0,0,0,0,0",
        ]
    )
    try:
        rows = list(bv.rows(path))
    finally:
        path.unlink()
    assert rows == [("2020-01-01T00:00:00+00:00", "7195.24", "7196.25", "7183.14", "7186.68", "51.64")]


def test_rows_acepta_microsegundos_de_2025():
    # Binance cambió la unidad en 2025: 1,735,689,600,000,000 µs = 2025-01-01.
    path = _zip_with(
        [
            "1735689600000000,94000.00,94100.00,93900.00,94050.00,12.5,1735689659999999,0,0,0,0,0"
        ]
    )
    try:
        rows = list(bv.rows(path))
    finally:
        path.unlink()
    assert rows[0][0] == "2025-01-01T00:00:00+00:00"
    assert rows[0][4] == "94050.00"


def _write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(datasets.HEADER)
        writer.writerows(rows)
    return path


def test_resample_a_diario_agrega_ohlcv(tmp_path):
    source = _write_csv(
        tmp_path / "min.csv",
        [
            ["2024-01-01T00:00:00+00:00", "BTC", "100", "110", "99", "105", "1"],
            ["2024-01-01T12:00:00+00:00", "BTC", "105", "120", "104", "118", "2"],
            ["2024-01-01T23:59:00+00:00", "BTC", "118", "119", "90", "95", "3"],
            ["2024-01-02T00:00:00+00:00", "BTC", "95", "97", "94", "96", "4"],
        ],
    )
    result = datasets.resample(source, tmp_path / "day.csv", "1D")
    assert result["rows"] == 2
    with (tmp_path / "day.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0] == {
        "ts": "2024-01-01T00:00:00+00:00",
        "symbol": "BTC",
        "o": "100.0",
        "h": "120.0",
        "l": "90.0",
        "c": "95.0",
        "v": "6.0",
    }
    assert rows[1]["o"] == "95.0" and rows[1]["c"] == "96.0"


def test_resample_rechaza_una_regla_que_no_existe(tmp_path):
    source = _write_csv(
        tmp_path / "min.csv",
        [["2024-01-01T00:00:00+00:00", "BTC", "1", "2", "0.5", "1.5", "1"]],
    )
    with pytest.raises(ValueError):
        datasets.resample(source, tmp_path / "x.csv", "7D")
