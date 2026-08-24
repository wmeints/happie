"""Command-line interface for happie.

Exposes the typer application (``app``) and its command tree, plus the
``configure_logging`` helper used to prepare terminal logging before the
commands run.

``auth login`` performs the browser OAuth flow (installs the ``appie://``
protocol handler, opens the authorization page, and waits for the token
file to be updated); ``auth complete`` exchanges the authorization code and
stores the token; ``serve`` runs the MCP server on stdio. ``auth logout``
is still a logging stand-in that arrives in a later change.
"""

import logging
import sys

import typer

from happie import auth, server
from happie.auth import AuthenticationError

__all__ = ["app", "auth_app", "configure_logging"]

_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(message)s]"

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="happie - Albert Heijn MCP server.",
    no_args_is_help=True,
)

auth_app = typer.Typer(
    help="Manage authentication to the Albert Heijn API.",
    no_args_is_help=True,
)


def configure_logging() -> None:
    """Install a StreamHandler on the root logger that writes to stderr.

    The handler uses the formatter ``[%(asctime)s] [%(levelname)s]
    [%(message)s]`` so log lines read as ``[timestamp] [level]
    [message]``. The root logger level is set to ``INFO``. Existing root
    handlers are replaced so the configured stream and format always win,
    regardless of handlers installed earlier by other code.
    """
    logging.basicConfig(
        level=logging.INFO,
        format=_LOG_FORMAT,
        stream=sys.stderr,
        force=True,
    )


@auth_app.command()
def login() -> None:
    """Authenticate via the browser to obtain an access token."""
    try:
        auth.login()
    except AuthenticationError as exc:
        logger.error(
            "Authentication failed: %s Run `happie auth login` again to "
            "obtain a token.",
            exc,
        )
        raise typer.Exit(code=1) from exc


@auth_app.command()
def logout() -> None:
    """Remove the stored access token."""
    logger.info("Would remove the stored access token (not yet implemented).")


@auth_app.command()
def complete(raw: str | None = typer.Argument(None)) -> None:
    """Complete the browser login by exchanging the authorization code."""
    try:
        auth.complete(raw)
    except AuthenticationError as exc:
        logger.error(
            "Authentication failed: %s Run `happie auth login` again to "
            "obtain a token.",
            exc,
        )
        raise typer.Exit(code=1) from exc
    logger.info("Stored Albert Heijn access token.")


@app.command()
def serve() -> None:
    """Run the MCP server on stdio."""
    server.serve()


app.add_typer(auth_app, name="auth")
