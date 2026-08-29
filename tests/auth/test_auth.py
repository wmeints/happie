"""Tests for the happie.auth complete() and login() orchestration."""

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from happie import auth
from happie.auth import AuthenticationError, Token
from happie.auth._flow import AUTHORIZATION_URL
from happie.auth._store import save_token as store_save_token


def _fresh_token() -> Token:
    return Token(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


def _stale_token() -> Token:
    return Token(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )


def _install_fake_clock(monkeypatch, advance: float = 1.0) -> list:
    """Fake the clock: ``time.monotonic`` reads the list, sleep advances it."""
    clock = [time.monotonic()]
    monkeypatch.setattr("happie.auth.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "happie.auth.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + advance),
    )
    return clock


def _patch_login_seams(monkeypatch, token_path: Path) -> tuple[list, list]:
    """Route the handler/browser/token-file seams to test doubles."""
    ensured: list = []
    monkeypatch.setattr(auth, "ensure_handler", lambda: ensured.append(1))
    opened: list = []

    def fake_open(url):
        opened.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)
    monkeypatch.setattr("happie.auth.DEFAULT_TOKEN_PATH", token_path)
    return ensured, opened


@pytest.mark.parametrize(
    "raw",
    ["GOODCODE", "appie://login-exit?code=GOODCODE", "?code=GOODCODE"],
)
def test_complete_accepts_input_forms(raw: str, monkeypatch, caplog) -> None:
    """complete() extracts the code from any accepted input form and stores once."""
    caplog.set_level(logging.INFO, logger="happie.auth")
    exchanged: list[str] = []

    def fake_exchange(code):
        exchanged.append(code)
        return ("access-secret", "refresh-secret", 3600)

    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    saved: list[Token] = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    result = auth.complete(raw)

    assert exchanged == ["GOODCODE"]
    assert saved == [result]
    assert result.access_token == "access-secret"
    assert result.refresh_token == "refresh-secret"
    delta = result.expires_at - datetime.now(UTC)
    assert abs(delta - timedelta(seconds=3600)) < timedelta(seconds=5)
    assert "GOODCODE" not in caplog.text
    assert "access-secret" not in caplog.text
    assert "refresh-secret" not in caplog.text


def test_complete_url_without_code_fails_without_exchange_or_store(
    monkeypatch,
) -> None:
    """A code-less URL argument fails; nothing is exchanged or stored."""
    exchanged: list[str] = []
    monkeypatch.setattr(auth, "exchange_code", lambda code: exchanged.append(code))
    saved: list[Token] = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    with pytest.raises(AuthenticationError):
        auth.complete("appie://login-exit")

    assert exchanged == []
    assert saved == []


def test_complete_exchange_failure_raises_without_storing_or_logging_code(
    monkeypatch, caplog
) -> None:
    """An exchange failure propagates; no token is stored and the code is not logged."""
    caplog.set_level(logging.INFO, logger="happie.auth")

    def failing(code):
        raise AuthenticationError("the code could not be used")

    monkeypatch.setattr(auth, "exchange_code", failing)
    saved: list[Token] = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    with pytest.raises(AuthenticationError):
        auth.complete("GOODCODE")

    assert saved == []
    assert "GOODCODE" not in caplog.text


def test_complete_no_arg_prompts_then_stores_once(monkeypatch, caplog) -> None:
    """With no argument, a code-less URL re-prompts; a valid code stores once."""
    caplog.set_level(logging.INFO, logger="happie.auth")
    inputs = iter(["appie://login-exit", "GOODCODE"])
    prompts: list[str] = []

    def fake_prompt(text: str) -> str:
        prompts.append(text)
        return next(inputs)

    monkeypatch.setattr("typer.prompt", fake_prompt)
    exchanged: list[str] = []

    def fake_exchange(code):
        exchanged.append(code)
        return ("access-secret", "refresh-secret", 3600)

    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    saved: list[Token] = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    result = auth.complete()

    assert len(prompts) == 2
    assert exchanged == ["GOODCODE"]
    assert saved == [result]
    assert "GOODCODE" not in caplog.text
    assert "access-secret" not in caplog.text


