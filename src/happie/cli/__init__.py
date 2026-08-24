"""Command-line interface for happie.

Exposes the typer application (``app``) and its command tree, plus the
``configure_logging`` helper used to prepare terminal logging before the
commands run.

Commands are currently logging stand-ins: each one reports, at ``INFO``,
what it would do. Real authentication and MCP server behavior arrive in
later changes.
"""

import logging
import sys

import typer

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
    logger.info(
        "Would authenticate the user via the browser to obtain an access token "
        "(not yet implemented)."
    )


@auth_app.command()
def logout() -> None:
    """Remove the stored access token."""
    logger.info("Would remove the stored access token (not yet implemented).")


@app.command()
def serve() -> None:
    """Run the MCP server."""
    logger.info("Would start the MCP server (not yet implemented).")


app.add_typer(auth_app, name="auth")
