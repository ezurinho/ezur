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
        # Lo fija el motor con la medición de ventaja contra coste del perfil.
        self.edge_guard = None

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

    def _strategy(
        self,
        output: StrategyOutput | None,
        rejections: dict[str, int] | None = None,
    ) -> StrategyBlock:
        cfg = self.settings.strategy
        meta = self.strategy_meta or {}
        strategy_id = meta.get("id", cfg.id)
        strategy_name = meta.get("name", cfg.id)
        strategy_version = meta.get("version", cfg.version)
        if output is None:
            # El motor detenido no es «sin estrategia»: el perfil sigue cargado.
            # Solo el NullStrategy real (id "null") no tiene regla que aplicar.
            pending = strategy_id == "null"
            return StrategyBlock(
                id=strategy_id,
                name=strategy_name,
                version=strategy_version,
                timeframe=cfg.timeframe,
                state="disabled" if pending else "idle",
                state_label="Sin estrategia" if pending else "Motor detenido",
                rejections=dict(rejections or {}),
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
            timeframe=cfg.timeframe,
            state=output.state,
            state_label=output.state_label,
            phases=self._phases(output),
            metrics=dict(self._metric(key, metric) for key, metric in output.metrics.items()),
            signal=signal,
            rejection=output.rejection,
            rejections=dict(rejections or {}),
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

    def _block_reason(self, state: EngineState) -> str | None:
        """El motivo del último rechazo, salvo que el propio estado lo desmienta.

        `block_reason` se queda pegado hasta el siguiente rechazo o el cambio de
        sesión. Tras un replay puede decir «posición abierta» cuando la posición
        ya se cerró, y tras subir un límite en Ajustes puede seguir diciendo
        «máximo de operaciones» cuando ya no lo es: el snapshot no puede afirmar
        un bloqueo que sus propios datos contradicen.
        """
        reason = state.block_reason
        if reason is None:
            return None
        cfg = self.settings.risk
        pending = any(order.status == "pending" for order in state.orders)
        if reason == "position_open" and state.position is None and not pending:
            return None
        if reason == "order_pending" and not pending:
            return None
        if reason == "max_trades_reached" and state.day_stats.trades < cfg.max_trades_per_day:
            return None
        loss_wall = -abs(cfg.initial_capital * cfg.max_daily_loss_pct / 100)
        if reason == "daily_loss_limit" and state.day_stats.pnl > loss_wall:
            return None
        if reason == "daily_profit_limit" and (
            cfg.max_daily_profit_pct <= 0
            or state.day_stats.pnl
            < cfg.initial_capital * cfg.max_daily_profit_pct / 100
        ):
            return None
        if reason == "consecutive_losses" and not cfg.loss_streak_cooldown_min:
            # Con minutos de pausa el motivo caduca por tiempo y aquí no se
            # sabe cuándo fue la última salida; sin pausa, la racha es el dato.
            if not cfg.no_trade_after_consecutive_losses:
                return None
            if state.day_stats.consecutive_losses < cfg.no_trade_after_consecutive_losses:
                return None
        return reason

    def _risk(self, state: EngineState) -> RiskModel:
        cfg = self.settings.risk
        reason = self._block_reason(state)
        guard = self.edge_guard
        edge = guard.as_dict() if guard is not None else None
        block_detail = None
        if guard is not None and guard.passes is False:
            # La guarda es del motor, no de la última vela: aunque el estado se
            # haya limpiado, el panel sigue diciendo por qué no se abre nada.
            if reason is None:
                reason = "edge_below_cost"
            if reason == "edge_below_cost":
                block_detail = guard.detail()
        # El motor aplica el límite sobre el capital inicial configurado, no
        # sobre la equity actual. Si la UI lo calcula por su cuenta con la
        # equity del día, anuncia un muro que no es el que después aplica.
        daily_loss_limit = cfg.initial_capital * cfg.max_daily_loss_pct / 100
        limits = {
            "risk_per_trade_pct": cfg.risk_per_trade_pct,
            "max_daily_loss_pct": cfg.max_daily_loss_pct,
            "daily_loss_limit": daily_loss_limit,
            # Sin el capital inicial la UI no puede decir «vas −2 % desde el
            # arranque» sin adivinar contra qué comparar.
            "initial_capital": cfg.initial_capital,
            "max_trades_per_day": float(cfg.max_trades_per_day),
            "loss_streak_cooldown_min": float(cfg.loss_streak_cooldown_min),
            "no_trade_after_consecutive_losses": float(
                cfg.no_trade_after_consecutive_losses
            ),
        }
        if cfg.soft_brakes:
            # Mismo umbral que server/risk.py: al 80 % del muro, media máquina.
            limits["soft_brake_at"] = daily_loss_limit * 0.8
        return RiskModel(
            equity=state.equity,
            open_risk=state.open_risk,
            daily_pnl=state.day_stats.pnl,
            daily_trades=state.day_stats.trades,
            blocked=bool(state.emergency or reason),
            block_reason=reason,
            block_count=state.block_count,
            block_detail=block_detail,
            edge=edge,
            limits=limits,
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
        public_settings = self.settings.model_dump(mode="json")
        if public_settings["alerts"]["webhook_url"]:
            # El snapshot viaja por WebSocket: no lleva credenciales de alertas.
            public_settings["alerts"]["webhook_url"] = "••••••"
        quality = state.quality
        staleness_ms = state.staleness_ms
        if (
            state.mode in {"paper", "live"}
            and state.provider in {"okx", "live"}
            and state.last_bar_ts is not None
        ):
            # Sin ticks nuevos el motor no puede envejecer su calidad: el
            # snapshot sí puede, usando el reloj de pared. Un replay histórico
            # conserva su calidad para no marcarse obsoleto por ser viejo.
            age_s = (
                _now() - (state.last_bar_ts if state.last_bar_ts.tzinfo else state.last_bar_ts.replace(tzinfo=timezone.utc))
            ).total_seconds()
            staleness_ms = max(staleness_ms, int(max(0.0, age_s) * 1000))
            if age_s > 900:
                quality = "stale"
            elif age_s > 180:
                quality = "degraded"
        data = SnapshotData(
            status=state.status,
            mode=state.mode,
            session=self._session(state),
            data=DataInfo(
                provider=state.provider or self.settings.feed.provider,
                quality=quality,
                last_bar_ts=state.last_bar_ts,
                staleness_ms=staleness_ms,
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
            strategy=self._strategy(output, rejections),
            position=self._position(state),
            orders=[OrderModel.model_validate(order.model_dump()) for order in state.orders],
            risk=self._risk(state),
            stats=stats or {},
            day_stats=state.day_stats.model_dump(),
            rejections=dict(rejections or {}),
            settings=public_settings,
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
