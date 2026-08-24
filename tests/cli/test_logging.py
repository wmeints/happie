"""Tests for the happie.cli logging configuration."""

import logging
import re

from happie.cli import configure_logging

LOG_LINE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?\] \[INFO\] \[logged from happie test\]$"
)


def test_configure_logging_writes_formatted_message_to_stderr(capsys) -> None:
    """configure_logging logs INFO messages to stderr in [ts] [level] [msg] form."""
    configure_logging()
    logging.getLogger("happie.test").info("logged from happie test")

    err = capsys.readouterr().err
    assert LOG_LINE.match(err.strip()), (
        f"stderr did not match expected log format: {err!r}"
    )
