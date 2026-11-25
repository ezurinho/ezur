"""Estrategias spec-driven: las reglas del runner, enchufadas al motor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from server.models import Bar, SessionInfo
from server.strategy.base import MarketData
from server.strategy.spec_driven import (
    DonchianBreakoutParams,
    DonchianBreakoutStrategy,
    EMAStateParams,
    EMAStateStrategy,
    ORBSessionParams,
    ORBSessionStrategy,
    ZScoreFadeParams,
    ZScoreFadeStrategy,
)

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _session() -> SessionInfo:
    return SessionInfo(id="2026-01-15:RTH", label="RTH", is_open=True, phase="open")


def _bars(rows: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            t=NOW + timedelta(minutes=index),
            o=open_,
            h=high,
            l=low,
            c=close,
            v=10,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _flat(count: int, price: float = 100.0, width: float = 0.5) -> list[Bar]:
    return _bars([(price, price + width, price - width, price)] * count)


def _market(bars: list[Bar]) -> MarketData:
    return MarketData(
        session=_session(),
        clock=bars[-1].t,
        primary="PRIMARY",
        bars={"PRIMARY": bars},
        context={"tick_size": 0.25},
    )


def _closes(values: list[float]) -> list[Bar]:
    return _bars([(value, value + 0.4, value - 0.4, value) for value in values])


# --- Donchian --------------------------------------------------------------


def test_donchian_spec_pide_calor_antes_de_mirar_el_canal():
    strategy = DonchianBreakoutStrategy({"N": 5, "atr_k": 2.0, "tp_r": 2.0})

    output = strategy.evaluate(_market(_flat(4)))

    assert output.state == "warmup"
    assert output.signal is None
    assert output.phases[0].status == "active"


def test_donchian_spec_senal_larga_y_plan_de_salida():
    strategy = DonchianBreakoutStrategy(
        {"N": 5, "atr_period": 5, "atr_k": 2.0, "tp_r": 3.0}
    )
    bars = _flat(7) + _bars([(100.0, 107.0, 99.9, 106.5)])

    output = strategy.evaluate(_market(bars))

    assert output.state == "armed"
    signal = output.signal
    assert signal is not None and signal.side == "long"
    assert signal.stop_price < 106.5 < signal.target_price
    distance = 2.0 * output.metrics["atr"].value  # atr_k × ATR
    assert signal.stop_price == pytest.approx(106.5 - distance, abs=1e-4)
    assert signal.target_price == pytest.approx(106.5 + 3.0 * distance, abs=1e-4)
    assert 0 < signal.strength <= 1
    assert any(zone.kind == "box" for zone in output.zones)
    assert output.markers and output.markers[0].side == "long"


def test_donchian_spec_senal_corta_en_ruptura_bajista():
    strategy = DonchianBreakoutStrategy({"N": 5, "atr_period": 5, "atr_k": 1.0, "tp_r": 2.0})
    bars = _flat(7) + _bars([(100.0, 100.1, 92.0, 93.0)])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None
    assert output.signal.side == "short"
    assert output.signal.stop_price > 93.0
    assert output.signal.target_price < 93.0


def test_donchian_spec_no_opera_dentro_del_canal():
    strategy = DonchianBreakoutStrategy({"N": 5, "atr_period": 5, "atr_k": 1.0, "tp_r": 2.0})

    output = strategy.evaluate(_market(_flat(8)))

    assert output.state == "scanning"
    assert output.signal is None
    assert output.zones[0].price_high == pytest.approx(100.5)


def test_donchian_spec_respeta_el_suelo_del_stop():
    strategy = DonchianBreakoutStrategy(
        {"N": 5, "atr_period": 5, "atr_k": 0.1, "tp_r": 2.0, "stop_floor_frac": 0.02}
    )
    bars = _flat(7) + _bars([(100.0, 101.0, 99.9, 100.8)])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None
    # 2 % de 100,8 manda sobre un ATR de 1,0 por 0,1
    assert output.signal.stop_price == pytest.approx(100.8 - 0.02 * 100.8, abs=1e-4)


def test_donchian_spec_rechaza_parametros_que_no_cuadran():
    with pytest.raises(ValidationError):
        DonchianBreakoutStrategy({"N": 1, "atr_k": 2.0, "tp_r": 2.0})
    with pytest.raises(ValidationError):
        DonchianBreakoutStrategy({"N": 5, "atr_k": 2.0, "tp_r": 2.0, "extra": 1})


# --- EMA -------------------------------------------------------------------


def test_ema_spec_exige_slow_mayor_que_fast():
    with pytest.raises(ValidationError):
        EMAStateParams(fast=10, slow=10, atr_k=1.0, tp_r=2.0)


def test_ema_spec_cruce_al_alza():
    strategy = EMAStateStrategy(
        {"fast": 2, "slow": 3, "atr_period": 3, "atr_k": 1.0, "tp_r": 2.0}
    )

    output = strategy.evaluate(_market(_closes([100, 100, 100, 90, 110])))

    assert output.state == "armed"
    assert output.signal is not None and output.signal.side == "long"
    assert "EMA2/EMA3" in output.signal.reason
    assert output.markers[0].label == "EMA long"


def test_ema_spec_cruce_a_la_baja():
    strategy = EMAStateStrategy(
        {"fast": 2, "slow": 3, "atr_period": 3, "atr_k": 1.0, "tp_r": 2.0}
    )

    output = strategy.evaluate(_market(_closes([100, 100, 100, 110, 90])))

    assert output.signal is not None and output.signal.side == "short"


def test_ema_spec_sin_cruce_no_hay_senal():
    strategy = EMAStateStrategy(
        {"fast": 2, "slow": 3, "atr_period": 3, "atr_k": 1.0, "tp_r": 2.0}
    )

    output = strategy.evaluate(_market(_flat(6)))

    assert output.state == "scanning"
    assert output.signal is None


def test_ema_spec_pide_calor_hasta_la_ema_lenta():
    strategy = EMAStateStrategy(
        {"fast": 2, "slow": 20, "atr_period": 3, "atr_k": 1.0, "tp_r": 2.0}
    )

    assert strategy.warmup_requirements().bars["*"] == 22
    assert strategy.evaluate(_market(_flat(5))).state == "warmup"


# --- Z-Score ---------------------------------------------------------------


def test_zscore_spec_no_opera_una_ventana_plana():
    strategy = ZScoreFadeStrategy({"N": 5, "atr_period": 5})

    output = strategy.evaluate(_market(_flat(8)))

    assert output.state == "warmup"
    assert output.signal is None


def test_zscore_spec_vende_la_desviacion_al_alza():
    strategy = ZScoreFadeStrategy({"N": 5, "atr_period": 5, "z": 2.0})
    bars = _closes([99, 101] * 5 + [110])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None and output.signal.side == "short"
    assert output.signal.reason.startswith("z-score fade")
    assert output.metrics["z_score"].value > 2.0


def test_zscore_spec_compra_la_desviacion_a_la_baja():
    strategy = ZScoreFadeStrategy({"N": 5, "atr_period": 5, "z": 2.0})
    bars = _closes([99, 101] * 5 + [90])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None and output.signal.side == "long"
    assert output.signal.target_price > 90.0


def test_zscore_spec_espera_dentro_de_la_banda():
    strategy = ZScoreFadeStrategy({"N": 5, "atr_period": 5, "z": 2.0})
    bars = _closes([99, 101] * 5 + [100.2])

    output = strategy.evaluate(_market(bars))

    assert output.state == "scanning"
    assert output.signal is None
    assert len(output.zones) == 2


def test_zscore_spec_rechaza_ventanas_fuera_de_rango():
    with pytest.raises(ValidationError):
        ZScoreFadeParams(N=4)


# --- ORB -------------------------------------------------------------------


def test_orb_spec_pide_calor_para_el_rango():
    strategy = ORBSessionStrategy({"range_bars": 5, "atr_period": 5})

    output = strategy.evaluate(_market(_flat(3)))

    assert output.state == "warmup"


def test_orb_spec_ruptura_alcista_del_rango():
    strategy = ORBSessionStrategy(
        {"range_bars": 5, "atr_period": 5, "atr_k": 1.0, "tp_r": 2.0}
    )
    bars = _flat(7) + _bars([(100.0, 106.0, 99.9, 105.5)])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None and output.signal.side == "long"
    assert output.signal.reason == "ORB breakout rango 5"
    assert output.markers[0].label == "ORB long"
    assert output.zones[0].label == "Rango ORB(5)"


def test_orb_spec_ruptura_bajista_y_suelo_de_stop():
    strategy = ORBSessionStrategy(
        {"range_bars": 5, "atr_period": 5, "atr_k": 0.1, "tp_r": 2.0, "stop_floor_frac": 0.03}
    )
    bars = _flat(7) + _bars([(100.0, 100.1, 94.0, 95.0)])

    output = strategy.evaluate(_market(bars))

    assert output.signal is not None and output.signal.side == "short"
    assert output.signal.stop_price == pytest.approx(95.0 + 0.03 * 95.0, abs=1e-4)


def test_orb_spec_sin_ruptura_queda_esperando():
    strategy = ORBSessionStrategy({"range_bars": 5, "atr_period": 5})

    output = strategy.evaluate(_market(_flat(8)))

    assert output.state == "scanning"
    assert output.signal is None


def test_orb_spec_pide_calor_de_sesion():
    strategy = ORBSessionStrategy({"range_bars": 8, "atr_period": 5})

    assert strategy.warmup_requirements().session_ready is True
    assert strategy.warmup_requirements().bars["*"] == 10


def test_orb_spec_rechaza_rangos_fuera_de_rango():
    with pytest.raises(ValidationError):
        ORBSessionParams(range_bars=0)