def test_login_ends_wait_when_handler_stores_token(tmp_path: Path, monkeypatch) -> None:
    """Login ensures the handler, opens the browser, and exits on a fresh token."""
    token_path = tmp_path / "token"
    clock = _install_fake_clock(monkeypatch)
    ensured, opened = _patch_login_seams(monkeypatch, token_path)
    written: list = []

    def fake_sleep(seconds):
        if not written:
            written.append(1)
            store_save_token(_fresh_token(), path=token_path)
        clock[0] += 1.0

    monkeypatch.setattr("happie.auth.time.sleep", fake_sleep)

    auth.login()

    assert ensured == [1]
    assert opened == [AUTHORIZATION_URL]
    assert json.loads(token_path.read_text())["access_token"] == "access-secret"


def test_login_detects_in_place_rewrite(tmp_path: Path, monkeypatch) -> None:
    """An existing token file rewritten in place with a fresh expiry ends the wait."""
    token_path = tmp_path / "token"
    store_save_token(_stale_token(), path=token_path)
    before_mtime = token_path.stat().st_mtime_ns
    clock = _install_fake_clock(monkeypatch)
    _patch_login_seams(monkeypatch, token_path)
    written: list = []

    def fake_sleep(seconds):
        if not written:
            written.append(1)
            store_save_token(_fresh_token(), path=token_path)
        clock[0] += 1.0

    monkeypatch.setattr("happie.auth.time.sleep", fake_sleep)

    auth.login()

    assert token_path.stat().st_mtime_ns != before_mtime
    assert json.loads(token_path.read_text())["access_token"] == "access-secret"


def test_login_stale_token_keeps_waiting_until_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    """A changed file whose expiry is not in the future keeps the flow waiting."""
    token_path = tmp_path / "token"
    store_save_token(_stale_token(), path=token_path)
    clock = _install_fake_clock(monkeypatch)
    _patch_login_seams(monkeypatch, token_path)
    written: list = []

    def fake_sleep(seconds):
        if not written:
            written.append(1)
            store_save_token(_stale_token(), path=token_path)
        clock[0] += 1.0

    monkeypatch.setattr("happie.auth.time.sleep", fake_sleep)

    with pytest.raises(AuthenticationError, match="timed out"):
        auth.login()


def test_login_malformed_json_keeps_waiting_until_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    """A changed file that does not parse as stored-token JSON keeps the flow waiting."""
    token_path = tmp_path / "token"
    clock = _install_fake_clock(monkeypatch)
    _patch_login_seams(monkeypatch, token_path)
    written: list = []

    def fake_sleep(seconds):
        if not written:
            written.append(1)
            token_path.write_text("{broken", encoding="utf-8")
        clock[0] += 1.0

    monkeypatch.setattr("happie.auth.time.sleep", fake_sleep)

    with pytest.raises(AuthenticationError, match="timed out"):
        auth.login()


def test_login_times_out_without_any_token(tmp_path: Path, monkeypatch) -> None:
    """No token file update within the window raises the timeout error."""
    _install_fake_clock(monkeypatch)
    _patch_login_seams(monkeypatch, tmp_path / "token")

    with pytest.raises(AuthenticationError, match="timed out"):
        auth.login()


def test_login_no_browser_raises_and_does_not_wait(tmp_path: Path, monkeypatch) -> None:
    """If the browser cannot be opened, login fails without watching the file."""
    ensured: list = []
    monkeypatch.setattr(auth, "ensure_handler", lambda: ensured.append(1))
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: False)
    waited: list = []
    monkeypatch.setattr(auth, "_wait_for_token", lambda state: waited.append(state))

    with pytest.raises(AuthenticationError, match="browser"):
        auth.login()

    assert ensured == [1]
    assert waited == []
