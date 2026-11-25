"""Guard: the infrastructure must stay agnostic.

If this test fails, a concrete instrument or a concrete strategy concept leaked
into code that is supposed to know nothing about either.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Tickers del bot original. En mayúsculas a propósito: `es` español no es `ES`.
BANNED = re.compile(r"\b(MNQ|NQ|ES|ORB|SMT)\b")
# Conceptos de estrategia que no deben vivir en la infraestructura, en cualquier caja.
STRATEGY_LEAKS = re.compile(
    r"(orb_session|opening_range|opening-range|smt_divergence|breakout_retest|order_block|fair_value_gap)",
    re.IGNORECASE,
)

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


def _leaks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group(0) for match in BANNED.finditer(text)] + [
        match.group(0) for match in STRATEGY_LEAKS.finditer(text)
    ]


def test_no_hardcoded_instruments_or_strategy_concepts_in_source():
    offenders = [
        f"{path.relative_to(ROOT)}: {', '.join(_leaks(path))}"
        for path in _sources()
        if _leaks(path)
    ]
    assert offenders == []


def test_the_guard_catches_the_lowercase_leaks_that_slipped_through():
    # El caso real: `orb_session` en research.py pasaba el guard por la caja.
    assert STRATEGY_LEAKS.search("if blueprint['rule'] == 'orb_session':")
    assert STRATEGY_LEAKS.search("document['entry']['opening_range']")
    assert not STRATEGY_LEAKS.search("session_ready")
    # `ES` mayúsculas es un ticker; `es` minúsculas es español y no debe saltar.
    assert BANNED.search("MNQ")
    assert not BANNED.search("esto es una prueba")


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
