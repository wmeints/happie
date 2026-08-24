"""Tests for happie.auth.get_access_token()."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from happie.auth import get_access_token
from happie.auth._flow import AuthenticationError
from happie.auth._store import Token, save_token
from happie.auth._token import REFRESH_URL


def _write_token(path: Path, expires_at: datetime) -> Token:
    """Store a fixed token triple at ``path``."""
    token = Token(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_at=expires_at,
    )
    save_token(token, path=path)
    return token


def test_valid_token_returned_without_refresh(tmp_path: Path) -> None:
    """A non-expired stored token is returned and no request is sent."""
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) + timedelta(hours=1))

    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the refresh endpoint must not be called")

    client = httpx.Client(transport=httpx.MockTransport(fail))
    assert get_access_token(path=path, client=client) == "access-secret"


def test_token_within_safety_skew_is_refreshed(tmp_path: Path) -> None:
    """A token expiring within five minutes is treated as expired."""
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) + timedelta(minutes=4))

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 7199,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert get_access_token(path=path, client=client) == "new-access"
    assert len(seen) == 1


def test_expired_token_refreshed_and_restored(tmp_path: Path) -> None:
    """An expired stored token is refreshed and the new pair re-stored."""
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) - timedelta(minutes=1))
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 7199,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert get_access_token(path=path, client=client) == "new-access"

    request = seen["request"]
    assert request.method == "POST"
    assert str(request.url) == REFRESH_URL
    assert request.headers["User-Agent"] == "Appie/8.22.3"
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {
        "clientId": "appie",
        "refreshToken": "refresh-secret",
    }

    data = json.loads(path.read_text())
    assert data["access_token"] == "new-access"
    assert data["refresh_token"] == "new-refresh"
    expiry = datetime.fromisoformat(data["expires_at"])
    assert expiry > datetime.now(UTC) + timedelta(seconds=7000)


def test_missing_token_raises_authentication_error(tmp_path: Path) -> None:
    """No token file raises an error telling the user to log in."""
    with pytest.raises(AuthenticationError, match="login"):
        get_access_token(path=tmp_path / "nope")


def test_refresh_failure_raises_and_keeps_stored_token(
    tmp_path: Path,
) -> None:
    """A rejected refresh raises and does not re-store anything."""
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) - timedelta(minutes=1))
    original = path.read_text()

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "expired"})
        )
    )
    with pytest.raises(AuthenticationError):
        get_access_token(path=path, client=client)
    assert path.read_text() == original


def test_refresh_malformed_body_raises_without_token(tmp_path: Path) -> None:
    """A 2xx refresh body missing fields raises without leaking values."""
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) - timedelta(minutes=1))

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"access_token": "secret-access"})
        )
    )
    with pytest.raises(AuthenticationError) as excinfo:
        get_access_token(path=path, client=client)
    message = str(excinfo.value)
    assert "access-secret" not in message
    assert "refresh-secret" not in message
    assert "secret-access" not in message


def test_no_token_values_in_log_records(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Neither the stored nor the refreshed token appears in log output."""
    caplog.set_level(logging.DEBUG, logger="happie.auth")
    path = tmp_path / "token"
    _write_token(path, datetime.now(UTC) - timedelta(minutes=1))

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 7199,
                },
            )
        )
    )
    get_access_token(path=path, client=client)

    for secret in ("access-secret", "refresh-secret", "new-access"):
        assert secret not in caplog.text
