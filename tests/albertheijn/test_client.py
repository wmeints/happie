"""Tests for the happie.albertheijn product search client."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from happie.albertheijn import AlbertHeijnClient, Product, PurchaseStat
from happie.albertheijn._client import SEARCH_URL
from happie.albertheijn._errors import AlbertHeijnError
from happie.auth import AuthenticationError


def _patch_transport(monkeypatch, handler) -> None:
    """Route every ``httpx.Client`` in the client module through ``handler``."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

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


# --- Purchase history ----------------------------------------------------


class PurchaseHistoryFake:
    """Canned responses for every purchase-history endpoint, with recording.

    Only one receipt page is supported: the same entries are returned for
    ``offset == 0`` and an empty page afterwards, which stops the client's
    pagination because all entries are expected to be inside the window.
    """

    def __init__(
        self,
        receipt_entries: list[dict] | None = None,
        receipt_details: dict[str, list] | None = None,
        conversion: dict[int, int | None] | None = None,
        summaries: list[dict] | None = None,
        order_details: dict[int, dict] | None = None,
        product_titles: dict[int, str] | None = None,
        fail_details_order: int | None = None,
    ):
        self.receipt_entries = receipt_entries or []
        self.receipt_details = receipt_details or {}
        self.conversion = conversion or {}
        self.summaries = summaries or []
        self.order_details = order_details or {}
        self.product_titles = product_titles or {}
        self.fail_details_order = fail_details_order
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/graphql":
            return self._graphql(request)
        if path == "/mobile-services/order/v1/summaries":
            return httpx.Response(200, json=self.summaries)
        match = re.fullmatch(
            r"/mobile-services/order/v1/(\d+)/details-grouped-by-taxonomy", path
        )
        if match:
            order_id = int(match.group(1))
            if self.fail_details_order == order_id:
                return httpx.Response(500)
            return httpx.Response(200, json=self.order_details.get(order_id, {}))
        if path == "/mobile-services/product/search/v2/products":
            ids = [
                int(value)
                for key, value in request.url.params.multi_items()
                if key == "ids"
            ]
            return httpx.Response(
                200,
                json=[
                    {"webshopId": product_id, "title": self.product_titles[product_id]}
                    for product_id in ids
                    if product_id in self.product_titles
                ],
            )
        raise AssertionError(f"unexpected request: {request.url}")

    def _graphql(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        query = body["query"]
        if "posReceiptsPage" in query:
            offset = body["variables"]["offset"]
            entries = self.receipt_entries if offset == 0 else []
            return httpx.Response(
                200, json={"data": {"posReceiptsPage": {"posReceipts": entries}}}
            )
        if "posReceiptDetails" in query:
            aliases = re.findall(r'(d\d+): posReceiptDetails\(id: "([^"]+)"\)', query)
            data = {
                alias: (
                    {"products": self.receipt_details[receipt_id]}
                    if receipt_id in self.receipt_details
                    else None
                )
                for alias, receipt_id in aliases
            }
            return httpx.Response(200, json={"data": data})
        if "productConvertId" in query:
            aliases = re.findall(r"(p\d+): productConvertId\(sourceId: (\d+)\)", query)
            data = {
                alias: self.conversion.get(int(pos_id)) for alias, pos_id in aliases
            }
            return httpx.Response(200, json={"data": data})
        raise AssertionError(f"unexpected query: {query}")


def _receipt_product(pos_id: int, quantity: int, name: str, amount: float) -> dict:
    return {
        "id": pos_id,
        "quantity": quantity,
        "name": name,
        "price": {"amount": amount / quantity},
        "amount": {"amount": amount},
    }


def _order_details(order_id: int, delivery_date: str, items: list[tuple]) -> dict:
    """Build a details payload from ``(webshop_id, title, quantity, price)``."""
    ordered = []
    for webshop_id, title, quantity, price in items:
        ordered.append(
            {
                "amount": 1,
                "quantity": quantity,
                "product": {
                    "webshopId": webshop_id,
                    "title": title,
                    "currentPrice": price,
                    "priceBeforeBonus": price,
                },
            }
        )
    return {
        "orderId": order_id,
        "deliveryDate": delivery_date,
        "orderState": "DELIVERED",
        "groupedProductsInTaxonomy": [
            {"taxonomyName": "Alles", "orderedProducts": ordered}
        ],
    }


def test_purchase_history_merges_receipt_and_order_records(monkeypatch) -> None:
    """Both sources flow into merged, quantity-sorted PurchaseStat results."""
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=89)
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    fake = PurchaseHistoryFake(
        receipt_entries=[
            {"id": "r1", "dateTime": f"{yesterday.isoformat()}T07:00:00.000Z"}
        ],
        receipt_details={
            "r1": [
                _receipt_product(624318, 2, "KAISERBROOD", 2.38),
                _receipt_product(999, 1, "NAPKINS", 0.5),
            ]
        },
        conversion={624318: 555, 999: None},
        summaries=[
            {
                "orderId": 42,
                "deliveryDate": two_days_ago.isoformat(),
                "state": "DELIVERED",
            }
        ],
        order_details={
            42: _order_details(
                42,
                two_days_ago.isoformat(),
                [
                    (555, "AH Kaiserbrood", 1, 1.19),
                    (777, "Melk", 4, 1.0),
                ],
            )
        },
        product_titles={555: "AH Kaiserbrood"},
    )
    _patch_transport(monkeypatch, fake.handler)
    _patch_token(monkeypatch)

    stats = AlbertHeijnClient().get_purchase_history(days=90)

    assert [stat.key for stat in stats] == ["wi777", "wi555", "pos999"]
    melted = stats[1]
    assert isinstance(melted, PurchaseStat)
    assert melted.key == "wi555"
    assert melted.name == "AH Kaiserbrood"
    assert melted.total_quantity == 3.0
    assert melted.purchase_days == 2
    assert melted.total_spend == 3.57
    assert melted.window_start == window_start
    assert len(melted.daily_counts) == 90
    yesterday_offset = (yesterday - window_start).days
    two_ago_offset = (two_days_ago - window_start).days
    assert melted.daily_counts[yesterday_offset] == 2.0
    assert melted.daily_counts[two_ago_offset] == 1.0
    assert sum(melted.daily_counts) == 3.0
    assert stats[0].total_quantity == 4.0
    assert stats[2].key == "pos999" and stats[2].name == "NAPKINS"
    # 2 receipt pages (in-window page plus the empty terminator) + 1 detail
    # batch + 1 conversion batch + 1 summary + 1 order details + 1 enrichment
    # request.
    assert len(fake.requests) == 7


