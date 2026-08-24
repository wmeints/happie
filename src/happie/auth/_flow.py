"""Authorization-code parsing and token exchange for the Albert Heijn OAuth flow.

Keeps the vendor-pinned URLs, headers, and request body internal, and turns a
raw token-endpoint response into a token triple or an ``AuthenticationError``.
"""

from urllib.parse import parse_qs

import httpx

__all__ = [
    "AUTHORIZATION_URL",
    "CLIENT_ID",
    "TOKEN_URL",
    "USER_AGENT",
    "AuthenticationError",
    "exchange_code",
    "extract_code",
]

CLIENT_ID = "appie"
USER_AGENT = "Appie/8.22.3"
AUTHORIZATION_URL = (
    "https://login.ah.nl/secure/oauth/authorize"
    "?client_id=appie&redirect_uri=appie://login-exit&response_type=code"
)
TOKEN_URL = "https://api.ah.nl/mobile-auth/v1/auth/token"


class AuthenticationError(Exception):
    """Raised when the OAuth login flow cannot complete.

    The message is safe to log: it never contains the authorization code or
    any token value.
    """


def extract_code(raw: str) -> str | None:
    """Pull the authorization code out of raw user input.

    Accepts a bare code, the full ``appie://login-exit?code=...`` deep-link
    URL, or a bare ``?code=...`` query string.

    Args:
        raw: The text the user pasted after logging in.

    Returns:
        The code, or ``None`` when the input looks like a URL or query string
        but carries no ``code`` value.
    """
    text = raw.strip()
    if not text:
        return None
    if "://" in text or text.startswith("?"):
        query = text.split("?", 1)[1] if "?" in text else ""
        values = parse_qs(query).get("code")
        return values[0] if values and values[0] else None
    return text


def exchange_code(
    code: str, *, client: httpx.Client | None = None
) -> tuple[str, str, int]:
    """Exchange ``code`` for tokens at the Albert Heijn token endpoint.

    Sends ``POST`` to ``TOKEN_URL`` with a JSON body carrying the client id and
    the code, the required ``User-Agent`` header, and no ``Authorization``
    header.

    Args:
        code: The authorization code from the browser flow.
        client: An optional ``httpx.Client`` (e.g. backed by a mock transport
            in tests). A disposable client is created and closed when omitted.

    Returns:
        A tuple of ``(access_token, refresh_token, expires_in)``.

    Raises:
        AuthenticationError: If the endpoint returns a non-2xx status or a 2xx
            body missing a required field.
    """
    own_client = client is None
    http = client or httpx.Client()
    try:
        response = http.post(
            TOKEN_URL,
            json={"clientId": CLIENT_ID, "code": code},
            headers={"User-Agent": USER_AGENT},
        )
    finally:
        if own_client:
            http.close()

    if response.status_code // 100 != 2:
        raise AuthenticationError(
            f"Token exchange failed with status {response.status_code}."
        )
    try:
        data = response.json()
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        expires_in = int(data["expires_in"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError(
            "Token exchange returned an unexpected response."
        ) from exc
    return access_token, refresh_token, expires_in
