"""La retención de eventos conserva los últimos sin recorrer la tabla entera."""
from __future__ import annotations

from server.db import EVENTS_RETENTION, Store


def test_la_retencion_conserva_los_ultimos(tmp_path):
    store = Store(tmp_path / "events.db")
    try:
        for index in range(EVENTS_RETENTION + 25):
            store.insert_event("info", "test", f"evento {index}")

        assert store.count_events() == EVENTS_RETENTION
        newest = store.list_events(limit=1)[0]
        assert newest["message"] == f"evento {EVENTS_RETENTION + 24}"
        oldest = store.list_events(limit=EVENTS_RETENTION)[-1]
        assert oldest["message"] == "evento 25"
    finally:
        store.close()


def test_sin_llegar_al_limite_no_se_borra_nada(tmp_path):
    store = Store(tmp_path / "corto.db")
    try:
        for index in range(3):
            store.insert_event("warn", "test", f"corto {index}")
        assert store.count_events() == 3
    finally:
        store.close()
