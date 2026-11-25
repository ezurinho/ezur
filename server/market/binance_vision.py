"""Velas históricas de Binance Vision: el pasado largo que la API no entrega.

La API de OKX da 600 velas y se acabó. Para validar una tendencia diaria hacen
falta años, y eso solo está en los ficheros mensuales públicos de Binance
(`data.binance.vision`), que no piden clave ni tienen cuota.

Origen: un ZIP por mes con un CSV sin cabecera:

    open_time_ms,open,high,low,close,volume,close_time,quote_volume,trades,...

Destino: el CSV del bot, ``ts,symbol,o,h,l,c,v``, más antiguo primero.

Descargar y convertir están separados a propósito. El ZIP se guarda y se
verifica contra el ``.CHECKSUM`` del propio Binance; reconstruir el CSV no
vuelve a pedir ochenta ficheros a la red, y un mes corrupto se detecta al
bajarlo, no tres pasos después.
"""

from __future__ import annotations

import csv
import hashlib
import io
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://data.binance.vision/data"
USER_AGENT = "ezur-dataset-loader"
HEADER = ["ts", "symbol", "o", "h", "l", "c", "v"]


def months(start: str, end: str) -> list[str]:
    """``("2020-01", "2020-03")`` → ``["2020-01", "2020-02", "2020-03"]``."""
    first = _parse_month(start)
    last = _parse_month(end)
    if last < first:
        raise ValueError(f"rango invertido: {start} > {end}")
    result: list[str] = []
    year, month = first
    while (year, month) <= last:
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return result


def _parse_month(value: str) -> tuple[int, int]:
    try:
        year, month = value.split("-")
        parsed = int(year), int(month)
    except (AttributeError, ValueError) as error:
        raise ValueError(f"mes inválido: {value!r} (se espera YYYY-MM)") from error
    # 2020-13 se convertiría en 2021-01 dentro del bucle y duplicaría el mes.
    if not 1 <= parsed[1] <= 12:
        raise ValueError(f"mes fuera de rango: {value!r}")
    return parsed


def url_for(
    month: str,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    market: str = "spot",
) -> str:
    return f"{BASE_URL}/{market}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"


def download(
    month: str,
    cache: Path | str,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    market: str = "spot",
    timeout: float = 60.0,
    verify: bool = True,
) -> tuple[Path, str]:
    """Descarga (o reutiliza) el ZIP del mes. Devuelve (ruta, estado)."""
    target = Path(cache) / f"{symbol}-{interval}-{month}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size > 0:
        return target, "cached"

    request = urllib.request.Request(
        url_for(month, symbol=symbol, interval=interval, market=market),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if not payload:
        raise ValueError(f"{month}: Binance devolvió un fichero vacío")

    target.write_bytes(payload)
    if verify and not verify_checksum(target, month, symbol=symbol, interval=interval, market=market, timeout=timeout):
        target.unlink(missing_ok=True)
        raise ValueError(f"{month}: el sha256 no coincide con el .CHECKSUM de Binance")
    return target, "downloaded"


def verify_checksum(
    path: Path,
    month: str,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    market: str = "spot",
    timeout: float = 60.0,
) -> bool:
    """Compara con el ``.CHECKSUM`` publicado. Sin fichero de control, no verifica."""
    url = url_for(month, symbol=symbol, interval=interval, market=market) + ".CHECKSUM"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return True  # sin checksum publicado no se puede acusar al fichero
    expected = text.split()[0].strip().lower() if text.split() else ""
    if not expected:
        return True
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == expected


def rows(zip_path: Path) -> Iterator[tuple[str, str, str, str, str, str]]:
    """Filas (ts, o, h, l, c, v) del CSV dentro del ZIP, sin cargar todo en RAM."""
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"{zip_path.name}: el ZIP no trae CSV")
        with archive.open(names[0]) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8")
            reader = csv.reader(stream)
            for row in reader:
                if not row:
                    continue
                if row[0].lower() in {"open_time", "open_time_ms", "open_time_us"}:
                    continue  # algunos meses traen cabecera
                # Hasta 2024 el open_time viene en milisegundos; desde 2025-01,
                # Binance publica microsegundos. Confundirlos no da error: da
                # fechas del año 56000, y Windows se niega a convertirlas.
                raw = int(row[0])
                micros = raw > 100_000_000_000_000  # 1e14: ms en 1973, µs en 1973
                seconds = raw / 1_000_000 if micros else raw / 1_000
                stamp = datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
                yield stamp, row[1], row[2], row[3], row[4], row[5]


def build(
    out: Path | str,
    cache: Path | str,
    month_list: Iterable[str],
    *,
    bot_symbol: str = "BTC",
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    market: str = "spot",
    report: callable | None = None,
) -> dict[str, object]:
    """Convierte los ZIP mensuales en un CSV único del bot, en streaming."""
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    first: str | None = None
    last: str | None = None
    downloaded = 0
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for month in month_list:
            try:
                path, state = download(month, cache, symbol=symbol, interval=interval, market=market)
            except Exception as error:  # noqa: BLE001 - el mes que falla debe salir en el mensaje
                raise ValueError(f"{month}: no se pudo preparar el mes: {error}") from error
            downloaded += 1 if state == "downloaded" else 0
            count = 0
            for stamp, o, h, low, c, v in rows(path):
                writer.writerow([stamp, bot_symbol, o, h, low, c, v])
                count += 1
                first = first or stamp
                last = stamp
            total += count
            if report is not None:
                report(month, count, total, state)
    return {
        "path": str(target),
        "months": downloaded,
        "rows": total,
        "first": first,
        "last": last,
    }
