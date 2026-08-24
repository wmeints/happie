"""Token model and the user-only on-disk token store.

Persists the exchanged OAuth tokens to a JSON file that only the user can
read, creating its directory with restrictive permissions when missing.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["DEFAULT_TOKEN_PATH", "Token", "save_token"]

#: Fixed location of the token file; no ``XDG_CONFIG_HOME`` override in this slice.
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "happie" / "token"

# Explicit modes, applied after creation so a permissive umask cannot weaken them.
_DIR_MODE = 0o700
_FILE_MODE = 0o600


@dataclass(frozen=True)
class Token:
    """A set of exchanged OAuth credentials with a computed expiry.

    Attributes:
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
