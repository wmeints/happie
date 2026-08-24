"""Browser-based OAuth login for the Albert Heijn API.

Exposes ``login()``, which captures the authorization code from the user's
browser, exchanges it for tokens, and stores them. Code parsing, the token
exchange, and the token store live in private submodules so each seam is
unit-testable without a browser or network.
"""

import webbrowser
from datetime import UTC, datetime, timedelta

import typer

from happie.auth._flow import (
    AUTHORIZATION_URL,
    AuthenticationError,
    exchange_code,
    extract_code,
)
from happie.auth._store import Token, save_token

__all__ = ["AuthenticationError", "Token", "login", "save_token"]

_PROMPT_TEXT = (
    "After logging in, the code is in your browser (the address bar or the "
    "failed appie://login-exit?code=... URL). Paste it here, or just the code:"
)


def login() -> Token:
    """Run the browser OAuth login flow and store the resulting token.

    Opens the authorization URL in the user's default browser, prompts for the
    authorization code, exchanges it for tokens, and stores them at
    ``~/.config/happie/token``.

    Returns:
        The stored :class:`Token`.

    Raises:
        AuthenticationError: If the browser cannot be opened, no code is
            available, the exchange fails, or the response is malformed.
    """
    if not webbrowser.open(AUTHORIZATION_URL):
        raise AuthenticationError("Could not open a browser for the login page.")

    code = _prompt_for_code()
    access_token, refresh_token, expires_in = exchange_code(code)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    token = Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
    save_token(token)
    return token


def _prompt_for_code() -> str:
    """Prompt until the user supplies input that yields an authorization code.

    The raw input is never logged; a code-less URL or query string is reported
    and the user is prompted again.
    """
    while True:
        raw = typer.prompt(_PROMPT_TEXT)
        code = extract_code(raw)
        if code is not None:
            return code
        print("No authorization code found in that input; please try again.")
