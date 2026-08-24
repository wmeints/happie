"""Tests for the happie.auth token store."""

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

from happie.auth._store import Token, save_token


def _token(expires_at: datetime) -> Token:
    return Token(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_at=expires_at,
    )


def test_save_token_writes_json_with_all_fields(tmp_path: Path) -> None:
    """save_token writes the three token fields as JSON with an ISO expiry."""
    path = tmp_path / "happie" / "token"
    save_token(_token(datetime(2026, 8, 24, 8, 0, 0, tzinfo=UTC)), path=path)
    data = json.loads(path.read_text())
    assert data == {
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "expires_at": "2026-08-24T08:00:00+00:00",
    }


def test_save_token_sets_user_only_modes(tmp_path: Path) -> None:
    """The token directory is 0700 and the file is 0600."""
    path = tmp_path / "happie" / "token"
    save_token(_token(datetime(2026, 8, 24, tzinfo=UTC)), path=path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_save_token_replaces_existing(tmp_path: Path) -> None:
    """A new save fully replaces the previously stored token."""
    path = tmp_path / "happie" / "token"
    save_token(_token(datetime(2026, 8, 24, tzinfo=UTC)), path=path)
    save_token(
        Token(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_at=datetime(2026, 8, 25, tzinfo=UTC),
        ),
        path=path,
    )
    data = json.loads(path.read_text())
    assert data["access_token"] == "new-access"
    assert data["refresh_token"] == "new-refresh"
