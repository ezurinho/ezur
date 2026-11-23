"""Local entry point: API + engine + dashboard in one process."""

from __future__ import annotations

import os
import webbrowser

import uvicorn

from server.env import env


def main() -> None:
    host = env("HOST") or "127.0.0.1"
    port = int(env("PORT") or "8765")
    if env("OPEN") == "1":
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run("server.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
