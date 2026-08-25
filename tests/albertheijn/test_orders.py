"""Tests for the webshop order (REST) purchase-history fetch."""

from datetime import date

import httpx
import pytest

from happie.albertheijn._client import _APP_HEADERS
from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._orders import (
    ORDER_DETAILS_URL,
    ORDER_SUMMARIES_URL,
    fetch_order_history,
)

AUTHORIZATION = "Bearer access-secret"


def _patch_transport(monkeypatch, handler) -> None:
    """Route every ``httpx.Client`` through ``handler``."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def _client(monkeypatch, handler) -> httpx.Client:
    """A preconfigured client like the orchestrator builds."""
    _patch_transport(monkeypatch, handler)
    return httpx.Client(headers={**_APP_HEADERS, "Authorization": AUTHORIZATION})


def _summary(order_id: int, delivery_date: str, state: str = "DELIVERED") -> dict:
    return {"orderId": order_id, "deliveryDate": delivery_date, "state": state}


def _ordered_product(
    webshop_id: int,
    title: str,
    quantity: int = 1,
    current_price: float | None = 0.0,
    price_before_bonus: float = 1.0,
) -> dict:
    product = {
        "webshopId": webshop_id,
        "title": title,
        "priceBeforeBonus": price_before_bonus,
    }
    if current_price is not None:
        product["currentPrice"] = current_price
    return {"amount": 1, "quantity": quantity, "product": product}


def _details(order_id: int, ordered_products: list[dict]) -> dict:
    return {
        "orderId": order_id,
        "deliveryDate": "2026-08-10",
        "orderState": "DELIVERED",
        "groupedProductsInTaxonomy": [
            {"taxonomyName": "Bakkerij", "orderedProducts": ordered_products}
        ],
    }


def test_orders_fetches_delivered_in_window_orders_only(monkeypatch) -> None:
    """Only DELIVERED orders inside the window are expanded; headers are pinned."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/mobile-services/order/v1/summaries":
            assert dict(request.url.params) == {"sortBy": "DEFAULT"}
            assert request.headers["User-Agent"] == "Appie/8.22.3"
            assert request.headers["x-application"] == "AHWEBSHOP"
            assert request.headers["Authorization"] == AUTHORIZATION
            return httpx.Response(
                200,
                json=[
                    _summary(1, "2026-08-10"),
                    _summary(2, "2026-08-11", state="CANCELLED"),
                    _summary(3, "2026-08-12", state="CONFIRMED"),
                    _summary(4, "2026-01-01"),  # outside the window
                ],
            )
        if str(request.url) == ORDER_DETAILS_URL.format(order_id=1):
            return httpx.Response(
                200,
                json=_details(
                    1,
                    [
                        _ordered_product(
                            4183, "AH Bloemkool", quantity=2, current_price=1.89
                        ),
                        _ordered_product(
                            186043, "AH Biologisch Bleekselderij", current_price=None
                        ),
                    ],
                ),
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(monkeypatch, handler)

    items = fetch_order_history(client, window_start=date(2026, 8, 1), days=30)

    assert [item.webshop_id for item in items] == [4183, 186043]
    assert items[0].date == date(2026, 8, 10)
    assert items[0].name == "AH Bloemkool"
    # quantity x current price
    assert items[0].quantity == 2.0
    assert items[0].amount == 3.78
    # no currentPrice -> priceBeforeBonus
    assert items[1].quantity == 1.0
    assert items[1].amount == 1.0
    # Exactly the summaries request and the one in-window order's details.
    assert len(seen) == 2
    assert str(seen[0].url) == f"{ORDER_SUMMARIES_URL}?sortBy=DEFAULT"


def test_orders_returns_empty_list_when_nothing_in_window(monkeypatch) -> None:
    """No delivered in-window order means no details requests at all."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                _summary(1, "2026-01-01"),
                _summary(2, "2026-08-01", state="CANCELLED"),
            ],
        )

    client = _client(monkeypatch, handler)

    assert fetch_order_history(client, window_start=date(2026, 8, 1), days=30) == []
    assert len(seen) == 1


def test_orders_summaries_http_error_raises_with_status(monkeypatch) -> None:
    """A non-200 on the summaries raises AlbertHeijnError with the status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_order_history(client, window_start=date(2026, 8, 1), days=30)

    assert "500" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_orders_details_http_error_raises_with_order_and_status(monkeypatch) -> None:
    """A failed detail request fails the whole call, naming the order."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/mobile-services/order/v1/summaries":
            return httpx.Response(200, json=[_summary(7, "2026-08-10")])
        return httpx.Response(404)

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_order_history(client, window_start=date(2026, 8, 1), days=30)

    assert "404" in str(excinfo.value)
    assert "7" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_orders_unexpected_summaries_body_raises(monkeypatch) -> None:
    """A 200 body that is not a list raises AlbertHeijnError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError):
        fetch_order_history(client, window_start=date(2026, 8, 1), days=30)


def test_orders_unexpected_details_body_raises(monkeypatch) -> None:
    """Details without groupedProductsInTaxonomy raise AlbertHeijnError."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/mobile-services/order/v1/summaries":
            return httpx.Response(200, json=[_summary(7, "2026-08-10")])
        return httpx.Response(200, json={"orderId": 7, "deliveryDate": "2026-08-10"})

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError):
        fetch_order_history(client, window_start=date(2026, 8, 1), days=30)
