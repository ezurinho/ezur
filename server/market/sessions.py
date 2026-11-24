"""Session calendar helpers: trading days, holidays and early closes.

Holidays are data, supplied by configuration. The module never assumes a
particular exchange calendar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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
        """La misma ventana que usa el motor, con festivos y cierres tempranos.

        Las sesiones que cruzan la medianoche se anclan al día en que abrieron:
        a las 02:00 sigue siendo la sesión de ayer. Sin esto nunca constaban
        abiertas y el cambio de día partía la sesión en dos a las 00:00.
        """
        local = clock.astimezone(ZoneInfo(template.timezone))
        day = local.date()
        open_h, open_m = template.open_time.hour, template.open_time.minute
        close_h, close_m = template.close_time.hour, template.close_time.minute
        overnight = (close_h, close_m) <= (open_h, open_m)
        open_ts = local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        close_ts = local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
        session_day = day
        if overnight:
            if local < open_ts:
                open_ts -= timedelta(days=1)
                session_day = day - timedelta(days=1)
            else:
                close_ts += timedelta(days=1)

        if not self.is_trading_day(session_day, template):
            return SessionInfo(
                id=f"{session_day.isoformat()}:{template.name}",
                label=template.name,
                is_open=False,
                phase="closed",
            )

        close_at = self.close_time(session_day, template)
        close_ts = close_ts.replace(
            hour=close_at.hour, minute=close_at.minute, second=0, microsecond=0
        )
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
            id=f"{session_day.isoformat()}:{template.name}",
            label=template.name,
            is_open=is_open,
            open_ts=open_ts,
            close_ts=close_ts,
            phase=phase,  # type: ignore[arg-type]
        )
