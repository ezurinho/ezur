"""Datasets en disco: lo que se descarga, se agrega y se escribe para el backtest."""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server import datasets
from server.config import Settings
from server.models import Bar

START = datetime(2026, 1, 15, 10, 7, tzinfo=timezone.utc)


def _bar(minutes: int, price: float = 100.0, symbol: str | None = None) -> Bar:
    return Bar(t=START + timedelta(minutes=minutes), o=price, h=price + 1, l=price - 1, c=price, v=5.0)


def _write_source(path: Path, rows: list[tuple]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(datasets.HEADER)
        for stamp, symbol, open_, high, low, close, volume in rows:
            writer.writerow([stamp, symbol, open_, high, low, close, volume])
    return path


# --- cubos ------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule,expected",
    [
        ("1D", datetime(2026, 1, 15, tzinfo=timezone.utc)),
        ("4H", datetime(2026, 1, 15, 8, tzinfo=timezone.utc)),
        ("1H", datetime(2026, 1, 15, 10, tzinfo=timezone.utc)),
        ("15m", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)),
    ],
)
def test_los_cubos_caen_en_el_borde_utc(rule, expected):
    assert datasets._bucket(START, rule) == expected


def test_una_regla_desconocida_lo_dice():
    with pytest.raises(ValueError, match="regla no soportada"):
        datasets._bucket(START, "7D")


# --- resample ---------------------------------------------------------------


