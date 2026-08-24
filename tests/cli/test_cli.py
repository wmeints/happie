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


def test_auth_login_logs_stand_in(capsys) -> None:
    """`happie auth login` logs that it would authenticate via the browser."""
    configure_logging()
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0
    messages = _logged_messages(capsys.readouterr().err)
    assert any(
        "browser" in message and "access token" in message for message in messages
    ), f"unexpected stderr log lines: {messages!r}"


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
