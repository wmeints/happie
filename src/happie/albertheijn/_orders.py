"""REST fetch of delivered webshop order purchase history.

Fetches the order summaries, keeps only the delivered orders whose delivery
date falls inside the requested window, and expands each of them into line
items via the per-order details endpoint.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from happie.albertheijn._errors import AlbertHeijnError

__all__ = [
    "ORDER_DETAILS_URL",
    "ORDER_SUMMARIES_URL",
    "OrderItem",
    "fetch_order_history",
]

ORDER_SUMMARIES_URL = "https://api.ah.nl/mobile-services/order/v1/summaries"
ORDER_DETAILS_URL = (
    "https://api.ah.nl/mobile-services/order/v1/{order_id}/details-grouped-by-taxonomy"
)


@dataclass(frozen=True)
class OrderItem:
    """One delivered webshop order line item.

    Attributes
    ----------
        date: The delivery day of the order.
        webshop_id: The webshop product id.
        name: The product title.
        quantity: The ordered quantity.
        amount: The amount spent on the line (quantity times price).
    """

    date: date
    webshop_id: int
    name: str
    quantity: float
    amount: float


def fetch_order_history(
    http: httpx.Client, window_start: date, days: int
) -> list[OrderItem]:
    """Fetch the line items of delivered webshop orders inside the window.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        window_start: The first calendar day to include.
        days: The length of the window in days.

    Returns
    -------
        The line items of all delivered orders delivered on a day in
        ``[window_start, window_start + days - 1]``, in summary order.
        Cancelled and still-open orders contribute nothing.

    Raises
    ------
        AlbertHeijnError: If the summaries or any order-details request
            returns a status other than 200 or an unexpected body.
    """
    summaries = _fetch_summaries(http)
    window_end = window_start + timedelta(days=days - 1)
    items: list[OrderItem] = []
    for summary in summaries:
        delivery_date = _window_delivery_day(summary, window_start, window_end)
        if delivery_date is None:
            continue
        order_id = int(summary["orderId"])
        items.extend(_order_items(http, order_id, delivery_date))
    return items


def _fetch_summaries(http: httpx.Client) -> list:
    """Fetch the raw order summaries, validating status and body shape."""
    response = http.get(ORDER_SUMMARIES_URL, params={"sortBy": "DEFAULT"})
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Order summaries failed with status {response.status_code}."
        )
    try:
        summaries = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(
            "Order summaries returned an unexpected response."
        ) from exc
    if not isinstance(summaries, list):
        raise AlbertHeijnError("Order summaries returned an unexpected response.")
    return summaries


def _window_delivery_day(
    summary: dict, window_start: date, window_end: date
) -> date | None:
    """Return the delivery day for a delivered in-window summary, else None."""
    if not isinstance(summary, dict) or summary.get("state") != "DELIVERED":
        return None
    delivery_date = _summary_day(summary)
    if not window_start <= delivery_date <= window_end:
        return None
    return delivery_date


def _summary_day(summary: dict) -> date:
    """Extract the delivery day from an order summary entry."""
    try:
        return date.fromisoformat(str(summary["deliveryDate"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(
            "Order summaries returned an unexpected response."
        ) from exc


def _order_items(
    http: httpx.Client, order_id: int, delivery_date: date
) -> list[OrderItem]:
    """Fetch and translate one order's line items."""
    body = _fetch_details(http, order_id)
    items: list[OrderItem] = []
    for ordered in _ordered_products(body):
        items.append(_order_item(order_id, delivery_date, ordered))
    return items


def _fetch_details(http: httpx.Client, order_id: int) -> dict:
    """Fetch one order's details, validating status and body shape."""
    response = http.get(ORDER_DETAILS_URL.format(order_id=order_id))
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Order details for order {order_id} failed with status {response.status_code}."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(
            f"Order details for order {order_id} returned an unexpected response."
        ) from exc
    if not isinstance(body, dict) or not isinstance(
        body.get("groupedProductsInTaxonomy"), list
    ):
        raise AlbertHeijnError(
            f"Order details for order {order_id} returned an unexpected response."
        )
    return body


def _ordered_products(body: dict) -> list[dict]:
    """Flatten the taxonomy groups into their ordered product entries."""
    products: list[dict] = []
    for group in body["groupedProductsInTaxonomy"]:
        if not isinstance(group, dict):
            continue
        for ordered in group.get("orderedProducts") or []:
            if isinstance(ordered, dict):
                products.append(ordered)
    return products


def _order_item(order_id: int, delivery_date: date, ordered: dict) -> OrderItem:
    """Translate one ordered product entry into an :class:`OrderItem`."""
    try:
        product = ordered["product"]
        quantity = float(ordered.get("quantity") or 0.0)
        price = float(
            product.get("currentPrice") or product.get("priceBeforeBonus") or 0.0
        )
        return OrderItem(
            date=delivery_date,
            webshop_id=int(product["webshopId"]),
            name=str(product.get("title") or ""),
            quantity=quantity,
            amount=quantity * price,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(
            f"Order details for order {order_id} returned an unexpected response."
        ) from exc
