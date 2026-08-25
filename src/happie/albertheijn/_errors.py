"""Errors raised by the Albert Heijn API client.

Holds :class:`AlbertHeijnError`, the single failure type every client
endpoint reports. Kept in its own module so the private endpoint submodules
can raise it without importing from the orchestrating client.
"""

__all__ = ["AlbertHeijnError"]


class AlbertHeijnError(Exception):
    """Raised when an Albert Heijn endpoint fails.

    The message is safe to log: it never contains a token value.
    """
