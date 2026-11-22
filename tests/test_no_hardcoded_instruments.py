"""Guard: the infrastructure must stay agnostic.

If this test fails, a concrete instrument or a concrete strategy concept leaked
into code that is supposed to know nothing about either.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = re.compile(r"\b(MNQ|NQ|ES|ORB|SMT)\b")

SERVER_DIRS = [ROOT / "server"]
EXCLUDED_FROM_SERVER = {"market"}  # adapters may name contract families
FRONTEND = ROOT / "frontend" / "src"


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in SERVER_DIRS:
        for path in directory.rglob("*.py"):
            relative = path.relative_to(directory)
            if relative.parts and relative.parts[0] in EXCLUDED_FROM_SERVER:
                continue
            files.append(path)
    if FRONTEND.is_dir():
        for pattern in ("*.ts", "*.tsx"):
            files.extend(FRONTEND.rglob(pattern))
    return files


def test_no_hardcoded_instruments_in_source():
    offenders = [
        f"{path.relative_to(ROOT)}: {BANNED.search(path.read_text(encoding='utf-8')).group(0)}"
        for path in _sources()
        if BANNED.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_strategy_package_does_not_import_infrastructure():
    forbidden = ("server.db", "server.engine", "server.api", "server.execution")
    offenders = []
    for path in (ROOT / "server" / "strategy").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if f"from ..{name.split('.')[-1]}" in text or f"import {name}" in text:
                offenders.append(f"{path.name}: {name}")
    assert offenders == []


def test_frontend_has_no_literal_instrument_names():
    if not FRONTEND.is_dir():
        return
    offenders = [
        str(path) for path in FRONTEND.rglob("*.ts*")
        if "PRIMARY" in path.read_text(encoding="utf-8")
        and "__tests__" not in path.parts
    ]
    assert offenders == []
