"""El nombre cambió: EZUR_* manda, TERMINAL_* sigue funcionando."""

from __future__ import annotations

import pytest

from server.env import env, env_flag


def test_prefers_the_new_prefix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TERMINAL_PROFILE_DIR", "old")
    monkeypatch.setenv("EZUR_PROFILE_DIR", "new")
    assert env("PROFILE_DIR") == "new"


def test_falls_back_to_the_legacy_prefix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EZUR_PROFILE_DIR", raising=False)
    monkeypatch.setenv("TERMINAL_PROFILE_DIR", "old")
    assert env("PROFILE_DIR") == "old"


def test_default_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EZUR_PORT", raising=False)
    monkeypatch.delenv("TERMINAL_PORT", raising=False)
    assert env("PORT") is None
    assert env("PORT", "8765") == "8765"


def test_empty_string_is_not_a_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EZUR_HOST", "")
    monkeypatch.delenv("TERMINAL_HOST", raising=False)
    assert env("HOST", "127.0.0.1") == "127.0.0.1"


@pytest.mark.parametrize("raw,expected", [("1", True), ("true", True), ("on", True), ("0", False), ("nope", False)])
def test_flags(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool):
    monkeypatch.setenv("EZUR_OPEN", raw)
    assert env_flag("OPEN") is expected
