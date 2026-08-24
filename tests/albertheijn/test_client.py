"""Tests for the happie.albertheijn product search client."""

import logging

import httpx
import pytest

from happie.albertheijn import AlbertHeijnClient, Product
from happie.albertheijn._client import SEARCH_URL, AlbertHeijnError
from happie.auth import AuthenticationError


def _patch_transport(monkeypatch, handler) -> None:
    """Route every ``httpx.Client`` in the client module through ``handler``."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", factory)


def _patch_token(monkeypatch, token: str = "access-secret") -> None:
    """Make the client's lazy token lookup return ``token``."""
    import happie.albertheijn._client as client_module

    monkeypatch.setattr(client_module, "get_access_token", lambda: token)


def _payload(products: list[dict]) -> dict:
    return {"products": products, "page": {"number": 0, "totalElements": len(products)}}


def _bonus_product(**overrides) -> dict:
    data = {
        "webshopId": 87654321,
        "title": "Bramatur kaas",
        "brand": "AH",
        "salesUnitSize": "250 g",
        "unitPriceDescription": "per 100 g",
        "currentPrice": 1.49,
        "priceBeforeBonus": 2.99,
        "isBonus": True,
        "bonusMechanism": "2e halve prijs",
        "mainCategory": "Kaas",
        "availableOnline": True,
    }
    data.update(overrides)
    return data


def test_search_sends_expected_request_and_parses_products(monkeypatch) -> None:
    """The search hits the v2 endpoint with pinned params/headers and parses."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json=_payload(
                [
                    _bonus_product(),
                    _bonus_product(
                        webshopId=111,
                        title="Melk",
                        currentPrice=1.19,
                        priceBeforeBonus=1.19,
                        isBonus=False,
                        bonusMechanism="",
                    ),
                ]
            ),
        )

    _patch_transport(monkeypatch, handler)
    _patch_token(monkeypatch)

    products = AlbertHeijnClient().search_products("melk", limit=5)

    request = seen["request"]
    assert request.method == "GET"
    assert str(request.url).startswith(SEARCH_URL)
    assert dict(request.url.params) == {
        "query": "melk",
        "page": "0",
        "size": "5",
        "sortOn": "RELEVANCE",
    }
    assert request.headers["User-Agent"] == "Appie/8.22.3"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["x-application"] == "AHWEBSHOP"
    assert request.headers["Authorization"] == "Bearer access-secret"

    assert len(products) == 2
    bonus, plain = products
    assert isinstance(bonus, Product)
    assert bonus.webshop_id == 87654321
    assert bonus.title == "Bramatur kaas"
    assert bonus.brand == "AH"
    assert bonus.price == 1.49
    assert bonus.price_before_bonus == 2.99
    assert bonus.is_bonus is True
    assert bonus.bonus_mechanism == "2e halve prijs"
    assert bonus.sales_unit_size == "250 g"
    assert bonus.unit_price_description == "per 100 g"
    assert bonus.available_online is True
    assert bonus.main_category == "Kaas"
    assert plain.is_bonus is False
    assert plain.price == plain.price_before_bonus == 1.19


def test_search_translates_null_optional_fields(monkeypatch) -> None:
    """Optional API fields that come back null become empty, not ``'None'``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_payload(
                [
                    _bonus_product(
                        webshopId=441199,
                        title="Campina Halfvolle melk voordeelverpakking",
                        brand="Campina",
                        currentPrice=None,
                        priceBeforeBonus=1.89,
                        isBonus=False,
                        bonusMechanism=None,
                        salesUnitSize=None,
                        unitPriceDescription=None,
                        mainCategory=None,
                        availableOnline=None,
                    )
                ]
            ),
        )

    _patch_transport(monkeypatch, handler)
    _patch_token(monkeypatch)

    (product,) = AlbertHeijnClient().search_products("melk")
    assert product.price == product.price_before_bonus == 1.89
    assert product.bonus_mechanism == ""
    assert product.sales_unit_size == ""
    assert product.unit_price_description == ""
    assert product.main_category == ""
    assert product.available_online is False


def test_search_returns_at_most_limit_products_in_api_order(monkeypatch) -> None:
    """When the API returns more than requested, only the first ``limit`` pass."""
    handler = lambda request: httpx.Response(
        200,
        json=_payload([_bonus_product(webshopId=i) for i in range(8)]),
    )
    _patch_transport(monkeypatch, handler)
    _patch_token(monkeypatch)

    products = AlbertHeijnClient().search_products("melk", limit=5)
    assert [product.webshop_id for product in products] == list(range(8))[:5]


def test_search_returns_empty_list_when_no_matches(monkeypatch) -> None:
    """A response with no products yields an empty list."""
    _patch_transport(
        monkeypatch, lambda request: httpx.Response(200, json=_payload([]))
    )
    _patch_token(monkeypatch)
    assert AlbertHeijnClient().search_products("zzzznotthere") == []


def test_search_http_error_raises_with_status(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A non-200 raises with the status; no token value appears in logs."""
    caplog.set_level(logging.DEBUG)
    _patch_transport(
        monkeypatch,
        lambda request: httpx.Response(500, json={"error": "boom"}),
    )
    _patch_token(monkeypatch)

    with pytest.raises(AlbertHeijnError, match="500"):
        AlbertHeijnClient().search_products("melk")

    assert "access-secret" not in caplog.text


def test_search_without_usable_token_makes_no_request(monkeypatch) -> None:
    """No token means no request: AuthenticationError propagates directly."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_payload([]))

    _patch_transport(monkeypatch, handler)

    def missing_token() -> str:
        raise AuthenticationError("No stored token. Run `happie auth login` first.")

    import happie.albertheijn._client as client_module

    monkeypatch.setattr(client_module, "get_access_token", missing_token)

    with pytest.raises(AuthenticationError):
        AlbertHeijnClient().search_products("melk")
    assert calls == []
