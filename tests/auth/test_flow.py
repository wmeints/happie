"""Tests for happie.auth code parsing and token exchange."""

import json

import httpx
import pytest

from happie.auth._flow import (
    TOKEN_URL,
    AuthenticationError,
    exchange_code,
    extract_code,
)


def test_extract_code_bare() -> None:
    assert extract_code("ABC123") == "ABC123"


def test_extract_code_full_url() -> None:
    assert extract_code("appie://login-exit?code=ABC123") == "ABC123"


def test_extract_code_query_string() -> None:
    assert extract_code("?code=ABC123") == "ABC123"


def test_extract_code_url_without_code_returns_none() -> None:
    assert extract_code("appie://login-exit") is None


def test_extract_code_query_without_code_returns_none() -> None:
    assert extract_code("?foo=bar") is None


def test_exchange_code_sends_expected_request_and_parses_tokens() -> None:
    """exchange_code posts the pinned body/headers and parses the tokens."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 7199,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    access, refresh, expires_in = exchange_code("CODE", client=client)
    assert (access, refresh, expires_in) == ("access-secret", "refresh-secret", 7199)

    request = seen["request"]
    assert request.method == "POST"
    assert str(request.url) == TOKEN_URL
    assert request.headers["User-Agent"] == "Appie/8.22.3"
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {"clientId": "appie", "code": "CODE"}


def test_exchange_code_raises_on_non_2xx() -> None:
    """A non-2xx status raises AuthenticationError without the code."""
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, json={"error": "invalid code"})
        )
    )
    with pytest.raises(AuthenticationError) as excinfo:
        exchange_code("CODE", client=client)
    assert "CODE" not in str(excinfo.value)


def test_exchange_code_raises_on_malformed_body() -> None:
    """A 2xx body missing a required field raises without leaking the value."""
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"access_token": "secret-access"})
        )
    )
    with pytest.raises(AuthenticationError) as excinfo:
        exchange_code("CODE", client=client)
    message = str(excinfo.value)
    assert "CODE" not in message
    assert "secret-access" not in message
