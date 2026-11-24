"""La ventana de sesión, también cuando cruza la medianoche."""
from __future__ import annotations

from datetime import datetime, timezone

from server.config import SessionTemplate
from server.timeutil import session_for


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _night() -> SessionTemplate:
    return SessionTemplate(
        name="noc", timezone="UTC", open="22:00", close="06:00", weekdays=[0, 1, 2, 3, 4]
    )


def test_una_sesion_nocturna_sigue_abierta_pasada_la_medianoche():
    template = _night()

    evening = session_for(_at("2026-11-24T23:00"), template)
    dawn = session_for(_at("2026-11-25T02:00"), template)

    assert evening.is_open is True
    assert dawn.is_open is True
    assert dawn.id == evening.id == "2026-11-24:noc"
    assert dawn.close_ts.date().isoformat() == "2026-11-25"


def test_la_sesion_nocturna_cierra_por_la_manana():
    template = _night()

    morning = session_for(_at("2026-11-25T12:00"), template)

    assert morning.is_open is False
    assert morning.phase == "closed"
    assert morning.id == "2026-11-24:noc"


def test_la_sesion_del_viernes_sigue_viva_el_sabado():
    template = _night()

    saturday = session_for(_at("2026-11-28T02:00"), template)

    # 2026-11-27 es viernes: la sesión abrió el viernes y cierra el sábado.
    assert saturday.id == "2026-11-27:noc"
    assert saturday.is_open is True


def test_una_sesion_normal_no_cambia():
    template = SessionTemplate(
        name="rth", timezone="UTC", open="09:30", close="16:00", weekdays=[0, 1, 2, 3, 4]
    )

    pre = session_for(_at("2026-11-24T08:00"), template)
    opened = session_for(_at("2026-11-24T10:00"), template)
    closing = session_for(_at("2026-11-24T16:30"), template)
    closed = session_for(_at("2026-11-24T18:00"), template)

    assert (pre.phase, pre.is_open) == ("pre", False)
    assert (opened.phase, opened.is_open) == ("open", True)
    assert (closing.phase, closing.is_open) == ("close", False)
    assert (closed.phase, closed.is_open) == ("closed", False)
    assert {pre.id, opened.id, closing.id, closed.id} == {"2026-11-24:rth"}
