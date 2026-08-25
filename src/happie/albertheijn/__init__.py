"""Client for the Albert Heijn product search and purchase-history APIs.

Exposes :class:`AlbertHeijnClient`, which attaches the required application
headers and the user's bearer token to every request, the
:class:`Product` and :class:`PurchaseStat` models it returns, and
:class:`AlbertHeijnError` for endpoint failures. The endpoint details and
the raw-response parsing live in private submodules so each seam is
unit-testable without a network.
"""

from happie.albertheijn._client import AlbertHeijnClient
from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._models import Product, PurchaseStat

__all__ = ["AlbertHeijnClient", "AlbertHeijnError", "Product", "PurchaseStat"]
