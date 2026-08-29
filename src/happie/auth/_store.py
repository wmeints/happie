"""Token model and the user-only on-disk token store.

Persists the exchanged OAuth tokens to a JSON file that only the user can
read, creating its directory with restrictive permissions when missing.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["DEFAULT_TOKEN_PATH", "Token", "load_token", "save_token"]

#: Fixed location of the token file; no ``XDG_CONFIG_HOME`` override in this slice.
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "happie" / "token"

# Explicit modes, applied after creation so a permissive umask cannot weaken them.
_DIR_MODE = 0o700
_FILE_MODE = 0o600


@dataclass(frozen=True)
class Token:
    """A set of exchanged OAuth credentials with a computed expiry.

    Attributes
    ----------
        access_token: The bearer token for calling the Albert Heijn API.
        refresh_token: The refresh token used to obtain a new access token.
        expires_at: The moment the access token expires (timezone-aware UTC).
    """

    access_token: str
    refresh_token: str
    expires_at: datetime


def save_token(token: Token, path: Path = DEFAULT_TOKEN_PATH) -> None:
    """Write ``token`` to ``path`` as JSON, readable only by the user.

    Creates the parent directory (``0700``) when missing and the file
    (``0600``), replacing any pre-existing token. Modes are applied with an
    explicit ``chmod`` after creation so umask cannot weaken them.

    Args:
        token: The tokens to persist.
        path: Where to write the JSON file; defaults to
            ``~/.config/happie/token``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, _DIR_MODE)
    payload = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "expires_at": token.expires_at.astimezone(UTC).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(path, _FILE_MODE)


def load_token(path: Path = DEFAULT_TOKEN_PATH) -> Token | None:
    """Parse the stored-token JSON at ``path`` into a :class:`Token`.

    Args:
        path: Where to read the JSON file; defaults to
            ``~/.config/happie/token``.

    Returns
    -------
        The parsed token, or ``None`` when the file is missing, unreadable,
        or does not carry the three stored-token fields with a parseable,
        timezone-aware ``expires_at``.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _parse_token(payload)


def _parse_token(payload: object) -> Token | None:
    """Validate a decoded token-file payload and build a :class:`Token`.

    Args:
        payload: The value decoded from the token JSON file.

    Returns
    -------
        The token described by ``payload``, or ``None`` when it is not a
        mapping carrying the three stored-token fields with a parseable,
        timezone-aware ``expires_at``.
    """
    if not isinstance(payload, dict):
        return None
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        return None
    expires_at = _parse_expiry(payload.get("expires_at"))
    if expires_at is None:
        return None
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def _parse_expiry(value: object) -> datetime | None:
    """Parse a stored ``expires_at`` value into a timezone-aware datetime.

    Args:
        value: The raw value stored under the ``expires_at`` key.

    Returns
    -------
        The parsed datetime, or ``None`` when ``value`` is not a string,
        is not ISO-8601 parseable, or carries no timezone information.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
