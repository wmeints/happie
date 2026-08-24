"""Tests for the happie CLI commands and help discovery."""

import json
import re
import time
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from happie.cli import app, configure_logging

runner = CliRunner()
LOG_LINE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?\] \[INFO\] \[(.+)\]$"
)


def _logged_messages(err: str) -> list[str]:
    """Extract the message part of every formatted log line on stderr."""
    return [match.group(1) for match in LOG_LINE.finditer(err)]


def test_auth_login_ensures_handler_and_waits_for_token(
    monkeypatch, tmp_path, capsys
) -> None:
    """`happie auth login` installs the handler, opens the browser, and exits
    when the token file is updated — without prompting for the code."""
    from happie import auth
    from happie.auth._store import Token, save_token

    ensured = []
    monkeypatch.setattr(auth, "ensure_handler", lambda: ensured.append(1))
    opened = []

    def fake_open(url):
        opened.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)

    token_path = tmp_path / "token"
    monkeypatch.setattr("happie.auth.DEFAULT_TOKEN_PATH", token_path)

    clock = [time.monotonic()]
    monkeypatch.setattr("happie.auth.time.monotonic", lambda: clock[0])
    written = []

    def fake_sleep(seconds):
        if not written:
            written.append(1)
            save_token(
                Token(
                    access_token="access-secret",
                    refresh_token="refresh-secret",
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                ),
                path=token_path,
            )
        clock[0] += 1.0

    monkeypatch.setattr("happie.auth.time.sleep", fake_sleep)

    configure_logging()
    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 0
    assert ensured == [1]
    assert opened == [auth.AUTHORIZATION_URL]
    data = json.loads(token_path.read_text())
    assert data["access_token"] == "access-secret"
    assert "access-secret" not in capsys.readouterr().err


def test_auth_complete_stores_token(monkeypatch, capsys) -> None:
    """`happie auth complete <url>` exchanges the code, stores the token, exits 0."""
    from happie import auth

    exchanged = []

    def fake_exchange(code):
        exchanged.append(code)
        return ("access-secret", "refresh-secret", 3600)

    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    saved = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    configure_logging()
    result = runner.invoke(
        app, ["auth", "complete", "appie://login-exit?code=GOODCODE"]
    )

    assert result.exit_code == 0
    assert exchanged == ["GOODCODE"]
    assert len(saved) == 1
    err = capsys.readouterr().err
    assert "GOODCODE" not in err
    assert "access-secret" not in err
    assert any("Stored Albert Heijn access token." in m for m in _logged_messages(err))


def test_auth_complete_failing_exchange_exits_nonzero_without_storing(
    monkeypatch, capsys
) -> None:
    """A failing exchange exits 1, stores nothing, and keeps the code out of output."""
    from happie import auth
    from happie.auth import AuthenticationError

    def failing(code):
        raise AuthenticationError("the code could not be used")

    monkeypatch.setattr(auth, "exchange_code", failing)
    saved = []
    monkeypatch.setattr(auth, "save_token", lambda token: saved.append(token))

    configure_logging()
    result = runner.invoke(
        app, ["auth", "complete", "appie://login-exit?code=GOODCODE"]
    )

    assert result.exit_code == 1
    assert saved == []
    err = capsys.readouterr().err
    assert "GOODCODE" not in err
    assert "the code could not be used" in err


def test_auth_login_exits_nonzero_on_failure(monkeypatch, capsys) -> None:
    """`happie auth login` exits non-zero and logs guidance when it fails."""
    from happie.auth import AuthenticationError

    def failing() -> None:
        raise AuthenticationError("the code could not be used")

    monkeypatch.setattr("happie.auth.login", failing)
    configure_logging()
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 1
    err = capsys.readouterr().err
    assert "again" in err
    assert "the code could not be used" in err


def test_auth_logout_logs_stand_in(capsys) -> None:
    """`happie auth logout` logs that it would remove the stored token."""
    configure_logging()
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    messages = _logged_messages(capsys.readouterr().err)
    assert any(
        "remove" in message and "stored access token" in message for message in messages
    ), f"unexpected stderr log lines: {messages!r}"


def test_serve_logs_stand_in(capsys) -> None:
    """`happie serve` logs that it would start the MCP server."""
    configure_logging()
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    messages = _logged_messages(capsys.readouterr().err)
    assert any(
        "start" in message and "MCP server" in message for message in messages
    ), f"unexpected stderr log lines: {messages!r}"


def test_root_help_lists_auth_and_serve() -> None:
    """`happie --help` lists both the `auth` group and the `serve` command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "serve" in result.output


def test_auth_help_lists_login_and_logout() -> None:
    """`happie auth --help` lists `login`, `complete`, and `logout`."""
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "complete" in result.output
    assert "logout" in result.output
