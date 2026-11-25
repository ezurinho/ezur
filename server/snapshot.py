"""Snapshot builder.

Contracts in, contract out. Every instrument map is produced by iterating the
configured instruments, so adding or removing a symbol is a configuration
change and never a code change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import Settings
from .db import Store
from .models import Bar, EngineState
from .schemas import (
    SNAPSHOT_VERSION,
    ChartModel,
    CandleModel,
    DataInfo,
    InstrumentModel,
    KvEntryModel,
    MarkerModel,
    OrderModel,
    PhaseModel,
    PositionModel,
    QuoteModel,
    RiskModel,
    SeriesModel,
    SessionModel,
    SignalModel,
    SnapshotData,
    StrategyBlock,
    UIModel,
    ZoneModel,
)
from .strategy.base import Marker, Metric, Phase, StrategyOutput, Zone

logger = logging.getLogger(__name__)

KNOWN_ZONE_KINDS = {"band", "line", "box", "region"}
KNOWN_MARKER_KINDS = {"entry", "exit", "phase", "note", "warning"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SnapshotBuilder:
    def __init__(self, settings: Settings, store: Store | None = None) -> None:
        self.settings = settings
        # Filled by the engine with the resolved plugin, so the UI shows the
        # strategy that is actually running, not just what the config claims.
        self.strategy_meta: dict[str, str] | None = None
        self.store = store

    # --- pieces -----------------------------------------------------------
    def _instruments(self) -> list[InstrumentModel]:
        return [
            InstrumentModel(
                symbol=item.symbol,
                role=item.role,
                enabled=item.enabled,
                tick_size=item.tick_size,
                tick_value=item.tick_value,
                point_value=item.point_value,
                currency=item.currency,
                decimals=item.decimals,
            )
            for item in self.settings.instruments.items
        ]

    def _quotes(self, quotes: dict[str, dict[str, Any]] | None) -> dict[str, QuoteModel]:
        """One entry per configured instrument, no orphans, no gaps."""
        payload = quotes or {}
        return {
            instrument.symbol: QuoteModel.model_validate(payload.get(instrument.symbol, {}))
            for instrument in self.settings.instruments.items
        }

    def _phases(self, output: StrategyOutput | None) -> list[PhaseModel]:
        if output is None:
            return []
        return [self._phase(phase) for phase in output.phases]

    @staticmethod
    def _phase(phase: Phase) -> PhaseModel:
        return PhaseModel(
            key=phase.key,
            label=phase.label,
            status=phase.status,
            ts=phase.ts,
            detail=phase.detail,
        )

    @staticmethod
    def _metric(key: str, metric: Metric) -> tuple[str, KvEntryModel]:
        return key, KvEntryModel(
            label=metric.label,
            value=metric.value,
            format=metric.format,
            unit=metric.unit,
            tone=metric.tone,
            group=metric.group,
        )

    def _zones(self, output: StrategyOutput | None) -> list[ZoneModel]:
        zones: list[ZoneModel] = []
        for zone in output.zones if output else []:
            if zone.kind not in KNOWN_ZONE_KINDS:
                logger.warning("unsupported zone kind %r dropped", zone.kind)
                continue
            zones.append(self._zone(zone))
        return zones

    @staticmethod
    def _zone(zone: Zone) -> ZoneModel:
        return ZoneModel(
            id=zone.id,
            kind=zone.kind,
            from_ts=zone.from_ts,
            price_low=zone.price_low,
            price_high=zone.price_high,
            label=zone.label,
            to_ts=zone.to_ts,
            style=zone.style,
            active=zone.active,
        )

    def _markers(self, output: StrategyOutput | None) -> list[MarkerModel]:
        markers: list[MarkerModel] = []
        for marker in output.markers if output else []:
            if marker.kind not in KNOWN_MARKER_KINDS:
                logger.warning("unsupported marker kind %r dropped", marker.kind)
                continue
            markers.append(self._marker(marker))
        return markers

    @staticmethod
    def _marker(marker: Marker) -> MarkerModel:
        return MarkerModel(
            id=marker.id,
            ts=marker.ts,
            price=marker.price,
            kind=marker.kind,
            side=marker.side,
            label=marker.label,
        )

    def _series(self, series: Iterable[dict[str, Any]] | None) -> list[SeriesModel]:
        known = set(self.settings.instruments.symbols)
        result: list[SeriesModel] = []
        for item in series or []:
            if item.get("symbol") not in known:
                logger.warning("series for unconfigured symbol %r dropped", item.get("symbol"))
                continue
            result.append(SeriesModel.model_validate(item))
        return result

    def _candles(self, candles: Iterable[Bar] | None) -> list[CandleModel]:
        return [
            CandleModel(t=bar.t, o=bar.o, h=bar.h, l=bar.l, c=bar.c, v=bar.v)
            for bar in candles or []
        ]

    def _strategy(self, output: StrategyOutput | None) -> StrategyBlock:
        cfg = self.settings.strategy
        meta = self.strategy_meta or {}
        strategy_id = meta.get("id", cfg.id)
        strategy_name = meta.get("name", cfg.id)
        strategy_version = meta.get("version", cfg.version)
        if output is None:
            return StrategyBlock(
                id=strategy_id,
                name=strategy_name,
                version=strategy_version,
                state="disabled",
                state_label="Sin estrategia",
            )
        signal = None
        if output.signal is not None:
            signal = SignalModel(
                key=output.signal.key,
                side=output.signal.side,
                strength=output.signal.strength,
                reason=output.signal.reason,
                ts=output.signal.ts,
                valid_until=output.signal.valid_until,
                stop_price=output.signal.stop_price,
                target_price=output.signal.target_price,
            )
        return StrategyBlock(
            id=strategy_id,
            name=strategy_name,
            version=strategy_version,
            state=output.state,
            state_label=output.state_label,
            phases=self._phases(output),
            metrics=dict(self._metric(key, metric) for key, metric in output.metrics.items()),
            signal=signal,
            rejection=output.rejection,
        )

    def _session(self, state: EngineState) -> SessionModel:
        if state.session is None:
            return SessionModel(id="none", label="none", is_open=False)
        return SessionModel(
            id=state.session.id,
            label=state.session.label,
            is_open=state.session.is_open,
            open_ts=state.session.open_ts,
            close_ts=state.session.close_ts,
            phase=state.session.phase,
        )

    def _position(self, state: EngineState) -> PositionModel | None:
        if state.position is None:
            return None
        position = state.position
        return PositionModel(
            symbol=position.symbol,
            side=position.side,
            units=position.units,
            entry_price=position.entry_price,
            stop_price=position.stop_price,
            target_price=position.target_price,
            opened_ts=position.opened_ts,
            unrealized=state.unrealized,
            r_open=(state.unrealized / state.open_risk)
            if state.open_risk
            else None,
        )

    def _risk(self, state: EngineState) -> RiskModel:
        cfg = self.settings.risk
        return RiskModel(
            equity=state.equity,
            open_risk=state.open_risk,
            daily_pnl=state.day_stats.pnl,
            daily_trades=state.day_stats.trades,
            blocked=bool(state.emergency or state.block_reason),
            block_reason=state.block_reason,
            block_count=state.block_count,
            limits={
                "risk_per_trade_pct": cfg.risk_per_trade_pct,
                "max_daily_loss_pct": cfg.max_daily_loss_pct,
                "max_trades_per_day": float(cfg.max_trades_per_day),
                "loss_streak_cooldown_min": float(cfg.loss_streak_cooldown_min),
                "no_trade_after_consecutive_losses": float(
                    cfg.no_trade_after_consecutive_losses
                ),
            },
        )

    # --- public -----------------------------------------------------------
    def build(
        self,
        state: EngineState,
        output: StrategyOutput | None = None,
        *,
        quotes: dict[str, dict[str, Any]] | None = None,
        candles: Iterable[Bar] | None = None,
        series: Iterable[dict[str, Any]] | None = None,
        stats: dict[str, Any] | None = None,
        rejections: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        data = SnapshotData(
            status=state.status,
            mode=state.mode,
            session=self._session(state),
            data=DataInfo(
                provider=state.provider or self.settings.feed.provider,
                quality=state.quality,
                last_bar_ts=state.last_bar_ts,
                staleness_ms=state.staleness_ms,
                bars_available=state.bars_available,
            ),
            instruments=self._instruments(),
            quotes=self._quotes(quotes),
            chart=ChartModel(
                primary=self.settings.instruments.primary,
                candles=self._candles(candles),
                series=self._series(series),
                zones=self._zones(output),
                markers=self._markers(output),
            ),
            strategy=self._strategy(output),
            position=self._position(state),
            orders=[OrderModel.model_validate(order.model_dump()) for order in state.orders],
            risk=self._risk(state),
            stats=stats or {},
            day_stats=state.day_stats.model_dump(),
            rejections=dict(rejections or {}),
            settings=self.settings.model_dump(mode="json"),
            ui=UIModel(
                panels=list(self.settings.ui.panels),
                theme=self.settings.ui.theme,
                locale=self.settings.ui.locale,
            ),
        )
        return {
            "type": "snapshot",
            "v": SNAPSHOT_VERSION,
            "ts": _now().isoformat(),
            "data": data.model_dump(mode="json"),
        }
