"""Session calendar helpers: trading days, holidays and early closes.

Holidays are data, supplied by configuration. The module never assumes a
particular exchange calendar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from ..config import SessionTemplate
from ..models import SessionInfo


@dataclass
class Calendar:
    holidays: set[date] = field(default_factory=set)
    early_closes: dict[date, time] = field(default_factory=dict)

    def is_trading_day(self, day: date, template: SessionTemplate) -> bool:
        if day.weekday() not in template.weekdays:
            return False
        return day not in self.holidays

    def close_time(self, day: date, template: SessionTemplate) -> time:
        return self.early_closes.get(day, template.close_time)

    def session(self, clock: datetime, template: SessionTemplate) -> SessionInfo:
        local = clock.astimezone(__import__("zoneinfo").ZoneInfo(template.timezone))
        day = local.date()
        if not self.is_trading_day(day, template):
            return SessionInfo(
                id=f"{day.isoformat()}:{template.name}",
                label=template.name,
                is_open=False,
                phase="closed",
            )
        open_ts = local.replace(
            hour=template.open_time.hour, minute=template.open_time.minute, second=0, microsecond=0
        )
        close_at = self.close_time(day, template)
        close_ts = local.replace(hour=close_at.hour, minute=close_at.minute, second=0, microsecond=0)
        is_open = open_ts <= local < close_ts
        if local < open_ts:
            phase = "pre"
        elif is_open:
            phase = "open"
        elif local < close_ts + timedelta(hours=1):
            phase = "close"
        else:
            phase = "closed"
        return SessionInfo(
            id=f"{day.isoformat()}:{template.name}",
            label=template.name,
            is_open=is_open,
            open_ts=open_ts,
            close_ts=close_ts,
            phase=phase,  # type: ignore[arg-type]
        )
