"""HTTP client for the Albert Heijn product search endpoint.

Attaches the required application headers and the user's bearer token to
every request, and translates the search response into ``Product`` models.
"""

import httpx

from happie.albertheijn._models import Product, product_from_api
from happie.auth import get_access_token

__all__ = ["SEARCH_URL", "AlbertHeijnClient", "AlbertHeijnError"]

SEARCH_URL = "https://api.ah.nl/mobile-services/product/search/v2"

#: Application headers required by api.ah.nl, applied to every request.
_APP_HEADERS = {
    "User-Agent": "Appie/8.22.3",
    # The product search endpoint rejects requests without an application
    # context (500 "Can not find application"); `x-application` alone suffices.
    "x-application": "AHWEBSHOP",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class AlbertHeijnError(Exception):
    """Raised when the Albert Heijn product search endpoint fails.

    The message is safe to log: it never contains a token value.
    """


class AlbertHeijnClient:
    """Client for the Albert Heijn product search endpoint.

    The client takes no arguments and obtains its bearer token lazily at
    request time, so constructing it never touches the network or the token
    store.
    """

    def search_products(self, query: str, limit: int = 10) -> list[Product]:
        """Search the Albert Heijn assortment for ``query``.

        Args:
            query: The search term.
            limit: The maximum number of products to return, in the API's
                relevance order.

        Returns:
            The matching products, at most ``limit`` of them.

        Raises:
            AuthenticationError: If no usable stored token exists. No
                request is made in that case.
            AlbertHeijnError: If the endpoint returns a status other than
                200, or a 200 with an unexpected body.
        """
        token = get_access_token()
        http = httpx.Client()
        try:
            response = http.get(
                SEARCH_URL,
                params={
                    "query": query,
                    "page": "0",
                    "size": str(limit),
                    "sortOn": "RELEVANCE",
                },
                headers={**_APP_HEADERS, "Authorization": f"Bearer {token}"},
            )
        finally:
            http.close()

        if response.status_code != 200:
            raise AlbertHeijnError(
                f"Product search failed with status {response.status_code}."
            )
        try:
            products = response.json()["products"]
            # The API may return slightly more products than requested
            # (injected sponsored products); keep only the first ``limit``.
            return [product_from_api(product) for product in products][:limit]
        except (KeyError, TypeError, ValueError) as exc:
            raise AlbertHeijnError(
                "Product search returned an unexpected response."
            ) from exc
