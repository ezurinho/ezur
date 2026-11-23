"""Trazabilidad de corridas y comparación de estrategias sobre el mismo dataset."""

from __future__ import annotations

from server.backtest import config_fingerprint, run_backtest
from server.config import Settings
from server.strategy.registry import resolve_strategy
from tests.test_api_backtest import _dataset, app_client  # noqa: F401  (fixture)


def test_same_dataset_twice_gets_two_run_ids(tmp_path):
    settings = Settings()
    settings.instruments.items = [
        type(settings.instruments.items[0])(symbol="PRIMARY", role="primary"),
        type(settings.instruments.items[0])(symbol="CTX_A", role="context"),
    ]
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=60)

    first = run_backtest(settings, path)
    second = run_backtest(settings, path)

    assert first.dataset_id == second.dataset_id
    assert first.run_id != second.run_id
    assert len(first.config_hash) == 16


def test_config_hash_changes_with_the_effective_settings(tmp_path):
    base = Settings()
    changed = Settings()
    changed.risk.risk_per_trade_pct = base.risk.risk_per_trade_pct + 0.25

    assert config_fingerprint(base) != config_fingerprint(changed)
    assert config_fingerprint(base) == config_fingerprint(Settings())


def test_two_strategies_share_dataset_but_not_run(tmp_path):
    settings = Settings()
    settings.instruments.items = [
        type(settings.instruments.items[0])(symbol="PRIMARY", role="primary"),
        type(settings.instruments.items[0])(symbol="CTX_A", role="context"),
    ]
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=80)

    a = run_backtest(settings, path, resolve_strategy("reference", None), run_group="grp")
    b = run_backtest(settings, path, resolve_strategy("donchian", None), run_group="grp")

    assert a.dataset_id == b.dataset_id
    assert a.config_hash == b.config_hash
    assert a.run_id != b.run_id
    assert a.run_group == b.run_group == "grp"


def test_compare_endpoint_returns_one_row_per_strategy(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=80)

    response = client.post(
        "/api/backtest/compare",
        json={"dataset_path": str(path), "strategies": ["reference", "donchian", "null"]},
    )
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["rows"]) == 3
    assert {row["strategy_id"] for row in payload["rows"]} == {"reference", "donchian", "null"}
    assert {row["run_group"] for row in payload["rows"]} == {payload["run_group"]}
    assert len({row["run_id"] for row in payload["rows"]}) == 3
    assert len({row["dataset_id"] for row in payload["rows"]}) == 1
    for row in payload["rows"]:
        assert row["verdict"] in {"APROBADA", "RECHAZADA", "INCONCLUSA"}
        assert "outcomes" in row["gates"]


def test_compare_sorts_by_expectancy(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=80)
    payload = client.post(
        "/api/backtest/compare", json={"dataset_path": str(path)}
    ).json()

    expectancies = [row["metrics"]["expectancy_r"] for row in payload["rows"]]
    assert expectancies == sorted(expectancies, reverse=True)


def test_compare_rejects_unknown_strategy(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=40)
    response = client.post(
        "/api/backtest/compare",
        json={"dataset_path": str(path), "strategies": ["no_existe"]},
    )
    assert response.status_code == 422


def test_compare_writes_ledger_entries_with_run_group(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=60)
    payload = client.post(
        "/api/backtest/compare",
        json={"dataset_path": str(path), "strategies": ["reference", "null"]},
    ).json()

    entries = client.get("/api/experiments").json()["entries"]
    group = payload["run_group"]
    matching = [entry for entry in entries if entry.get("run_group") == group]
    assert len(matching) == 2
    assert all(entry["kind"] == "backtest_compare" for entry in matching)
    assert {entry["run_id"] for entry in matching} == {row["run_id"] for row in payload["rows"]}


def test_strategies_endpoint_lists_plugins_with_versions(app_client):
    client, _, _ = app_client
    payload = client.get("/api/backtest/strategies").json()
    ids = {item["id"] for item in payload["items"]}
    assert {"reference", "donchian", "fade", "null"} <= ids
    assert all(item["version"] for item in payload["items"])
    assert payload["active"] == "reference"
