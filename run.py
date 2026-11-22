"""Local entry point: API + engine + dashboard in one process."""

from __future__ import annotations

import os
import webbrowser

import uvicorn


def main() -> None:
    host = os.getenv("TERMINAL_HOST", os.getenv("YED_HOST", "127.0.0.1"))
    port = int(os.getenv("TERMINAL_PORT", os.getenv("YED_PORT", "8765")))
    if os.getenv("TERMINAL_OPEN") == "1":
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run("server.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