def test_purchase_history_without_usable_token_makes_no_request(monkeypatch) -> None:
    """No token means no request: AuthenticationError propagates directly."""
    fake = PurchaseHistoryFake()
    _patch_transport(monkeypatch, fake.handler)

    def missing_token() -> str:
        raise AuthenticationError("No stored token. Run `happie auth login` first.")

    import happie.albertheijn._client as client_module

    monkeypatch.setattr(client_module, "get_access_token", missing_token)

    with pytest.raises(AuthenticationError):
        AlbertHeijnClient().get_purchase_history()
    assert fake.requests == []


def test_purchase_history_failed_details_request_fails_the_call(monkeypatch) -> None:
    """One failed sub-request raises; no partial result is returned."""
    fake = PurchaseHistoryFake(
        summaries=[{"orderId": 7, "deliveryDate": "2026-08-10", "state": "DELIVERED"}],
        fail_details_order=7,
    )
    _patch_transport(monkeypatch, fake.handler)
    _patch_token(monkeypatch)

    with pytest.raises(AlbertHeijnError) as excinfo:
        AlbertHeijnClient().get_purchase_history()

    assert "500" in str(excinfo.value)
    assert "7" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_purchase_history_empty_window_returns_empty_list(monkeypatch) -> None:
    """No in-window receipts or orders yield an empty list, not an error."""
    today = datetime.now(UTC).date()
    fake = PurchaseHistoryFake(
        receipt_entries=[],
        summaries=[
            {
                "orderId": 7,
                "deliveryDate": (today - timedelta(days=400)).isoformat(),
                "state": "DELIVERED",
            }
        ],
    )
    _patch_transport(monkeypatch, fake.handler)
    _patch_token(monkeypatch)

    assert AlbertHeijnClient().get_purchase_history() == []
    # One receipt page and the summaries; no details or enrichment requests.
    assert len(fake.requests) == 2
