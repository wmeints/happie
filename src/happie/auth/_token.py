"""Access-token retrieval and refresh for authenticated API requests.

Loads the stored token, returns the access token while it is still valid,
and otherwise refreshes it at the Albert Heijn refresh endpoint, re-storing
the refreshed pair with the token store's permissions.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from happie.auth._flow import CLIENT_ID, USER_AGENT, AuthenticationError
from happie.auth._store import DEFAULT_TOKEN_PATH, Token, save_token

__all__ = ["REFRESH_URL", "get_access_token"]

REFRESH_URL = "https://api.ah.nl/mobile-auth/v1/auth/token/refresh"

#: Tokens this close to expiry are refreshed early so long-running
#: processes do not race the exact expiry instant.
_SAFETY_SKEW = timedelta(minutes=5)

logger = logging.getLogger(__name__)


def get_access_token(
    *,
    path: Path = DEFAULT_TOKEN_PATH,
    client: httpx.Client | None = None,
) -> str:
    """Return a usable Albert Heijn access token.

    Returns the stored access token while it is valid. When it has expired
    (or is within a five-minute safety skew of expiry), it is refreshed
    via the refresh endpoint and the refreshed pair is re-stored.

    Parameters
    ----------
    path : Path
        Where the token JSON file lives; defaults to
        ``~/.config/happie/token``.
    client : httpx.Client | None
        An optional ``httpx.Client`` (e.g. backed by a mock transport in
        tests). A disposable client is created and closed when a refresh
        is needed and no client is given.

    Returns
    -------
    str
        The access token to use as the bearer credential.

    Raises
    ------
    AuthenticationError
        If no token is stored, or the refresh request fails or returns an
        unexpected body. No token value ever appears in a raised message
        or in log output.
    """  # noqa: DOC502, RUF100
    token = _load_token(path)
    if token.expires_at - _SAFETY_SKEW > datetime.now(UTC):
        return token.access_token

    logger.info("Stored access token is expired; refreshing.")
    access_token, refresh_token, expires_in = _refresh(token, client=client)
    save_token(
        Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        ),
        path=path,
    )
    logger.info("Access token refreshed and re-stored.")
    return access_token


def _load_token(path: Path) -> Token:
    """Read and parse the stored token file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Token(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
    except FileNotFoundError as exc:
        raise AuthenticationError(
            "No stored token. Run `happie auth login` first."
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("The stored token file is malformed.") from exc


def _refresh(
    stored: Token, *, client: httpx.Client | None = None
) -> tuple[str, str, int]:
    """Exchange the stored refresh token for a fresh token pair.

    Sends ``POST`` to ``REFRESH_URL`` with the client id and refresh token,
    the required ``User-Agent`` header, and no ``Authorization`` header.
    """
    own_client = client is None
    http = client or httpx.Client()
    try:
        response = http.post(
            REFRESH_URL,
            json={"clientId": CLIENT_ID, "refreshToken": stored.refresh_token},
            headers={"User-Agent": USER_AGENT},
        )
    finally:
        if own_client:
            http.close()

    if response.status_code // 100 != 2:
        raise AuthenticationError(
            f"Token refresh failed with status {response.status_code}."
        )
    try:
        data = response.json()
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        expires_in = int(data["expires_in"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError(
            "Token refresh returned an unexpected response."
        ) from exc
    return access_token, refresh_token, expires_in
