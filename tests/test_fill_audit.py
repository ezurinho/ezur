"""El audit de fills separa lo imposible del slippage que el modelo declara."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server.fill_audit import audit_fills, load_candles
from server.models import Bar, TradeRecord

STAMP = datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc)


def _bar(when: datetime, low: float, high: float) -> Bar:
    return Bar(t=when, o=low, h=high, l=low, c=high, v=1.0)


def _trade(
    index: int,
    *,
    opened: datetime,
    closed: datetime,
    entry: float,
    exit_price: float,
    pnl: float,
) -> TradeRecord:
    return TradeRecord(
        symbol="BTC",
        side="long",
        units=1,
        entry_price=entry,
        exit_price=exit_price,
        opened_ts=opened,
        closed_ts=closed,
        pnl_net=pnl,
        mode="backtest",
        signal_key=f"k{index}",
    )


def test_cuenta_fills_imposibles_y_mide_la_caida_de_pf():
    candles = {
        ("BTC", STAMP): _bar(STAMP, 99.0, 101.0),
        ("BTC", STAMP + timedelta(minutes=5)): _bar(
            STAMP + timedelta(minutes=5), 109.0, 111.0
        ),
        ("BTC", STAMP + timedelta(minutes=10)): _bar(
            STAMP + timedelta(minutes=10), 99.0, 101.0
        ),
        ("BTC", STAMP + timedelta(minutes=15)): _bar(
            STAMP + timedelta(minutes=15), 89.0, 91.0
        ),
        ("BTC", STAMP + timedelta(minutes=20)): _bar(
            STAMP + timedelta(minutes=20), 99.0, 101.0
        ),
        ("BTC", STAMP + timedelta(minutes=25)): _bar(
            STAMP + timedelta(minutes=25), 119.0, 121.0
        ),
    }
    trades = [
        _trade(
            0,
            opened=STAMP,
            closed=STAMP + timedelta(minutes=5),
            entry=100.0,
            exit_price=110.0,
            pnl=10.0,
        ),
        _trade(
            1,
            opened=STAMP + timedelta(minutes=10),
            closed=STAMP + timedelta(minutes=15),
            entry=100.0,
            exit_price=90.0,
            pnl=-20.0,
        ),
        # La salida a 130 no cabe en la vela 119..121: es imposible y además
        # ganadora, así que quitarla tiene que hacer caer el PF.
        _trade(
            2,
            opened=STAMP + timedelta(minutes=20),
            closed=STAMP + timedelta(minutes=25),
            entry=100.0,
            exit_price=130.0,
            pnl=30.0,
        ),
    ]

    result = audit_fills(trades, candles)

    assert result["impossible_fills"] == 1
    assert result["impossible_exit_fills"] == 1
    assert result["trades_removed"] == 1
    assert result["pf_before"] == pytest.approx(2.0)
    assert result["pf_after"] == pytest.approx(0.5)
    assert result["pf_drop"] == pytest.approx(1.5)
    assert len(result["details"]) == 1
    detail = result["details"][0]
    assert detail["trade"] == 2
    assert detail["leg"] == "exit"
    assert detail["status"] == "impossible"
    assert detail["ts"] == (STAMP + timedelta(minutes=25)).isoformat()
    assert detail["price"] == 130.0
    assert detail["low"] == 119.0
    assert detail["high"] == 121.0
    assert detail["overshoot_ticks"] == pytest.approx(900.0)


def test_la_tolerancia_de_slippage_no_marca_un_fill_modelado():
    candles = {
        ("BTC", STAMP): _bar(STAMP, 99.0, 101.0),
        ("BTC", STAMP + timedelta(minutes=5)): _bar(
            STAMP + timedelta(minutes=5), 109.0, 111.0
        ),
    }
    trade = _trade(
        0,
        opened=STAMP,
        closed=STAMP + timedelta(minutes=5),
        entry=101.04,  # 4 ticks por encima del high
        exit_price=110.0,
        pnl=10.0,
    )

    result = audit_fills([trade], candles, tolerance_ticks=5)

    assert result["outside_ohlc_fills"] == 1
    assert result["tolerated_fills"] == 1
    assert result["impossible_fills"] == 0
    assert result["trades_removed"] == 0
    assert result["pf_before"] == result["pf_after"] == pytest.approx(1.0)


def test_load_candles_filtra_por_clave_y_normaliza_al_minuto(tmp_path: Path):
    path = tmp_path / "candles.csv"
    path.write_text(
        "ts,symbol,o,h,l,c,v\n"
        "2026-11-26T10:00:30+00:00,BTC,100,101,99,100.5,2\n"
        "2026-11-26T10:01:00+00:00,BTC,100,102,98,101,3\n",
        encoding="utf-8",
    )

    candles = load_candles(path, {("BTC", STAMP)})

    assert len(candles) == 1
    bar = candles[("BTC", STAMP)]
    assert bar.t == STAMP
    assert (bar.l, bar.h) == (99.0, 101.0)
