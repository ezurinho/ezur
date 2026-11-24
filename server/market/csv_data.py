"""Dataset validation.

Checks the properties a backtest depends on, and reports them as machine
readable codes. No instrument names: the expected symbols come as a list.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ValidationIssue:
    code: str
    message: str
    row: int | None = None


@dataclass
class ValidationReport:
    ok: bool
    symbols: list[str] = field(default_factory=list)
    rows: int = 0
    sessions: int = 0
    errors: list[ValidationIssue] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "symbols": self.symbols,
            "rows": self.rows,
            "sessions": self.sessions,
            "errors": [
                {"code": issue.code, "message": issue.message, "row": issue.row}
                for issue in self.errors
            ],
        }


def _parse_ts(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def validate_dataset(
    path: str | Path, instruments: list[str]
) -> ValidationReport:
    target = Path(path)
    errors: list[ValidationIssue] = []
    if not target.exists():
        return ValidationReport(ok=False, errors=[ValidationIssue("missing_file", str(target))])

    stamps: dict[str, list[datetime]] = {symbol: [] for symbol in instruments}
    seen_unknown: set[str] = set()
    rows = 0

    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"ts", "symbol", "o", "h", "l", "c"} - set(reader.fieldnames or [])
        if missing:
            return ValidationReport(
                ok=False,
                errors=[
                    ValidationIssue("missing_columns", f"columnas ausentes: {sorted(missing)}")
                ],
            )
        for index, row in enumerate(reader, start=2):
            rows += 1
            symbol = row["symbol"]
            if symbol not in instruments:
                if symbol not in seen_unknown:
                    seen_unknown.add(symbol)
                    errors.append(
                        ValidationIssue("unknown_symbol", f"símbolo no configurado: {symbol}", index)
                    )
                continue
            try:
                stamp = _parse_ts(row["ts"])
            except ValueError:
                errors.append(ValidationIssue("bad_timestamp", row["ts"], index))
                continue
            try:
                open_ = float(row["o"])
                high = float(row["h"])
                low = float(row["l"])
                close = float(row["c"])
            except (TypeError, ValueError):
                errors.append(ValidationIssue("invalid_bar", "valores no numéricos", index))
                continue
            if not all(
                math.isfinite(value) for value in (open_, high, low, close)
            ) or low <= 0:
                # `nan`/`inf` pasan cualquier comparación (nan < low es falso) y
                # un precio no positivo rompe los indicadores que dividen.
                errors.append(
                    ValidationIssue("invalid_bar", "precio no finito o no positivo", index)
                )
                continue
            if high < low:
                errors.append(ValidationIssue("invalid_bar", "high < low", index))
            stamps[symbol].append(stamp)

    for symbol in instruments:
        values = stamps[symbol]
        if not values:
            errors.append(ValidationIssue("empty_symbol", f"sin datos para {symbol}"))
            continue
        if values != sorted(values):
            errors.append(ValidationIssue("unsorted", f"{symbol} no está ordenado"))
        if len(values) != len(set(values)):
            errors.append(ValidationIssue("duplicate_ts", f"{symbol} tiene timestamps duplicados"))

    sets = [set(values) for values in stamps.values() if values]
    if len(sets) > 1:
        common = set.intersection(*sets)
        union = set.union(*sets)
        if common != union:
            errors.append(
                ValidationIssue(
                    "misaligned",
                    f"timestamps desalineados entre series ({len(union - common)} marcas)",
                )
            )

    sessions = len({stamp.date() for values in stamps.values() for stamp in values})
    return ValidationReport(
        ok=not errors,
        symbols=[symbol for symbol in instruments if stamps[symbol]],
        rows=rows,
        sessions=sessions,
        errors=errors,
    )
