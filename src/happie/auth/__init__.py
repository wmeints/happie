"""Browser-based OAuth login for the Albert Heijn API.

``login()`` installs the ``appie://`` protocol handler, opens the
authorization page, and waits for the token file to hold a fresh token.
``complete()`` accepts the authorization code (argument or terminal
prompt), exchanges it for tokens, and stores them. ``get_access_token()``
returns a usable access token, refreshing the stored pair on expiry. Code
parsing and the token exchange live in a private submodule; the token
store and the handler installation are separate private modules, so each
seam is unit-testable without a browser or network.
"""

import time
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from happie.auth._flow import (
    AUTHORIZATION_URL,
    AuthenticationError,
    exchange_code,
    extract_code,
)
from happie.auth._handler import ensure_handler
from happie.auth._store import (
    DEFAULT_TOKEN_PATH,
    Token,
    load_token,
    save_token,
)
from happie.auth._token import get_access_token

__all__ = [
    "AuthenticationError",
    "Token",
    "complete",
    "ensure_handler",
    "get_access_token",
    "login",
    "save_token",
]

#: How long ``login`` waits for a fresh token; codes are single-use and
#: short-lived, so the user reruns the login on timeout.
_WATCH_TIMEOUT = timedelta(minutes=5)
#: Poll interval for the token-file watch.
_POLL_INTERVAL = 0.01
#: Tolerance when judging a stored token's expiry as "in the future".
_FRESHNESS_GRACE = timedelta(seconds=30)

_PROMPT_TEXT = (
    "Paste the authorization code here, or the full "
    "appie://login-exit?code=... URL or ?code=... query string:"
)


def login() -> None:
    """Run the browser OAuth login flow.

    Installs the ``appie://`` protocol handler, snapshots the token file,
    opens the authorization URL in the user's default browser, and waits
    for the code-completion entrypoint to store a fresh token (invoked
    by the desktop environment when the browser redirects to
    ``appie://login-exit``). The flow never prompts for the code.

    Raises
    ------
    AuthenticationError
        If the handler cannot be installed, the browser cannot be
        opened, or no fresh token is stored within five minutes.
    """
    ensure_handler()
    initial_state = _token_file_state(DEFAULT_TOKEN_PATH)
    if not webbrowser.open(AUTHORIZATION_URL):
        raise AuthenticationError("Could not open a browser for the login page.")
    _wait_for_token(initial_state)


def complete(raw: str | None = None) -> Token:
    """Complete the browser login by exchanging an authorization code.

    When ``raw`` is given (bare code, full ``appie://`` deep-link URL, or
    query string) it is used directly; when it is omitted the user is
    prompted until the input yields a code. The exchanged token is
    stored at ``~/.config/happie/token``.

    Parameters
    ----------
    raw : str | None
        The deep-link URL, query string, or bare code; ``None`` prompts
        on the terminal.

    Returns
    -------
    Token
        The stored :class:`Token`.

    Raises
    ------
    AuthenticationError
        If no code can be extracted from ``raw`` or the exchange fails.
        The message never contains the code or any token value.
    """
    if raw is None:
        code = _prompt_for_code()
    else:
        code = extract_code(raw)
        if code is None:
            raise AuthenticationError(
                "No authorization code found in the supplied input."
            )

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
    """Prompt until the input yields an authorization code.

    The raw input is never logged; a code-less URL or query string is
    reported and the user is prompted again.
    """
    while True:
        raw = typer.prompt(_PROMPT_TEXT)
        code = extract_code(raw)
        if code is not None:
            return code
        print("No authorization code found in that input; please try again.")


def _token_file_state(path: Path) -> tuple[int, int] | None:
    """Return the token file's ``(st_ino, st_mtime_ns)``, or ``None``."""
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return None
    return (stat_result.st_ino, stat_result.st_mtime_ns)


def _token_file_is_fresh(path: Path) -> bool:
    """Return True when the file holds a parseable unexpired token."""
    token = load_token(path)
    if token is None:
        return False
    return token.expires_at > datetime.now(UTC) - _FRESHNESS_GRACE


def _wait_for_token(initial_state: tuple[int, int] | None) -> None:
    """Block until the token file changes to hold a fresh stored token.

    Polls ``DEFAULT_TOKEN_PATH`` every 10 ms; a change counts as success
    only when the new content parses as stored-token JSON whose
    ``expires_at`` is in the future. Any other update (stale expiry,
    malformed JSON) keeps the wait going. A token written later by other
    tooling (e.g. a future token refresh) also ends the wait with a
    usable token — accepted trade-off.

    Parameters
    ----------
    initial_state : tuple[int, int] | None
        The ``(st_ino, st_mtime_ns)`` snapshot taken before the browser
        was opened, or ``None`` when the file was absent.

    Raises
    ------
    AuthenticationError
        If no valid change occurs within the timeout.
    """
    deadline = time.monotonic() + _WATCH_TIMEOUT.total_seconds()
    while time.monotonic() < deadline:
        state = _token_file_state(DEFAULT_TOKEN_PATH)
        if state != initial_state and _token_file_is_fresh(DEFAULT_TOKEN_PATH):
            return
        time.sleep(_POLL_INTERVAL)
    raise AuthenticationError(
        "Login timed out: no fresh token was stored within five minutes."
    )
