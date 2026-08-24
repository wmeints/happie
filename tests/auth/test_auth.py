"""Tests for the happie.auth.login() orchestration."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from happie import auth
from happie.auth import AuthenticationError, Token


def test_login_no_browser_raises_and_does_nothing(monkeypatch) -> None:
    """If the browser cannot be opened, login fails without exchange or store."""
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: False)
    exchanged: list[str] = []
    saved: list[Token] = []
    monkeypatch.setattr(auth, "exchange_code", lambda code: exchanged.append(code))
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    with pytest.raises(AuthenticationError):
        auth.login()

    assert exchanged == []
    assert saved == []


def test_login_reprompts_then_stores_once(monkeypatch, caplog) -> None:
    """A code-less URL re-prompts; a valid code stores exactly once, no secrets."""
    caplog.set_level(logging.INFO, logger="happie.auth")
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: True)

    inputs = iter(["appie://login-exit", "GOODCODE"])
    prompts: list[str] = []

    def fake_prompt(text: str) -> str:
        prompts.append(text)
        return next(inputs)

    monkeypatch.setattr("typer.prompt", fake_prompt)
    monkeypatch.setattr(
        auth,
        "exchange_code",
        lambda code: ("access-secret", "refresh-secret", 3600),
    )
    saved: list[Token] = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    result = auth.login()

    assert len(prompts) == 2
    assert len(saved) == 1
    assert isinstance(result, Token)
    assert result.access_token == "access-secret"
    assert result.refresh_token == "refresh-secret"
    delta = result.expires_at - datetime.now(UTC)
    assert abs(delta - timedelta(seconds=3600)) < timedelta(seconds=5)
    assert "GOODCODE" not in caplog.text
    assert "access-secret" not in caplog.text
    assert "refresh-secret" not in caplog.text