def test_resample_agrega_con_simbolos_intercalados(tmp_path):
    source = _write_source(
        tmp_path / "source.csv",
        [
            (START.isoformat(), "AAA", 100.0, 101.0, 99.0, 100.5, 2.0),
            (START.isoformat(), "BBB", 200.0, 201.0, 199.0, 200.5, 3.0),
            ((START + timedelta(minutes=5)).isoformat(), "AAA", 100.5, 104.0, 100.0, 103.0, 1.0),
            ((START + timedelta(minutes=5)).isoformat(), "BBB", 200.5, 202.0, 198.0, 199.0, 4.0),
            ((START + timedelta(minutes=20)).isoformat(), "AAA", 103.0, 103.5, 102.0, 103.2, 1.0),
            ((START + timedelta(minutes=20)).isoformat(), "BBB", 199.0, 199.5, 197.0, 197.5, 1.0),
        ],
    )

    result = datasets.resample(source, tmp_path / "hour.csv", "1H")

    assert result["rows"] == 2
    assert result["first"] is not None and result["last"] is not None
    with (tmp_path / "hour.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    aaa = [row for row in rows if row["symbol"] == "AAA"]
    assert aaa[0]["o"] == "100.0"
    assert aaa[0]["h"] == "104.0"
    assert aaa[0]["l"] == "99.0"
    assert aaa[0]["c"] == "103.2"
    assert aaa[0]["v"] == "4.0"


def test_resample_sin_filas_devuelve_rango_vacio(tmp_path):
    source = _write_source(tmp_path / "empty.csv", [])

    result = datasets.resample(source, tmp_path / "out.csv", "1D")

    assert result["rows"] == 0
    assert result["first"] is None and result["last"] is None


# --- directorio y escritura -------------------------------------------------


def test_el_directorio_sale_del_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EZUR_DATA_DIR", str(tmp_path))

    assert datasets.data_dir() == tmp_path


def test_sin_entorno_usa_la_carpeta_data(monkeypatch):
    monkeypatch.delenv("EZUR_DATA_DIR", raising=False)
    monkeypatch.delenv("TERMINAL_DATA_DIR", raising=False)

    assert datasets.data_dir().name in {"data", "."}


def test_listar_datasets_solo_devuelve_csv(tmp_path):
    (tmp_path / "b.csv").write_text("x", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("x", encoding="utf-8")

    assert [Path(item).name for item in datasets.list_datasets(tmp_path)] == ["a.csv", "b.csv"]
    assert datasets.list_datasets(tmp_path / "no_existe") == []


def test_write_dataset_alinea_los_simbolos_y_escribe_la_cabecera(tmp_path):
    series = {
        "AAA": [_bar(0), _bar(1), _bar(2)],
        "BBB": [_bar(0), _bar(2)],
    }

    path = datasets.write_dataset(tmp_path / "sub" / "bars.csv", series)

    rows = path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == ",".join(datasets.HEADER)
    # El minuto 1 solo existe en AAA: no se escribe a medias.
    assert len(rows) == 1 + 4


# --- pull -------------------------------------------------------------------


class _FakeFeed:
    """Paginación de mentira con el mismo contrato que OKXFeed."""

    def __init__(self, symbols, bars=None, **kwargs):
        self.symbols = list(symbols)
        pages = [
            [_bar(2), _bar(3)],
            # El borde de OKX repite la última vela paginada.
            [_bar(3), _bar(4)],
            [],
        ]
        self.chunks = [{symbol: page for symbol in self.symbols} for page in pages]

    def fetch(self, limit, after=None):
        return self.chunks.pop(0) if self.chunks else {}


def test_pull_pagina_hasta_agotar_y_deduplica_el_borde(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "OKXFeed", _FakeFeed)
    settings = Settings()
    for item in settings.instruments.items:
        item.enabled = True

    path = datasets.pull(settings, bars=4, output=tmp_path / "pull.csv")

    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    assert len(rows) == 3 * len(settings.instruments.enabled)


def test_pull_exige_instrumentos_habilitados(tmp_path):
    settings = Settings()
    for item in settings.instruments.items:
        item.enabled = False

    with pytest.raises(ValueError, match="instrumentos habilitados"):
        datasets.pull(settings, output=tmp_path / "pull.csv")


def test_pull_usa_el_venue_symbol_cuando_existe(tmp_path, monkeypatch):
    seen: dict = {}

    class _Spy(_FakeFeed):
        def __init__(self, symbols, bars=None, **kwargs):
            seen.update(symbols)
            super().__init__(symbols, bars=bars)

    monkeypatch.setattr(datasets, "OKXFeed", _Spy)
    settings = Settings()
    for item in settings.instruments.items:
        item.enabled = True
        item.venue_symbol = "AAA-USDT"

    datasets.pull(settings, bars=2, output=tmp_path / "pull.csv")

    assert set(seen.values()) == {"AAA-USDT"}


# --- CLI --------------------------------------------------------------------


def test_el_cli_lista_los_csv(tmp_path, monkeypatch, capsys):
    (tmp_path / "uno.csv").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["datasets", "list", "--dir", str(tmp_path)])

    datasets.main()

    assert "uno.csv" in capsys.readouterr().out


def test_el_cli_agrega_un_fichero(tmp_path, monkeypatch, capsys):
    source = _write_source(
        tmp_path / "source.csv",
        [(START.isoformat(), "AAA", 100.0, 101.0, 99.0, 100.5, 2.0)],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["datasets", "resample", "--in", str(source), "--out", str(tmp_path / "out.csv")],
    )

    datasets.main()

    assert "1 filas" in capsys.readouterr().out


def test_el_cli_delega_la_descarga_de_binance_vision(tmp_path, monkeypatch, capsys):
    from server.market import binance_vision

    seen: dict = {}

    def fake_build(out, cache, months, **kwargs):
        seen.update({"out": out, "months": list(months)})
        return {"path": out, "rows": 1, "first": "a", "last": "b"}

    monkeypatch.setattr(binance_vision, "build", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "datasets",
            "vision",
            "--start",
            "2026-01",
            "--end",
            "2026-02",
            "--out",
            str(tmp_path / "v.csv"),
        ],
    )

    datasets.main()

    assert seen["months"] == ["2026-01", "2026-02"]
    assert "1 filas" in capsys.readouterr().out


def test_el_cli_descarga_del_venue(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(datasets, "OKXFeed", _FakeFeed)
    config = tmp_path / "config.json"
    config.write_text('{"feed": {"provider": "okx"}}', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "datasets",
            "pull",
            "--bars",
            "4",
            "--out",
            str(tmp_path / "pull.csv"),
            "--config",
            str(config),
        ],
    )

    datasets.main()

    out = capsys.readouterr().out
    assert "filas" in out
