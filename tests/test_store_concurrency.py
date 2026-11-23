"""Un solo SQLite, varios hilos: las escrituras se serializan.

El motor escribe desde el bucle de eventos y la API desde el hilo de la
petición. Sin bloqueo, dos `with conn:` solapados terminan en
«cannot commit - no transaction is active» — un fallo real visto en
/api/bot/start mientras el replay corría.
"""

from __future__ import annotations

import threading

from server.db import Store


def test_concurrent_writes_do_not_lose_transactions(tmp_path):
    store = Store(tmp_path / "concurrent.db")
    errors: list[BaseException] = []

    def worker(worker_id: int) -> None:
        try:
            for index in range(25):
                store.insert_event("info", "test", f"{worker_id}-{index}")
        except BaseException as error:  # noqa: BLE001 - se re-lanza en el hilo principal
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    row = store.conn.execute("SELECT COUNT(*) AS total FROM events").fetchone()
    assert row["total"] == 100
    store.close()


def test_row_factory_survives_the_lock_wrapper(tmp_path):
    store = Store(tmp_path / "rows.db")
    store.insert_event("info", "test", "una fila")
    rows = store.list_events(limit=1)
    assert rows and isinstance(rows[0], dict)
    assert rows[0]["message"] == "una fila"
    store.close()
