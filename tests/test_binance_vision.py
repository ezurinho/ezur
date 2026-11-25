"""Binance Vision y el resample: formato, unidades de tiempo y agregación.

Sin red: los ZIP se fabrican en memoria y el CSV de entrada es de tres líneas.
Lo que se prueba es la conversión, que es donde se rompió la primera vez.
"""

from __future__ import annotations

import csv
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


def test_resample_a_quince_minutos_corta_en_el_cubo(tmp_path):
    source = _write_csv(
        tmp_path / "min.csv",
        [
            ["2024-01-01T00:00:00+00:00", "BTC", "100", "101", "99", "100", "1"],
            ["2024-01-01T00:07:00+00:00", "BTC", "100", "103", "98", "102", "1"],
            ["2024-01-01T00:14:00+00:00", "BTC", "102", "102", "95", "96", "1"],
            ["2024-01-01T00:15:00+00:00", "BTC", "96", "99", "96", "99", "1"],
            ["2024-01-01T00:29:00+00:00", "BTC", "99", "100", "97", "98", "1"],
        ],
    )
    result = datasets.resample(source, tmp_path / "q.csv", "15m")
    assert result["rows"] == 2
    with (tmp_path / "q.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["ts"] for row in rows] == [
        "2024-01-01T00:00:00+00:00",
        "2024-01-01T00:15:00+00:00",
    ]
    assert (rows[0]["o"], rows[0]["h"], rows[0]["l"], rows[0]["c"]) == (
        "100.0", "103.0", "95.0", "96.0"
    )
    assert (rows[1]["o"], rows[1]["c"]) == ("96.0", "98.0")


def test_resample_rechaza_una_regla_que_no_existe(tmp_path):
    source = _write_csv(
        tmp_path / "min.csv",
        [["2024-01-01T00:00:00+00:00", "BTC", "1", "2", "0.5", "1.5", "1"]],
    )
    with pytest.raises(ValueError):
        datasets.resample(source, tmp_path / "x.csv", "7D")


# --- descarga y verificación ------------------------------------------------


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args) -> bool:
        return False


def test_download_reutiliza_el_zip_cacheado(tmp_path, monkeypatch):
    cached = tmp_path / "BTCUSDT-1m-2020-01.zip"
    cached.write_bytes(b"zip")

    def explode(*args, **kwargs):
        raise AssertionError("no debe tocar la red si el fichero ya está")

    monkeypatch.setattr(bv.urllib.request, "urlopen", explode)

    path, state = bv.download("2020-01", tmp_path)

    assert path == cached
    assert state == "cached"


def test_download_guarda_el_zip_sin_verificar(tmp_path, monkeypatch):
    monkeypatch.setattr(bv.urllib.request, "urlopen", lambda *a, **k: _Response(b"zip-bytes"))

    path, state = bv.download("2020-01", tmp_path, verify=False)

    assert state == "downloaded"
    assert path.read_bytes() == b"zip-bytes"


def test_download_rechaza_un_fichero_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(bv.urllib.request, "urlopen", lambda *a, **k: _Response(b""))

    with pytest.raises(ValueError, match="vacío"):
        bv.download("2020-01", tmp_path, verify=False)


def test_download_borra_el_zip_si_el_checksum_no_cuadra(tmp_path, monkeypatch):
    monkeypatch.setattr(bv.urllib.request, "urlopen", lambda *a, **k: _Response(b"corrupto"))
    monkeypatch.setattr(bv, "verify_checksum", lambda *a, **k: False)

    with pytest.raises(ValueError, match="sha256"):
        bv.download("2020-01", tmp_path)

    assert not (tmp_path / "BTCUSDT-1m-2020-01.zip").exists()


def test_verify_checksum_compara_con_el_fichero_publicado(tmp_path, monkeypatch):
    target = tmp_path / "mes.zip"
    target.write_bytes(b"contenido")
    import hashlib

    digest = hashlib.sha256(b"contenido").hexdigest()
    monkeypatch.setattr(
        bv.urllib.request, "urlopen", lambda *a, **k: _Response(f"{digest}  mes.zip\n".encode())
    )

    assert bv.verify_checksum(target, "2020-01") is True

    monkeypatch.setattr(
        bv.urllib.request, "urlopen", lambda *a, **k: _Response(b"0" * 64 + b"  mes.zip\n")
    )
    assert bv.verify_checksum(target, "2020-01") is False


def test_verify_checksum_no_acusa_sin_fichero_de_control(tmp_path, monkeypatch):
    target = tmp_path / "mes.zip"
    target.write_bytes(b"contenido")

    def offline(*args, **kwargs):
        raise bv.urllib.error.URLError("sin red")

    monkeypatch.setattr(bv.urllib.request, "urlopen", offline)
    assert bv.verify_checksum(target, "2020-01") is True

    monkeypatch.setattr(bv.urllib.request, "urlopen", lambda *a, **k: _Response(b"\n"))
    assert bv.verify_checksum(target, "2020-01") is True


# --- build ------------------------------------------------------------------


def test_build_convierte_los_zip_en_un_csv_del_bot(tmp_path, monkeypatch):
    source = _zip_with(
        [
            "1577836800000,7195.24,7196.25,7183.14,7186.68,51.64,1577836859999,0,0,0,0,0",
            "1577836860000,7186.68,7190.00,7180.00,7185.00,10.00,1577836919999,0,0,0,0,0",
        ]
    )
    monkeypatch.setattr(bv, "download", lambda *a, **k: (source, "downloaded"))
    calls: list[tuple] = []

    result = bv.build(
        tmp_path / "out.csv",
        tmp_path / "cache",
        ["2020-01"],
        report=lambda *args: calls.append(args),
    )

    assert result["rows"] == 2
    assert result["months"] == 1
    assert result["first"].startswith("2020-01-01")
    assert calls == [("2020-01", 2, 2, "downloaded")]
    with (tmp_path / "out.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0] == {
        "ts": "2020-01-01T00:00:00+00:00",
        "symbol": "BTC",
        "o": "7195.24",
        "h": "7196.25",
        "l": "7183.14",
        "c": "7186.68",
        "v": "51.64",
    }
    source.unlink()


def test_build_explica_que_mes_fallo(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("sin red")

    monkeypatch.setattr(bv, "download", broken)

    with pytest.raises(ValueError, match="2020-01: no se pudo preparar el mes"):
        bv.build(tmp_path / "out.csv", tmp_path / "cache", ["2020-01"])


def test_un_zip_sin_csv_lo_dice(tmp_path):
    path = tmp_path / "sin-csv.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("LEEME.txt", "nada")

    with pytest.raises(ValueError, match="no trae CSV"):
        list(bv.rows(path))
