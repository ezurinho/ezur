"""Constructor verificable del dataset histórico de Binance Vision.

El conversor de ``binance_vision`` resuelve el formato; este módulo añade lo
que hace falta para que el resultado sea evidencia: revalida la caché contra el
``.CHECKSUM`` publicado, exige que no falte ningún mes, valida monotonicidad y
OHLC, remuestrea y deja un manifiesto con URLs, hashes y cobertura.

No toca el motor ni el feed vivo. ``data.provider=simulated`` sigue siendo el
camino completo por defecto.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import DataConfig, Settings, load_settings
from ..datasets import resample
from . import binance_vision as bv

HEADER = bv.HEADER
_CHECKSUM_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_CONTRACT_RE = re.compile(r"^[A-Z0-9]+_(\d{2})(\d{2})(\d{2})$")


def last_closed_month(now: datetime | None = None) -> str:
    """Último mes completo en UTC; nunca se pide el mes en curso."""
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    first_of_month = stamp.date().replace(day=1)
    previous = first_of_month - timedelta(days=1)
    return f"{previous.year:04d}-{previous.month:02d}"


def market_path(market: str) -> str:
    """Ruta de mercado en Vision para el contrato del bot."""
    if market == "spot":
        return "spot"
    if market in {"um", "quarterly"}:
        return "futures/um"
    raise ValueError(f"mercado no soportado: {market!r}")


def default_output(data: DataConfig) -> Path:
    stem = f"{data.normalized_symbol}.{data.market}.{data.interval}"
    return Path("data") / f"{stem}.csv"


def contract_expiry(symbol: str) -> datetime:
    """Vencimiento del trimestral: último viernes del mes, 08:00 UTC."""
    match = _CONTRACT_RE.fullmatch(symbol)
    if match is None:
        raise ValueError(f"contrato trimestral inválido: {symbol!r}")
    year = 2000 + int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    try:
        expiry = datetime(year, month, day, 8, tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"fecha de vencimiento inválida: {symbol!r}") from error
    if expiry.weekday() != 4 or (expiry + timedelta(days=7)).month == expiry.month:
        raise ValueError(f"{symbol} no vence el último viernes de su mes")
    return expiry


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_bytes(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": bv.USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as error:
        raise ValueError(f"no se pudo descargar {url}: {error}") from error


def _read_checksum(url: str, timeout: float) -> str:
    """Lee el ``.CHECKSUM`` publicado; su ausencia es un fallo, no un aviso."""
    try:
        payload = _fetch_bytes(url, timeout).decode("utf-8", "replace")
    except ValueError as error:
        raise ValueError(f"{url}: no se pudo leer .CHECKSUM: {error}") from error
    for line in payload.splitlines():
        parts = line.split()
        if parts and _CHECKSUM_RE.fullmatch(parts[0]):
            return parts[0].lower()
    raise ValueError(f"{url}: .CHECKSUM vacío o mal formado")


def _cache_dir(cache: Path, data: DataConfig) -> Path:
    # El spot conserva la disposición plana que ya usaba el conversor; los
    # futuros necesitan un subdirectorio para no colisionar con BTCUSDT spot.
    if data.market == "spot":
        return cache
    return cache / data.market / data.symbol


def _download_month(
    month: str,
    cache: Path,
    data: DataConfig,
    *,
    timeout: float = 60.0,
) -> tuple[Path, str, str]:
    """Devuelve ``(zip, sha256 esperado, estado)`` y revalida siempre la caché."""
    url = bv.url_for(
        month,
        symbol=data.symbol,
        interval=data.interval,
        market=market_path(data.market),
    )
    expected = _read_checksum(url + ".CHECKSUM", timeout)
    target = _cache_dir(cache, data) / Path(url).name
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_file() and target.stat().st_size > 0:
        if _sha256(target) == expected:
            return target, expected, "cached"
        target.unlink()

    payload = _fetch_bytes(url, timeout)
    if not payload:
        raise ValueError(f"{month}: Binance devolvió un ZIP vacío")
    target.write_bytes(payload)
    actual = _sha256(target)
    if actual != expected:
        target.unlink(missing_ok=True)
        raise ValueError(
            f"{month}: sha256 {actual} no coincide con el .CHECKSUM {expected}"
        )
    target.with_suffix(target.suffix + ".CHECKSUM").write_text(
        f"{expected}  {target.name}\n", encoding="utf-8"
    )
    return target, expected, "downloaded"


def _iter_rows(path: Path, data: DataConfig) -> Iterator[tuple[str, str, str, str, str, str]]:
    rows = bv.rows(path)
    if data.market != "quarterly":
        yield from rows
        return

    # Los ZIP trimestrales siguen publicando barras planas con volumen 0
    # después del vencimiento. Se corta en la última barra realmente negociada;
    # no se inventa un final distinto ni se usa el final del ZIP como contrato.
    collected = list(rows)
    last_traded: int | None = None
    for index, row in enumerate(collected):
        if float(row[5]) > 0:
            last_traded = index
    if last_traded is None:
        raise ValueError(f"{path.name}: el contrato no tiene barras con volumen")
    yield from collected[: last_traded + 1]


def _validate_row(stamp: str, open_: str, high: str, low: str, close: str, volume: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(stamp)
        o, h, low_value, c, v = map(float, (open_, high, low, close, volume))
    except ValueError as error:
        raise ValueError(f"fila mal formada en {stamp!r}: {error}") from error
    if h < low_value or not (low_value <= o <= h and low_value <= c <= h):
        raise ValueError(f"OHLC inválido en {stamp}: {open_},{high},{low},{close}")
    if v < 0:
        raise ValueError(f"volumen negativo en {stamp}: {volume}")
    return parsed


def _csv_stamp(stamp: str) -> str:
    """UTC compacto y ordenable: ``2020-01-01T00:00Z``.

    La base es de minutos, así que los segundos siempre son ``:00``. Quitarlos
    ahorra 3 bytes por fila sin cambiar el instante ni la zona.
    """
    compact = stamp.replace("+00:00", "Z")
    if compact.endswith(":00Z"):
        compact = compact[:-4] + "Z"
    return compact


def _compact_number(value: str) -> str:
    """Quita ceros decimales sin redondear ni cambiar el valor de Binance."""
    text = value.strip()
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _manifest_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def build(
    data: DataConfig,
    out: Path | str | None = None,
    *,
    cache: Path | str = "data/vision",
    end: str | None = None,
    manifest_path: Path | str | None = None,
    resample_rule: str | None = "1D",
    timeout: float = 60.0,
    now: datetime | None = None,
    report: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Construye el CSV del bot y su manifiesto desde los ZIP mensuales."""
    if data.provider != "vision":
        raise ValueError("data.provider debe ser 'vision' para construir el histórico")

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    target = Path(out) if out is not None else default_output(data)
    manifest_target = Path(manifest_path) if manifest_path is not None else Path(data.manifest)
    cache_dir = Path(cache)

    end_month = end or data.history_end or last_closed_month(stamp)
    expiry: datetime | None = None
    if data.market == "quarterly":
        expiry = contract_expiry(data.symbol)
        expiry_month = f"{expiry.year:04d}-{expiry.month:02d}"
        if end_month > expiry_month:
            end_month = expiry_month
    month_list = bv.months(data.history_start, end_month)
    if not month_list:
        raise ValueError("el rango no contiene ningún mes")

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    daily_target = (
        target.with_name(f"{target.stem}.{resample_rule}.csv") if resample_rule else None
    )
    daily_tmp = (
        daily_target.with_name(daily_target.name + ".tmp") if daily_target is not None else None
    )

    total = 0
    downloaded = 0
    first: str | None = None
    last: str | None = None
    previous: datetime | None = None
    dates: set[str] = set()
    gap_count = 0
    missing_bars = 0
    max_gap_minutes = 0
    month_entries: list[dict[str, Any]] = []
    checksums: dict[str, str] = {}

    try:
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            for month in month_list:
                try:
                    path, digest, state = _download_month(
                        month, cache_dir, data, timeout=timeout
                    )
                except Exception as error:  # noqa: BLE001 - el mes que falla debe salir en el mensaje
                    raise ValueError(f"{month}: no se pudo preparar el mes: {error}") from error
                downloaded += int(state == "downloaded")
                count = 0
                for ts, o, h, low, c, v in _iter_rows(path, data):
                    parsed = _validate_row(ts, o, h, low, c, v)
                    if previous is not None:
                        if parsed <= previous:
                            raise ValueError(f"{month}: timestamp duplicado o fuera de orden: {ts}")
                        delta = int((parsed - previous).total_seconds() // 60)
                        if delta > 1:
                            gap_count += 1
                            missing_bars += delta - 1
                            max_gap_minutes = max(max_gap_minutes, delta)
                            if delta > 1440:
                                raise ValueError(f"{month}: hueco de más de un día en {ts}")
                    csv_ts = _csv_stamp(ts)
                    writer.writerow(
                        [
                            csv_ts,
                            data.normalized_symbol,
                            _compact_number(o),
                            _compact_number(h),
                            _compact_number(low),
                            _compact_number(c),
                            _compact_number(v),
                        ]
                    )
                    count += 1
                    total += 1
                    first = first or csv_ts
                    last = csv_ts
                    previous = parsed
                    dates.add(csv_ts[:10])
                if count == 0:
                    raise ValueError(f"{month}: el mes no contiene barras")
                checksums[path.name] = digest
                month_entries.append(
                    {
                        "month": month,
                        "rows": count,
                        "file": path.name,
                        "url": bv.url_for(
                            month,
                            symbol=data.symbol,
                            interval=data.interval,
                            market=market_path(data.market),
                        ),
                        "sha256": digest,
                    }
                )
                if report is not None:
                    report(month, count, total, state)

        if total == 0:
            raise ValueError("el dataset no contiene barras")
        dataset_id = _sha256(tmp)

        derived: dict[str, Any] | None = None
        if daily_tmp is not None and daily_target is not None and resample_rule is not None:
            # Se remuestrea el temporal: un fallo deja intacto el dataset anterior.
            result = resample(tmp, daily_tmp, resample_rule)
            derived_id = _sha256(daily_tmp)
            os.replace(tmp, target)
            os.replace(daily_tmp, daily_target)
            derived = {
                "rule": resample_rule,
                "rows": result["rows"],
                "first": result["first"],
                "last": result["last"],
                "dataset_id": derived_id,
            }
        else:
            os.replace(tmp, target)

        first_date = first[:10] if first else None
        last_date = last[:10] if last else None
        expected_days = (
            (datetime.fromisoformat(last_date).date() - datetime.fromisoformat(first_date).date()).days + 1
            if first_date and last_date
            else 0
        )
        payload: dict[str, Any] = {
            "manifest_version": 1,
            "vendor": "binance_vision",
            "market": data.market,
            "symbol": data.symbol,
            "bot_symbol": data.normalized_symbol,
            "interval": data.interval,
            "dataset_id": dataset_id,
            "range": {
                "start": data.history_start,
                "end": end_month,
                "first": first,
                "last": last,
            },
            "rows": total,
            "days": len(dates),
            "expected_days": expected_days,
            "missing_days": expected_days - len(dates),
            "gaps": {
                "count": gap_count,
                "missing_bars": missing_bars,
                "max_gap_minutes": max_gap_minutes,
            },
            "months": month_entries,
            "checksums": checksums,
            "checksum_coverage": 1.0 if month_entries else 0.0,
            "rolls": [],
            "continuous": False,
            "funding": {
                "status": "not_included" if data.market != "spot" else "not_applicable"
            },
            "derived": derived,
            "built_at": stamp.isoformat(),
            "code_version": __version__,
        }
        if expiry is not None:
            payload["contract"] = {
                "expiry": expiry.isoformat(),
                "symbol": data.symbol,
                "continuous": False,
            }
        payload["manifest_sha256"] = _manifest_digest(payload)
        _write_manifest(manifest_target, payload)
    except Exception:
        tmp.unlink(missing_ok=True)
        if daily_tmp is not None:
            daily_tmp.unlink(missing_ok=True)
        raise

    return {
        "path": str(target),
        "manifest": str(manifest_target),
        "rows": total,
        "dataset_id": dataset_id,
        "manifest_sha256": payload["manifest_sha256"],
        "downloaded": downloaded,
        "months": month_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye el histórico verificable de Binance Vision")
    parser.add_argument("--config", default=None, help="config.json alternativo")
    parser.add_argument("--market", choices=["spot", "um", "quarterly"], default=None)
    parser.add_argument("--symbol", default=None, help="símbolo exacto del vendor")
    parser.add_argument("--start", default=None, help="primer mes YYYY-MM")
    parser.add_argument("--out", default=None, help="CSV de salida")
    parser.add_argument("--cache", default="data/vision")
    parser.add_argument("--end", default=None, help="último mes YYYY-MM (por defecto, el último cerrado)")
    parser.add_argument("--manifest", default=None, help="ruta del manifiesto")
    parser.add_argument("--no-resample", action="store_true", help="no escribir el CSV diario")
    args = parser.parse_args()

    settings: Settings = load_settings(args.config) if args.config else Settings()
    values = settings.data.model_dump()
    values.update({"provider": "vision"})
    for name in ("market", "symbol", "start"):
        if getattr(args, name) is not None:
            values["history_start" if name == "start" else name] = getattr(args, name)
    data = DataConfig(**values)

    def report(month: str, count: int, total: int, state: str) -> None:
        print(f"{month} · {count:>6} velas · {state} · total {total}", flush=True)

    result = build(
        data,
        args.out,
        cache=args.cache,
        end=args.end,
        manifest_path=args.manifest,
        resample_rule=None if args.no_resample else "1D",
        report=report,
    )
    print(
        f"{result['path']} · {result['rows']} filas · "
        f"dataset_id {result['dataset_id']} · manifiesto {result['manifest']}"
    )


if __name__ == "__main__":
    main()
