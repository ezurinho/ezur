"""Instrument specifications, expiries and rolls.

Everything here is generic: the quarterly cycle and the third-Friday rule are
properties of a contract family, not of any particular symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

QUARTER_MONTHS = (3, 6, 9, 12)


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (4 - first.weekday()) % 7  # 4 = Friday
    return first + timedelta(days=offset + 14)


@dataclass(frozen=True)
class Contract:
    symbol: str
    expiry: date


@dataclass(frozen=True)
class RollPlan:
    """Maps a date to the contract that is active on it."""

    root: str
    roll_days_before: int = 0

    def active(self, day: date) -> Contract:
        expiry_month = next(
            (month for month in QUARTER_MONTHS if (month, third_friday(day.year, month)) >= (day.month, day)),
            None,
        )
        if expiry_month is None:
            year, month = day.year + 1, QUARTER_MONTHS[0]
        else:
            year, month = day.year, expiry_month
        expiry = third_friday(year, month)
        if day > expiry - timedelta(days=self.roll_days_before):
            following = QUARTER_MONTHS.index(month) + 1
            if following == len(QUARTER_MONTHS):
                year, month = year + 1, QUARTER_MONTHS[0]
            else:
                month = QUARTER_MONTHS[following]
            expiry = third_friday(year, month)
        code = _month_code(month)
        return Contract(symbol=f"{self.root}{code}{year % 100:02d}", expiry=expiry)


MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}


def _month_code(month: int) -> str:
    return MONTH_CODES[month]
