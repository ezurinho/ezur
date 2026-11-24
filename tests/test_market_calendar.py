from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from server.config import SessionTemplate
from server.market.instruments import RollPlan, third_friday
from server.market.sessions import Calendar
from server.timeutil import session_for


def test_third_friday_is_always_a_friday():
    for month in (3, 6, 9, 12):
        day = third_friday(2026, month)
        assert day.weekday() == 4
        assert 15 <= day.day <= 21


def test_roll_plan_returns_a_contract_with_expiry():
    plan = RollPlan(root="ABC")
    contract = plan.active(date(2026, 1, 15))
    assert contract.symbol.startswith("ABC")
    assert contract.expiry == third_friday(2026, 3)


def test_roll_plan_switches_after_expiry():
    plan = RollPlan(root="ABC")
    before = plan.active(date(2026, 3, 18))
    after = plan.active(date(2026, 3, 20))
    assert before.expiry != after.expiry
    assert after.expiry == third_friday(2026, 6)


def test_roll_plan_rolls_ahead_when_configured():
    plan = RollPlan(root="ABC", roll_days_before=5)
    contract = plan.active(date(2026, 3, 16))
    assert contract.expiry == third_friday(2026, 6)


def test_roll_plan_crosses_the_year_boundary():
    plan = RollPlan(root="ABC")
    contract = plan.active(date(2026, 12, 20))
    assert contract.expiry.year == 2027
    assert "27" in contract.symbol


def _template() -> SessionTemplate:
    return SessionTemplate(
        name="RTH", timezone="America/New_York", open="09:30", close="16:00"
    )


def test_weekend_is_not_a_trading_day():
    calendar = Calendar()
    assert calendar.is_trading_day(date(2026, 1, 17), _template()) is False  # Saturday
    assert calendar.is_trading_day(date(2026, 1, 16), _template()) is True


def test_holidays_are_data_not_code():
    calendar = Calendar(holidays={date(2026, 1, 16)})
    assert calendar.is_trading_day(date(2026, 1, 16), _template()) is False


def test_early_close_overrides_template_close():
    calendar = Calendar(early_closes={date(2026, 11, 27): time(13, 0)})
    assert calendar.close_time(date(2026, 11, 27), _template()) == time(13, 0)
    assert calendar.close_time(date(2026, 11, 30), _template()) == time(16, 0)


def test_session_phases_around_open_and_close():
    calendar = Calendar()
    template = _template()
    pre = calendar.session(datetime(2026, 1, 16, 13, 0, tzinfo=timezone.utc), template)
    assert pre.phase == "pre"
    assert pre.is_open is False

    during = calendar.session(datetime(2026, 1, 16, 15, 0, tzinfo=timezone.utc), template)
    assert during.phase == "open"
    assert during.is_open is True

    after = calendar.session(datetime(2026, 1, 16, 22, 0, tzinfo=timezone.utc), template)
    assert after.is_open is False
    assert after.phase == "closed"


def test_session_on_a_holiday_is_closed():
    calendar = Calendar(holidays={date(2026, 1, 16)})
    session = calendar.session(datetime(2026, 1, 16, 15, 0, tzinfo=timezone.utc), _template())
    assert session.is_open is False
    assert session.phase == "closed"


def _overnight() -> SessionTemplate:
    return SessionTemplate(
        name="NIGHT",
        timezone="America/New_York",
        open="22:00",
        close="06:00",
        weekdays=[0, 1, 2, 3, 4, 5],
    )


def test_una_sesion_nocturna_sigue_abierta_de_madrugada():
    calendar = Calendar()
    local = datetime(2026, 1, 16, 2, 0, tzinfo=ZoneInfo("America/New_York"))

    session = calendar.session(local, _overnight())

    assert session.is_open is True
    assert session.id == "2026-01-15:NIGHT"


def test_el_calendario_y_el_motor_ven_la_misma_sesion_nocturna():
    calendar = Calendar()
    template = _overnight()
    for hour in (21, 22, 23, 2, 6, 7):
        clock = datetime(2026, 1, 16, hour, 0, tzinfo=ZoneInfo("America/New_York"))
        assert calendar.session(clock, template) == session_for(clock, template)


def test_el_calendario_y_el_motor_ven_la_misma_sesion_diurna():
    calendar = Calendar()
    template = _template()
    for hour in (9, 10, 16, 17, 22):
        clock = datetime(2026, 1, 16, hour, 0, tzinfo=ZoneInfo("America/New_York"))
        assert calendar.session(clock, template) == session_for(clock, template)
