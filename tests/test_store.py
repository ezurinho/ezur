from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.migrations import CURRENT_VERSION, apply_migrations
from server.models import TradeRecord


def _trade(**overrides) -> TradeRecord:
    stamp = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
    payload = dict(
        symbol="PRIMARY",
        side="long",
        units=2,
        entry_price=100.0,
        exit_price=101.0,
        stop_price=99.5,
        target_price=101.5,
        opened_ts=stamp,
        closed_ts=stamp,
        pnl_gross=2.0,
        fees=1.24,
        pnl_net=0.76,
        r_multiple=0.38,
        exit_reason="target",
        mode="paper",
        signal_key="k1",
        diagnostics={"ambiguous_bar": False},
    )
    payload.update(overrides)
    return TradeRecord(**payload)


def test_store_creates_v1_schema(store):
    assert {
        "trades",
        "events",
        "equity",
        "kv",
        "backtests",
        "backtest_runs",
        "backtest_results",
        "backtest_ledger_outbox",
        "schema_migrations",
    } <= store.tables()


def test_wal_enabled(store):
    mode = store.conn.execute("pragma journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_events_capped_at_5000(store):
    for index in range(5010):
        store.insert_event("info", "test", str(index))
    assert store.count_events() == 5000


def test_migrations_are_idempotent(store):
    apply_migrations(store.conn)
    apply_migrations(store.conn)
    assert store.schema_version() == CURRENT_VERSION


def test_kv_roundtrip(store):
    store.kv_set("position", {"symbol": "PRIMARY"})
    assert store.kv_get("position") == {"symbol": "PRIMARY"}
    store.kv_delete("position")
    assert store.kv_get("position") is None


def test_trade_insert_and_list(store):
    store.insert_trade(_trade())
    rows = store.list_trades()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "PRIMARY"
    assert rows[0]["pnl_net"] == 0.76
    assert store.count_trades() == 1


def test_trade_filter_by_mode(store):
    store.insert_trade(_trade(mode="paper"))
    store.insert_trade(_trade(mode="backtest", signal_key="k2"))
    assert len(store.list_trades(mode="paper")) == 1
    assert len(store.list_trades(mode="backtest")) == 1


def test_accounting_can_isolate_a_mode(store):
    store.insert_trade(_trade(mode="paper", pnl_net=100.0, signal_key="paper"))
    store.insert_trade(_trade(mode="backtest", pnl_net=-40.0, signal_key="backtest"))
    assert store.realized_pnl() == pytest.approx(60.0)
    assert store.realized_pnl(mode="paper") == pytest.approx(100.0)
    assert store.realized_pnl(mode="backtest") == pytest.approx(-40.0)
    assert store.count_trades(mode="paper") == 1
    assert [trade.mode for trade in store.all_trades(mode="paper")] == ["paper"]


def test_equity_curve_is_chronological(store):
    stamp = datetime(2026, 1, 15, tzinfo=timezone.utc)
    store.append_equity(25000, stamp)
    store.append_equity(25010, stamp)
    curve = store.equity_curve()
    assert [point["equity"] for point in curve] == [25000, 25010]


def test_online_backup_is_a_consistent_snapshot(store, tmp_path):
    store.insert_trade(_trade(signal_key="before"))
    target = store.backup(tmp_path / "backup.db")
    store.insert_trade(_trade(signal_key="after", exit_price=102.0, closed_ts=datetime(2026, 1, 15, 15, 1, tzinfo=timezone.utc)))

    import sqlite3

    copied = sqlite3.connect(target)
    try:
        assert copied.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
        assert copied.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        copied.close()


def test_backtest_pagination(store):
    for index in range(5):
        store.save_backtest(f"run-{index:02d}", {"run_id": f"run-{index:02d}"})
    page = store.list_backtest_runs(limit=2)
    assert page["has_more"] is True
    assert len(page["runs"]) == 2
    assert page["next_cursor"] == page["runs"][-1]["run_id"]


def test_reset_stats_preserves_backtests(store):
    store.insert_trade(_trade())
    store.append_equity(25000.0)
    store.insert_event("info", "test", "hola")
    store.save_backtest("run-1", {"run_id": "run-1"})

    deleted = store.reset_stats()
    assert deleted["trades"] == 1
    assert deleted["events"] == 1
    assert deleted["equity"] == 1
    assert deleted["backtests"] == 0
    assert store.stats_counts()["backtests"] == 1


def test_reset_one_mode_preserves_other_trade_modes(store):
    store.insert_trade(_trade(mode="paper", signal_key="paper"))
    store.insert_trade(_trade(mode="backtest", signal_key="backtest"))
    store.reset_stats(mode="paper")
    assert [trade.mode for trade in store.all_trades()] == ["backtest"]


def test_reset_stats_can_clear_backtests(store):
    store.save_backtest("run-1", {"run_id": "run-1"})
    deleted = store.reset_stats(include_backtests=True)
    assert deleted["backtests"] == 1
    assert store.stats_counts()["backtests"] == 0

def test_reset_stats_clears_operational_state(store):
    store.kv_set("equity", 24_000.0)
    store.kv_set("peak_equity", 30_000.0)
    store.kv_set("day_stats", {"trades": 2})
    store.kv_set("session_id", "2026-11-24:CRYPTO24")
    store.kv_set("last_exit_ts", "2026-11-24T00:00:00+00:00")
    store.kv_set("position", {"symbol": "BTC"})
    store.kv_set("heartbeat", "2026-11-24T00:00:00+00:00")
    store.kv_set("emergency", True)

    store.reset_stats()

    for key in (
        "equity",
        "peak_equity",
        "day_stats",
        "session_id",
        "last_exit_ts",
        "position",
        "heartbeat",
    ):
        assert store.kv_get(key) is None
    assert store.kv_get("emergency") is True


def test_la_pagina_siguiente_no_repite_ni_salta_corridas(store):
    ids = ["b", "e", "a", "d", "c"]
    for run_id in ids:
        store.save_backtest(run_id, {"strategy_id": "reference", "trades": []})

    seen: list[str] = []
    cursor = None
    for _ in range(3):
        page = store.list_backtest_runs(cursor=cursor, limit=2)
        seen.extend(row["run_id"] for row in page["runs"])
        cursor = page["next_cursor"]

    assert seen == list(reversed(ids))
    assert len(set(seen)) == len(ids)
