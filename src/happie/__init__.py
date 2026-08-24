"""happie: Albert Heijn grocery MCP server."""

from happie.cli import app, configure_logging

__all__ = ["main"]


def main() -> None:
    """Entry point for the ``happie`` console script.

    Configures terminal logging, then runs the typer CLI application.
    """
    configure_logging()
    app()
