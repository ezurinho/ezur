"""Comprueba si Binance Vision conserva el funding de perpetuos deslistados.

La pregunta que responde: antes de pre-registrar H10 (carry cross-sectional en
el tramo largo) hay que saber si el panel gratuito incluye los símbolos que
Binance ya retiró. Sin ellos, el universo queda sesgado a los supervivientes y
el tramo largo parece rentable por construcción.

Método, sin descargar el universo entero:

1. Censo: se enumeran los símbolos con ``fundingRate`` mensual en Vision y se
   comprueba, uno a uno, si existe el fichero de 2026-10. Un símbolo sin ese
   fichero no cotiza hoy: está deslistado (o nunca llegó a octubre de 2026).
2. Para cada deslistado se enumeran sus meses: primero, último y cuántos.
3. Se descargan los últimos ZIP de una muestra, se verifica el ``.CHECKSUM`` y
   se cuentan filas y timestamps. Un fichero presente pero vacío no sirve.

Uso:
    python scripts/check_h10_funding_coverage.py
    python scripts/check_h10_funding_coverage.py --sample 8 --json data/h10_coverage.json

No mide ninguna estrategia: sólo comprueba disponibilidad de datos.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
USER_AGENT = "ezur-lab-coverage/1.0"
REFERENCE_MONTH = "2026-10"
RETRIES = 4


def _get(url: str, timeout: float = 45.0) -> bytes:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def list_prefix(prefix: str) -> list[str]:
    """Todas las claves bajo un prefijo, paginando con ``marker``."""
    keys: list[str] = []
    marker = ""
    while True:
        query = {"prefix": prefix, "max-keys": "1000"}
        if marker:
            query["marker"] = marker
        url = f"{BASE}?{urllib.parse.urlencode(query)}"
        xml = _get(url).decode("utf-8", "replace")
        keys.extend(re.findall(r"<Key>(.*?)</Key>", xml))
        nxt = re.search(r"<NextMarker>(.*?)</NextMarker>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml:
            return keys
        marker = nxt.group(1) if nxt else (keys[-1] if keys else "")
        if not marker:
            return keys


def list_symbols(kind: str) -> list[str]:
    """Símbolos con datos de ``kind`` (``fundingRate`` o ``klines``)."""
    found: list[str] = []
    marker = ""
    prefix = f"data/futures/um/monthly/{kind}/"
    while True:
        query = {"prefix": prefix, "delimiter": "/", "max-keys": "1000"}
        if marker:
            query["marker"] = marker
        xml = _get(f"{BASE}?{urllib.parse.urlencode(query)}").decode("utf-8", "replace")
        found.extend(re.findall(r"<Prefix>(.*?)</Prefix>", xml))
        nxt = re.search(r"<NextMarker>(.*?)</NextMarker>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml:
            break
        marker = nxt.group(1) if nxt else (found[-1] if found else "")
        if not marker:
            break
    return sorted({item.rstrip("/").split("/")[-1] for item in found})


def _months_of(keys: list[str], symbol: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(symbol)}-fundingRate-(\d{{4}}-\d{{2}})\.zip$")
    months = []
    for key in keys:
        match = pattern.search(key)
        if match:
            months.append(match.group(1))
    return sorted(set(months))


def inspect(symbol: str) -> dict:
    keys = list_prefix(f"data/futures/um/monthly/fundingRate/{symbol}/")
    months = _months_of(keys, symbol)
    kline_keys = list_prefix(f"data/futures/um/monthly/klines/{symbol}/1d/")
    return {
        "symbol": symbol,
        "funding_months": len(months),
        "first_month": months[0] if months else None,
        "last_month": months[-1] if months else None,
        "kline_months": sum(1 for key in kline_keys if key.endswith(".zip")),
        "active": REFERENCE_MONTH in months,
    }


def verify_zip(symbol: str, month: str) -> dict:
    """Descarga el ZIP del mes, verifica el checksum y cuenta filas reales."""
    name = f"{symbol}-fundingRate-{month}.zip"
    url = f"data/futures/um/monthly/fundingRate/{symbol}/{name}"
    payload = _get(f"{BASE}/{url}")
    digest = hashlib.sha256(payload).hexdigest()
    expected = ""
    try:
        text = _get(f"{BASE}/{url}.CHECKSUM").decode("utf-8", "replace")
        expected = text.split()[0].strip().lower() if text.split() else ""
    except RuntimeError:
        expected = ""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        rows = 0
        first_ts = last_ts = None
        if names:
            with archive.open(names[0]) as raw:
                for line in io.TextIOWrapper(raw, encoding="utf-8"):
                    line = line.strip()
                    if not line or line.lower().startswith("calc_time"):
                        continue
                    stamp = line.split(",")[0]
                    rows += 1
                    first_ts = first_ts or stamp
                    last_ts = stamp
    return {
        "symbol": symbol,
        "month": month,
        "rows": rows,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "checksum_ok": bool(expected) and digest == expected,
        "checksum_published": bool(expected),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cobertura de funding para deslistados")
    parser.add_argument("--sample", type=int, default=6, help="ZIP a verificar por contenido")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    print("Enumerando símbolos con fundingRate mensual…", flush=True)
    symbols = list_symbols("fundingRate")
    print(f"{len(symbols)} símbolos con fundingRate mensual", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(inspect, symbols))

    active = [r for r in rows if r["active"]]
    delisted = [r for r in rows if not r["active"]]
    usable = [r for r in delisted if r["funding_months"] >= 12]
    deep = [r for r in delisted if r["funding_months"] >= 24]

    print(f"Con fichero en {REFERENCE_MONTH}: {len(active)}")
    print(f"Sin fichero en {REFERENCE_MONTH} (deslistados o anteriores): {len(delisted)}")
    print(f"  de ellos con >= 12 meses de funding: {len(usable)}")
    print(f"  de ellos con >= 24 meses de funding: {len(deep)}")

    ranked = sorted(delisted, key=lambda r: r["funding_months"], reverse=True)
    print("\nMuestra de deslistados con más historia:")
    print(f"{'símbolo':<18}{'meses':>6}  {'primero':<9} {'último':<9} velas 1d")
    for row in ranked[:15]:
        print(
            f"{row['symbol']:<18}{row['funding_months']:>6}  "
            f"{row['first_month'] or '-':<9} {row['last_month'] or '-':<9} "
            f"{row['kline_months']}"
        )

    to_verify = [r for r in ranked if r["last_month"]][: args.sample]
    checks = [verify_zip(r["symbol"], r["last_month"]) for r in to_verify]
    print("\nVerificación de contenido del último mes de cada uno:")
    for check in checks:
        ok = "ok" if check["checksum_ok"] else ("sin checksum" if not check["checksum_published"] else "FALLA")
        print(
            f"{check['symbol']:<18}{check['month']}  filas={check['rows']:<5} "
            f"{check['first_ts']} -> {check['last_ts']}  checksum={ok}"
        )

    payload = {
        "source": "data.binance.vision futures/um monthly fundingRate",
        "reference_month": REFERENCE_MONTH,
        "generated_at": datetime.now(UTC).isoformat(),
        "symbols_total": len(symbols),
        "active": len(active),
        "delisted": len(delisted),
        "delisted_ge_12m": len(usable),
        "delisted_ge_24m": len(deep),
        "sample": ranked[:40],
        "checked": checks,
    }
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nEscrito {target}")

    if not usable:
        print("\nVEREDICTO: no hay deslistados reconstruibles. H10 no se puede medir.")
        return 1
    print(f"\nVEREDICTO: {len(usable)} deslistados con >= 12 meses de funding en Vision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
