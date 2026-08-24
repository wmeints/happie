"""Tests for the happie.auth protocol-handler installation."""

import stat
from pathlib import Path

import pytest

from happie.auth._flow import AuthenticationError
from happie.auth._handler import DESKTOP_ENTRY_PATH, ensure_handler


def _patch_cli_path(monkeypatch, path: str = "/opt/venv/bin/happie") -> None:
    """Point ``shutil.which`` at a fixed CLI location."""
    monkeypatch.setattr("happie.auth._handler.shutil.which", lambda name: path)


def _patch_gio(monkeypatch, calls: list) -> None:
    """Record ``gio`` invocations instead of running them."""

    def fake_run(command, **kwargs):
        calls.append(command)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("happie.auth._handler.subprocess.run", fake_run)


def test_default_entry_path() -> None:
    """The entry lives in the fixed XDG user applications directory."""
    assert (
        DESKTOP_ENTRY_PATH
        == Path.home() / ".local" / "share" / "applications" / "happie.desktop"
    )


def test_ensure_handler_writes_desktop_entry(tmp_path: Path, monkeypatch) -> None:
    """First write creates the entry with the scheme, NoDisplay, and an absolute Exec."""
    _patch_cli_path(monkeypatch)
    gio_calls: list = []
    _patch_gio(monkeypatch, gio_calls)
    path = tmp_path / "nested" / "happie.desktop"

    ensure_handler(path=path)

    assert path.read_text(encoding="utf-8") == (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=happie\n"
        "NoDisplay=true\n"
        'Exec="/opt/venv/bin/happie" auth complete %u\n'
        "MimeType=x-scheme-handler/appie;\n"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o755
    assert gio_calls == [["gio", "set", str(path), "trusted", "true"]]


def test_ensure_handler_no_rewrite_when_up_to_date(tmp_path: Path, monkeypatch) -> None:
    """An unchanged re-run leaves the file untouched (content and mtime)."""
    _patch_cli_path(monkeypatch)
    path = tmp_path / "happie.desktop"
    ensure_handler(path=path)
    before = path.stat()

    ensure_handler(path=path)

    assert path.stat() == before


def test_ensure_handler_rewrites_when_cli_path_changed(
    tmp_path: Path, monkeypatch
) -> None:
    """A stale Exec path (reinstall) triggers a rewrite to the current path."""
    _patch_cli_path(monkeypatch, "/opt/venv/bin/happie")
    gio_calls: list = []
    _patch_gio(monkeypatch, gio_calls)
    path = tmp_path / "happie.desktop"
    ensure_handler(path=path)
    assert len(gio_calls) == 1

    _patch_cli_path(monkeypatch, "/new/venv/bin/happie")
    ensure_handler(path=path)

    assert 'Exec="/new/venv/bin/happie" auth complete %u' in path.read_text(
        encoding="utf-8"
    )
    assert len(gio_calls) == 1  # trusted-mark is first-write only


def test_ensure_handler_raises_when_cli_not_found(tmp_path: Path, monkeypatch) -> None:
    """Without a resolvable CLI the install fails and writes nothing."""
    monkeypatch.setattr("happie.auth._handler.shutil.which", lambda name: None)

    with pytest.raises(AuthenticationError):
        ensure_handler(path=tmp_path / "happie.desktop")

    assert not (tmp_path / "happie.desktop").exists()


def test_ensure_handler_ignores_gio_failure(tmp_path: Path, monkeypatch) -> None:
    """A missing ``gio`` binary is swallowed; the entry is still written."""

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("gio not found")

    monkeypatch.setattr("happie.auth._handler.subprocess.run", missing)
    _patch_cli_path(monkeypatch)

    ensure_handler(path=tmp_path / "happie.desktop")

    assert (tmp_path / "happie.desktop").exists()
