"""Tests for the in-store receipt (GraphQL) purchase-history fetch."""

import json
import re
from datetime import date

import httpx
import pytest

from happie.albertheijn._client import _APP_HEADERS
from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._receipts import (
    GRAPHQL_URL,
    enrich_product_names,
    fetch_receipt_history,
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


class GraphQLRecorder:
    """Canned GraphQL responses with request recording."""

    def __init__(
        self,
        pages: dict[int, list] | None = None,
        details: dict[str, list] | None = None,
        conversion=None,
    ):
        self.pages = pages or {}
        self.details = details or {}
        self.conversion = (
            conversion if conversion is not None else (lambda pos_id: pos_id + 100000)
        )
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.errors = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        canned = self._canned_error()
        if canned is not None:
            return canned
        body = json.loads(request.content)
        query = body["query"]
        if "posReceiptsPage" in query:
            return self._page(body)
        if "posReceiptDetails" in query:
            return self._details(query)
        if "productConvertId" in query:
            return self._convert(query)
        raise AssertionError(f"unexpected query: {query}")

    def _canned_error(self) -> httpx.Response | None:
        """Response forced by the ``status``/``errors`` flags, else ``None``."""
        if self.status != 200:
            return httpx.Response(self.status)
        if self.errors:
            return httpx.Response(200, json={"errors": [{"message": "boom"}]})
        return None

    def _page(self, body: dict) -> httpx.Response:
        """Canned receipt page for the request's offset."""
        offset = body["variables"]["offset"]
        return httpx.Response(
            200,
            json={
                "data": {"posReceiptsPage": {"posReceipts": self.pages.get(offset, [])}}
            },
        )

    def _details(self, query: str) -> httpx.Response:
        """Canned per-alias receipt details (null for unknown ids)."""
        aliases = re.findall(r'(d\d+): posReceiptDetails\(id: "([^"]+)"\)', query)
        data = {
            alias: (
                {"products": self.details[receipt_id]}
                if receipt_id in self.details
                else None
            )
            for alias, receipt_id in aliases
        }
        return httpx.Response(200, json={"data": data})

    def _convert(self, query: str) -> httpx.Response:
        """Canned pos-id to webshop-id conversions."""
        aliases = re.findall(r"(p\d+): productConvertId\(sourceId: (\d+)\)", query)
        data = {alias: self.conversion(int(pos_id)) for alias, pos_id in aliases}
        return httpx.Response(200, json={"data": data})


def _receipt(receipt_id: str, day: str, amount: float = 10.0) -> dict:
    return {
        "id": receipt_id,
        "dateTime": f"{day}T07:00:00.000Z",
        "totalAmount": {"amount": amount},
    }


def _product(
    pos_id: int, quantity: int = 1, name: str = "NAPKINS", amount: float = 1.0
) -> dict:
    return {
        "id": pos_id,
        "quantity": quantity,
        "name": name,
        "price": {"amount": amount / quantity} if quantity else None,
        "amount": {"amount": amount},
    }


def test_receipt_fetch_covers_window_and_parses_items(monkeypatch) -> None:
    """Receipts page until the window is covered; items and ids are parsed."""
    recorder = GraphQLRecorder(
        pages={
            0: [_receipt("r1", "2026-08-20"), _receipt("r2", "2026-08-19")],
            100: [_receipt("r3", "2026-08-18")],  # still inside the window
            200: [_receipt("r4", "2026-07-01")],  # oldest entry predates the window
        },
        details={
            "r1": [_product(624318, quantity=2, name="KAISERBROOD", amount=2.38)],
            "r2": [_product(20147, quantity=1, name="WORSTEN BR", amount=1.29)],
            "r3": [_product(539971, quantity=1, name="SLAGROOMSOES", amount=3.49)],
        },
    )
    client = _client(monkeypatch, recorder.handler)

    items, conversion = fetch_receipt_history(client, window_start=date(2026, 8, 15))

    assert [item.date for item in items] == [
        date(2026, 8, 20),
        date(2026, 8, 19),
        date(2026, 8, 18),
    ]
    assert [item.pos_id for item in items] == [624318, 20147, 539971]
    assert items[0].quantity == 2.0
    assert items[0].name == "KAISERBROOD"
    assert items[0].amount == 2.38
    assert conversion == {624318: 724318, 20147: 120147, 539971: 639971}
    # Two pages fetched before the oldest entry left the window; r4 was never
    # requested in the detail or conversion batches.
    page_requests = [
        request
        for request in recorder.requests
        if "posReceiptsPage" in json.loads(request.content)["query"]
    ]
    assert [
        json.loads(request.content)["variables"]["offset"] for request in page_requests
    ] == [0, 100, 200]
    assert len(recorder.requests) == 3 + 1 + 1

    first = recorder.requests[0]
    assert first.method == "POST"
    assert str(first.url) == GRAPHQL_URL
    assert first.headers["User-Agent"] == "Appie/8.22.3"
    assert first.headers["x-application"] == "AHWEBSHOP"
    assert first.headers["Authorization"] == AUTHORIZATION


def test_receipt_fetch_stops_on_empty_page(monkeypatch) -> None:
    """An empty first page ends the fetch with a single request."""
    recorder = GraphQLRecorder(pages={0: []})
    client = _client(monkeypatch, recorder.handler)

    items, conversion = fetch_receipt_history(client, window_start=date(2026, 8, 15))

    assert items == []
    assert conversion == {}
    assert len(recorder.requests) == 1


def test_receipt_details_are_fetched_in_aliased_batches_of_fifty(monkeypatch) -> None:
    """Sixty in-window receipts yield two detail requests: 50 aliases, then 10."""
    pages = {0: [_receipt(f"r{i}", "2026-08-10") for i in range(60)]}
    details = {f"r{i}": [_product(1000 + i)] for i in range(60)}
    recorder = GraphQLRecorder(pages=pages, details=details)
    client = _client(monkeypatch, recorder.handler)

    items, conversion = fetch_receipt_history(client, window_start=date(2026, 8, 1))

    detail_queries = [
        json.loads(request.content)["query"]
        for request in recorder.requests
        if "posReceiptDetails" in json.loads(request.content)["query"]
    ]
    assert len(detail_queries) == 2
    assert len(re.findall(r"d\d+: posReceiptDetails\(", detail_queries[0])) == 50
    assert len(re.findall(r"d\d+: posReceiptDetails\(", detail_queries[1])) == 10
    assert len(items) == 60
    assert len(conversion) == 60


def test_receipt_pos_ids_are_converted_in_aliased_batches_of_one_hundred(
    monkeypatch,
) -> None:
    """150 unique POS ids yield two conversion requests: 100 aliases, then 50."""
    pages = {
        0: [_receipt(f"r{i}", "2026-08-10") for i in range(100)],
        100: [_receipt(f"r{i}", "2026-08-09") for i in range(100, 150)],
    }
    details = {f"r{i}": [_product(1000 + i)] for i in range(150)}
    recorder = GraphQLRecorder(pages=pages, details=details)
    client = _client(monkeypatch, recorder.handler)

    _, conversion = fetch_receipt_history(client, window_start=date(2026, 8, 1))

    convert_queries = [
        json.loads(request.content)["query"]
        for request in recorder.requests
        if "productConvertId" in json.loads(request.content)["query"]
    ]
    assert len(convert_queries) == 2
    assert len(re.findall(r"p\d+: productConvertId\(", convert_queries[0])) == 100
    assert len(re.findall(r"p\d+: productConvertId\(", convert_queries[1])) == 50
    assert len(conversion) == 150


def test_receipt_conversion_omits_unresolved_ids(monkeypatch) -> None:
    """Null and non-positive conversion values leave the id out of the mapping."""
    pages = {0: [_receipt(f"r{i}", "2026-08-10") for i in range(3)]}
    details = {f"r{i}": [_product(7 + 11 * i)] for i in range(3)}

    def conversion(pos_id: int):
        if pos_id == 7:
            return None
        if pos_id == 18:
            return -1
        return pos_id + 100000

    recorder = GraphQLRecorder(pages=pages, details=details, conversion=conversion)
    client = _client(monkeypatch, recorder.handler)

    _, mapping = fetch_receipt_history(client, window_start=date(2026, 8, 1))

    assert mapping == {29: 100029}


def test_receipt_null_details_skip_the_receipt(monkeypatch) -> None:
    """A receipt whose details come back null contributes no items."""
    pages = {0: [_receipt("r1", "2026-08-10"), _receipt("r2", "2026-08-09")]}
    details = {"r1": [_product(1)]}  # r2 absent -> null
    recorder = GraphQLRecorder(pages=pages, details=details)
    client = _client(monkeypatch, recorder.handler)

    items, _ = fetch_receipt_history(client, window_start=date(2026, 8, 1))

    assert [item.pos_id for item in items] == [1]


def test_receipt_graphql_error_payload_raises_without_token(monkeypatch) -> None:
    """A GraphQL errors payload raises AlbertHeijnError without leaking the token."""
    recorder = GraphQLRecorder()
    recorder.errors = True
    client = _client(monkeypatch, recorder.handler)

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_receipt_history(client, window_start=date(2026, 8, 15))

    assert "status 200" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_receipt_http_error_raises_with_status(monkeypatch) -> None:
    """A non-200 raises AlbertHeijnError naming the failing status."""
    recorder = GraphQLRecorder()
    recorder.status = 500
    client = _client(monkeypatch, recorder.handler)

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_receipt_history(client, window_start=date(2026, 8, 15))

    assert "500" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_enrich_product_names_chunks_in_batches_of_one_hundred(monkeypatch) -> None:
    """150 ids produce two requests: 100 ids, then 50; titles map by webshop id."""
    seen: list[httpx.Request] = []
    first_response = [
        {"webshopId": i, "title": f"Title {i}", "currentPrice": None}
        for i in range(1, 101)
    ]
    second_response = [
        {"webshopId": i, "title": f"Title {i}", "currentPrice": None}
        for i in range(101, 151)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        assert request.url.path == "/mobile-services/product/search/v2/products"
        ids = [value for key, value in request.url.params.multi_items() if key == "ids"]
        assert request.url.params["sortOn"] == "INPUT_PRODUCT_IDS"
        assert request.headers["Authorization"] == AUTHORIZATION
        if len(ids) == 100:
            return httpx.Response(200, json=first_response)
        assert len(ids) == 50
        return httpx.Response(200, json=second_response)

    client = _client(monkeypatch, handler)

    names = enrich_product_names(client, list(range(1, 151)))

    assert len(seen) == 2
    assert names[1] == "Title 1"
    assert names[150] == "Title 150"
    assert len(names) == 150


def test_enrich_product_names_omits_ids_the_endpoint_skips(monkeypatch) -> None:
    """Ids the endpoint does not return have no entry, keeping the caller's name."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"webshopId": 1, "title": "Melk"}])

    client = _client(monkeypatch, handler)

    assert enrich_product_names(client, [1, 2, 3]) == {1: "Melk"}


def test_enrich_product_names_http_error_raises_with_status(monkeypatch) -> None:
    """A non-200 raises AlbertHeijnError naming the failing status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError) as excinfo:
        enrich_product_names(client, [1])

    assert "503" in str(excinfo.value)


def test_enrich_product_names_unexpected_body_raises(monkeypatch) -> None:
    """A 200 body that is not a product list raises AlbertHeijnError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = _client(monkeypatch, handler)

    with pytest.raises(AlbertHeijnError):
        enrich_product_names(client, [1])
