"""Timezone and session helpers. No instrument knowledge."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import SessionTemplate
from .models import SessionInfo


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_zone(clock: datetime, timezone_name: str) -> datetime:
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.astimezone(ZoneInfo(timezone_name))


def parse_hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")
    return int(hours), int(minutes)


def session_open_utc(template: SessionTemplate, day: date) -> datetime:
    """UTC instant of the session open for ``day`` in the template timezone."""
    local_open = datetime.combine(
        day, template.open_time, tzinfo=ZoneInfo(template.timezone)
    )
    return local_open.astimezone(timezone.utc)


def session_for(clock: datetime, template: SessionTemplate) -> SessionInfo:
    """Return the session window that contains (or precedes) ``clock``.

    Las sesiones que cruzan la medianoche (apertura 22:00, cierre 06:00) se
    anclan al día en que abrieron: a las 02:00 sigue siendo la sesión de ayer,
    y solo cambia cuando abre la siguiente. Sin esto nunca constaban abiertas
    y el cambio de día partía la sesión en dos a las 00:00.
    """
    local = to_zone(clock, template.timezone)
    open_h, open_m = parse_hhmm(template.open)
    close_h, close_m = parse_hhmm(template.close)
    overnight = (close_h, close_m) <= (open_h, open_m)
    day = local.date()
    open_ts = local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    close_ts = local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

    session_day = day
    if overnight:
        if local < open_ts:
            # La sesión anterior abrió ayer y cierra esta madrugada.
            open_ts -= timedelta(days=1)
            session_day = day - timedelta(days=1)
        else:
            close_ts += timedelta(days=1)

    trading_day = session_day.weekday() in template.weekdays
    is_open = trading_day and open_ts <= local < close_ts
    if not trading_day:
        phase = "closed"
    elif local < open_ts:
        phase = "pre"
    elif local < close_ts:
        phase = "open"
    elif local < (close_ts + timedelta(hours=1) if overnight else close_ts.replace(hour=min(23, close_h + 1))):
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


def same_session(a: SessionInfo | None, b: SessionInfo | None) -> bool:
    if a is None or b is None:
        return False
    return a.id == b.id
