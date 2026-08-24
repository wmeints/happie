"""Tests for the happie CLI commands and help discovery."""

import re

from typer.testing import CliRunner

from happie.cli import app, configure_logging

runner = CliRunner()
LOG_LINE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?\] \[INFO\] \[(.+)\]$"
)


def _logged_messages(err: str) -> list[str]:
    """Extract the message part of every formatted log line on stderr."""
    return [match.group(1) for match in LOG_LINE.finditer(err)]


def test_auth_login_runs_flow(monkeypatch) -> None:
    """`happie auth login` invokes the browser OAuth flow."""
    from happie import auth

    calls = []
    monkeypatch.setattr(auth, "login", lambda: calls.append(1))
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0
    assert calls == [1]


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
    """`happie auth --help` lists both `login` and `logout`."""
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "logout" in result.output
