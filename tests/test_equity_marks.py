"""La curva auditada no lleva marcas intradía; la deriva sí se detecta."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from server import equity
from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.models import TradeRecord

STAMP = datetime(2026, 11, 26, 17, 30, tzinfo=timezone.utc)


def test_la_marca_intradia_va_a_su_tabla_y_no_a_la_curva(tmp_path):
    store = Store(tmp_path / "terminal.db")
    try:
        engine = TradingEngine(Settings(), store, feed=None)
        engine.execution.position = SimpleNamespace(symbol="BTC")
        engine.state.equity = 24_987.5
        engine.state.unrealized = -12.5

        engine._record_equity_point(STAMP)

        assert store.equity_curve() == []
        assert store.equity_marks() == [
            {"ts": STAMP.isoformat(), "equity": 24_975.0}
        ]
    finally:
        store.close()


def test_stats_api_separa_la_curva_auditada_de_las_marcas(client):
    engine = client.app.state.engine
    store = engine.store
    store.insert_trade(
        TradeRecord(
            symbol=engine.settings.instruments.primary,
            side="long",
            units=1,
            entry_price=100.0,
            exit_price=110.0,
            opened_ts=STAMP - timedelta(minutes=30),
            closed_ts=STAMP,
            pnl_net=10.0,
            mode=engine.mode,
            signal_key="separacion",
        )
    )
    store.append_equity_mark(24_990.0, STAMP - timedelta(minutes=10))

    payload = client.get("/api/stats").json()

    assert [point["equity"] for point in payload["equity"]] == [25_010.0]
    assert [point["equity"] for point in payload["equity_marks"]] == [24_990.0]
    assert payload["equity"][0]["ts"] != payload["equity_marks"][0]["ts"]


def test_la_auditoria_ignora_marcas_y_sigue_viendo_deriva(tmp_path):
    db = tmp_path / "terminal.db"
    store = Store(db)
    try:
        store.append_equity_mark(24_900.0, STAMP)
        assert equity.audit(db, 25_000.0)["ok"] is True

        # Una fila de más en `equity` no es una marca: es la curva desviada que
        # bloqueó el arranque, y la auditoría tiene que seguir cazándola.
        store.append_equity(25_100.0, STAMP)
        result = equity.audit(db, 25_000.0)
        assert result["ok"] is False
        assert "curve_rows" in result["issues"]
    finally:
        store.close()
