"""Constructor histórico: checksum estricto, CSV, manifiesto y trimestrales."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.config import DataConfig
from server.market import vision_builder as vb


def _ms(stamp: str) -> int:
    return int(datetime.fromisoformat(stamp).timestamp() * 1000)


def _zip(path: Path, rows: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "BTCUSDT-1m-2020-01.csv",
            "open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_base,taker_quote,ignore\n"
            + "\n".join(rows)
            + "\n",
        )
    return path


def _fake_downloader(zips: dict[str, Path], digest: str = "a" * 64):
    def fake(month, cache, data, *, timeout=60.0):
        return zips[month], digest, "cached"

    return fake


def _config(tmp_path: Path, **overrides) -> DataConfig:
    values = {
        "provider": "vision",
        "market": "spot",
        "symbol": "BTCUSDT",
        "history_start": "2020-01",
        "history_end": "2020-01",
        "manifest": str(tmp_path / "manifest.json"),
    }
    values.update(overrides)
    return DataConfig(**values)


def test_el_constructor_escribe_csv_manifiesto_y_diario(tmp_path, monkeypatch):
    source = _zip(
        tmp_path / "2020-01.zip",
        [
            f"{_ms('2020-01-01T00:00:00+00:00')},100,101,99,100.5,1,0,0,0,0,0,0",
            f"{_ms('2020-01-01T00:01:00+00:00')},100.5,102,100,101,2,0,0,0,0,0,0",
        ],
    )
    monkeypatch.setattr(vb, "_download_month", _fake_downloader({"2020-01": source}))
    out = tmp_path / "bars.csv"

    result = vb.build(
        _config(tmp_path),
        out,
        now=datetime(2026, 11, 28, tzinfo=timezone.utc),
    )

    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["ts"] for row in rows] == [
        "2020-01-01T00:00Z",
        "2020-01-01T00:01Z",
    ]
    assert rows[0]["symbol"] == "BTC-USDT"
    assert rows[1]["c"] == "101"

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["vendor"] == "binance_vision"
    assert manifest["market"] == "spot"
    assert manifest["symbol"] == "BTCUSDT"
    assert manifest["bot_symbol"] == "BTC-USDT"
    assert manifest["rows"] == 2
    assert manifest["days"] == 1
    assert manifest["dataset_id"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert manifest["checksums"] == {"2020-01.zip": "a" * 64}
    assert manifest["months"][0]["url"].endswith("BTCUSDT-1m-2020-01.zip")
    assert manifest["gaps"] == {"count": 0, "missing_bars": 0, "max_gap_minutes": 0}
    assert manifest["rolls"] == []
    assert manifest["continuous"] is False
    assert manifest["derived"]["rule"] == "1D"
    assert manifest["derived"]["rows"] == 1

    body = dict(manifest)
    digest = body.pop("manifest_sha256")
    assert vb._manifest_digest(body) == digest


def test_el_mismo_dataset_produce_el_mismo_hash(tmp_path, monkeypatch):
    source = _zip(
        tmp_path / "2020-01.zip",
        [f"{_ms('2020-01-01T00:00:00+00:00')},100,101,99,100.5,1,0,0,0,0,0,0"],
    )
    monkeypatch.setattr(vb, "_download_month", _fake_downloader({"2020-01": source}))
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    data = _config(tmp_path)

    first = vb.build(data, tmp_path / "uno.csv", now=now)
    second = vb.build(data, tmp_path / "dos.csv", now=now)

    assert (tmp_path / "uno.csv").read_bytes() == (tmp_path / "dos.csv").read_bytes()
    assert first["dataset_id"] == second["dataset_id"]
    assert first["manifest_sha256"] == second["manifest_sha256"]


def test_la_cache_se_revalida_y_se_reescribe_si_el_hash_no_cuadra(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    target = cache / "BTCUSDT-1m-2020-01.zip"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"viejo")
    payload = b"zip-nuevo"
    expected = hashlib.sha256(payload).hexdigest()

    def fake_fetch(url, timeout):
        if url.endswith(".CHECKSUM"):
            return f"{expected}  BTCUSDT-1m-2020-01.zip\n".encode()
        return payload

    monkeypatch.setattr(vb, "_fetch_bytes", fake_fetch)

    path, digest, state = vb._download_month("2020-01", cache, _config(tmp_path))

    assert path == target
    assert path.read_bytes() == payload
    assert digest == expected
    assert state == "downloaded"
    assert target.with_suffix(".zip.CHECKSUM").exists()


def test_sin_checksum_no_se_acepta_el_fichero(tmp_path, monkeypatch):
    def fake_fetch(url, timeout):
        raise ValueError("404")

    monkeypatch.setattr(vb, "_fetch_bytes", fake_fetch)

    with pytest.raises(ValueError, match="CHECKSUM"):
        vb._download_month("2020-01", tmp_path, _config(tmp_path))


def test_trimestral_corta_las_barras_planas_posteriores_al_vencimiento(tmp_path, monkeypatch):
    source = _zip(
        tmp_path / "2024-03.zip",
        [
            f"{_ms('2024-03-29T08:00:00+00:00')},100,101,99,100.5,1,0,0,0,0,0,0",
            f"{_ms('2024-03-29T08:01:00+00:00')},100.5,100.5,100.5,100.5,0,0,0,0,0,0,0",
            f"{_ms('2024-03-29T08:02:00+00:00')},100.5,100.5,100.5,100.5,0,0,0,0,0,0,0",
        ],
    )
    monkeypatch.setattr(vb, "_download_month", _fake_downloader({"2024-03": source}))
    data = _config(
        tmp_path,
        market="quarterly",
        symbol="BTCUSDT_240329",
        history_start="2024-03",
        history_end="2024-03",
    )

    result = vb.build(data, tmp_path / "q.csv", now=datetime(2026, 11, 28, tzinfo=timezone.utc))

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["rows"] == 1
    assert manifest["range"]["last"] == "2024-03-29T08:00Z"
    assert manifest["contract"]["expiry"] == "2024-03-29T08:00:00+00:00"
    assert manifest["continuous"] is False


def test_rechaza_un_timestamp_duplicado(tmp_path, monkeypatch):
    stamp = _ms("2020-01-01T00:00:00+00:00")
    source = _zip(
        tmp_path / "2020-01.zip",
        [
            f"{stamp},100,101,99,100.5,1,0,0,0,0,0,0",
            f"{stamp},100,101,99,100.5,1,0,0,0,0,0,0",
        ],
    )
    monkeypatch.setattr(vb, "_download_month", _fake_downloader({"2020-01": source}))

    with pytest.raises(ValueError, match="duplicado o fuera de orden"):
        vb.build(_config(tmp_path), tmp_path / "bad.csv")
    assert not (tmp_path / "bad.csv").exists()


def test_simulated_no_construye_historico(tmp_path):
    with pytest.raises(ValueError, match="vision"):
        vb.build(DataConfig(), tmp_path / "x.csv")


def test_ultimo_mes_cerrado_y_vencimiento():
    assert vb.last_closed_month(datetime(2026, 11, 28, tzinfo=timezone.utc)) == "2026-10"
    assert vb.last_closed_month(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "2025-12"
    assert vb.contract_expiry("BTCUSDT_240329").isoformat() == "2024-03-29T08:00:00+00:00"
    with pytest.raises(ValueError, match="último viernes"):
        vb.contract_expiry("BTCUSDT_240328")
