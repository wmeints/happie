"""HTTP client for the Albert Heijn product search and purchase-history APIs.

Attaches the required application headers and the user's bearer token to
every request. The product search endpoint is wrapped directly here; the
purchase-history endpoints live in the ``_receipts``, ``_orders``, and
``_history`` submodules, orchestrated by :meth:`AlbertHeijnClient.get_purchase_history`.
"""

from datetime import UTC, datetime, timedelta

import httpx

from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._history import PurchaseRecord, aggregate
from happie.albertheijn._models import Product, PurchaseStat, product_from_api
from happie.albertheijn._orders import fetch_order_history
from happie.albertheijn._receipts import enrich_product_names, fetch_receipt_history
from happie.auth import get_access_token

__all__ = ["SEARCH_URL", "AlbertHeijnClient"]

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


class AlbertHeijnClient:
    """Client for the Albert Heijn product search endpoint.

    The client takes no arguments and obtains its bearer token lazily at
    request time, so constructing it never touches the network or the token
    store.
    """

    def get_purchase_history(self, days: int = 90) -> list[PurchaseStat]:
        """Summarise the user's purchases over the last ``days`` days.

        Merges in-store receipt items and delivered webshop order items
        into one statistic per product, with a dense per-day purchase
        quantity covering the whole window. Products bought in-store and
        online under the same webshop id merge into one statistic; receipt
        items without a webshop conversion stay separate under their
        point-of-sale id.

        Args:
            days: The length of the window in days, ending today.

        Returns:
            One :class:`PurchaseStat` per purchased product, sorted by
            total quantity descending.

        Raises:
            AuthenticationError: If no usable stored token exists. No
                request is made in that case.
            AlbertHeijnError: If any purchase-history request fails. No
                partial result is returned.
        """
        token = get_access_token()
        window_start = datetime.now(UTC).date() - timedelta(days=days - 1)
        http = httpx.Client(
            headers={**_APP_HEADERS, "Authorization": f"Bearer {token}"}
        )
        try:
            receipt_items, conversion = fetch_receipt_history(http, window_start)
            order_items = fetch_order_history(http, window_start, days)
            converted_ids = sorted(set(conversion.values()))
            titles = enrich_product_names(http, converted_ids) if converted_ids else {}
            records = [
                PurchaseRecord(
                    day=item.date,
                    key=(
                        f"wi{conversion[item.pos_id]}"
                        if item.pos_id in conversion
                        else f"pos{item.pos_id}"
                    ),
                    name=titles.get(conversion.get(item.pos_id), item.name),
                    quantity=item.quantity,
                    amount=item.amount,
                )
                for item in receipt_items
            ]
            records.extend(
                PurchaseRecord(
                    day=item.date,
                    key=f"wi{item.webshop_id}",
                    name=item.name,
                    quantity=item.quantity,
                    amount=item.amount,
                )
                for item in order_items
            )
            return aggregate(records, window_start, days)
        finally:
            http.close()

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
