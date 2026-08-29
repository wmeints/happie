"""Tests for the bonus-page endpoint fetches (metadata, section, groups)."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from happie.albertheijn._bonus import (
    METADATA_URL,
    SECTION_URL,
    BonusGroup,
    fetch_bonus_products,
    fetch_bonus_promotions,
    fetch_bonus_section,
    fetch_national_categories,
)
from happie.albertheijn._client import _APP_HEADERS
from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._receipts import GRAPHQL_URL, PRODUCTS_BY_IDS_URL

AUTHORIZATION = "Bearer access-secret"

TODAY = datetime.now(UTC).date()
ACTIVE_START = (TODAY - timedelta(days=3)).isoformat()
ACTIVE_END = (TODAY + timedelta(days=4)).isoformat()


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


def _period(start: str, end: str) -> dict:
    return {"bonusStartDate": start, "bonusEndDate": end}


def _tab_entry(bonus_type: str, description: str) -> dict:
    return {
        "bonusType": bonus_type,
        "description": description,
        "count": 3,
        "url": f"/bonus/{description}",
    }


def _metadata_body(periods: list[tuple[dict, list[dict]]]) -> dict:
    """A metadata body: each period carries its own ``tabs``."""
    return {
        "periods": [
            {**period, "tabs": [{"urlMetadataList": entries}]}
            for period, entries in periods
        ]
    }


def _product(webshop_id: int, **overrides) -> dict:
    data = {
        "webshopId": webshop_id,
        "title": f"Product {webshop_id}",
        "brand": "AH",
        "salesUnitSize": "500 g",
        "unitPriceDescription": "per 100 g",
        "currentPrice": 2.49,
        "priceBeforeBonus": 3.49,
        "isBonus": True,
        "bonusMechanism": "1+1 gratis",
        "mainCategory": "Bijgerecht",
        "availableOnline": True,
    }
    data.update(overrides)
    return data


def _group(segment_id: str, **overrides) -> dict:
    data = {
        "id": segment_id,
        "segmentDescription": "Alle Galbani",
        "discountDescription": "1+1 gratis",
        "category": "Bijgerecht",
        "exampleFromPrice": None,
        "exampleForPrice": None,
        "products": [],
    }
    data.update(overrides)
    return data


# --- Metadata --------------------------------------------------------------


def test_metadata_returns_active_period_and_national_categories(monkeypatch) -> None:
    """The first period containing today and the NATIONAL tabs come back, in
    the active period's tab order, other bonus types and other periods'
    categories excluded."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json=_metadata_body(
                [
                    (
                        _period("2026-01-01", "2026-01-07"),
                        [_tab_entry("NATIONAL", "Oude categorie")],
                    ),
                    (
                        _period(ACTIVE_START, ACTIVE_END),
                        [
                            _tab_entry("NATIONAL", "Voor de kids"),
                            _tab_entry("SPOTLIGHT", "Uit de folder"),
                            _tab_entry("NATIONAL", "Voor thuis"),
                            _tab_entry("PERSONAL", "Jouw bonus"),
                        ],
                    ),
                    (
                        _period(ACTIVE_END, "2026-12-31"),
                        [_tab_entry("NATIONAL", "Volgende week")],
                    ),
                ],
            ),
        )

    period_start, categories = fetch_national_categories(_client(monkeypatch, handler))

    assert period_start == ACTIVE_START
    assert categories == ["Voor de kids", "Voor thuis"]
    request = seen["request"]
    assert request.method == "GET"
    assert str(request.url) == METADATA_URL
    assert request.headers["Authorization"] == AUTHORIZATION
    assert request.headers["User-Agent"] == "Appie/8.22.3"


def test_metadata_without_active_period_yields_no_categories(monkeypatch) -> None:
    """Periods that do not contain today (past or future) yield none, even
    when they carry national categories."""
    bodies = [
        _metadata_body(
            [
                (
                    _period("2026-01-01", "2026-01-07"),
                    [_tab_entry("NATIONAL", "Voor de kids")],
                )
            ]
        ),
        _metadata_body(
            [
                (
                    _period(ACTIVE_END, "2026-12-31"),
                    [_tab_entry("NATIONAL", "Voor de kids")],
                )
            ]
        ),
    ]
    calls = iter(bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(calls))

    client = _client(monkeypatch, handler)
    assert fetch_national_categories(client) == ("", [])
    assert fetch_national_categories(client) == ("", [])


def test_metadata_http_error_raises_without_token(monkeypatch) -> None:
    """A non-200 raises AlbertHeijnError naming the status, not the token."""
    client = _client(monkeypatch, lambda request: httpx.Response(503))

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_national_categories(client)

    assert "503" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_metadata_unexpected_body_raises(monkeypatch) -> None:
    """A 200 body without a usable periods list raises AlbertHeijnError."""
    client = _client(
        monkeypatch, lambda request: httpx.Response(200, json={"periods": "nope"})
    )

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_national_categories(client)

    assert "access-secret" not in str(excinfo.value)


def test_metadata_active_period_without_tabs_raises(monkeypatch) -> None:
    """An active period that carries no tabs list raises AlbertHeijnError."""
    client = _client(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"periods": [_period(ACTIVE_START, ACTIVE_END)]}
        ),
    )

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_national_categories(client)

    assert "access-secret" not in str(excinfo.value)


# --- Section ----------------------------------------------------------------


def test_section_sends_category_request_and_unwraps_entries(monkeypatch) -> None:
    """The section request carries the period start, NATIONAL, and category;
    entries unwrap to raw products and BonusGroup objects in the API's order."""
    seen: dict[str, httpx.Request] = {}
    products = [_product(101), _product(102)]

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "bonusGroupOrProducts": [
                    {"product": products[0]},
                    {"bonusGroup": _group("805111")},
                    {"product": products[1]},
                ]
            },
        )

    section = fetch_bonus_section(
        _client(monkeypatch, handler), "2026-08-24", "Voor de kids"
    )

    assert section == [
        products[0],
        BonusGroup(
            segment_id="805111",
            description="Alle Galbani",
            discount="1+1 gratis",
            category="Bijgerecht",
        ),
        products[1],
    ]
    request = seen["request"]
    assert request.method == "GET"
    assert str(request.url).startswith(SECTION_URL)
    assert dict(request.url.params) == {
        "application": "AHWEBSHOP",
        "date": "2026-08-24",
        "promotionType": "NATIONAL",
        "category": "Voor de kids",
    }
    assert request.headers["Authorization"] == AUTHORIZATION


def test_section_http_error_names_the_category(monkeypatch) -> None:
    """A failing section fetch raises naming the category and the status."""
    client = _client(monkeypatch, lambda request: httpx.Response(500))

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_section(client, "2026-08-24", "Voor de kids")

    assert "Voor de kids" in str(excinfo.value)
    assert "500" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_section_unexpected_entry_raises(monkeypatch) -> None:
    """An entry that is neither product nor bonusGroup raises AlbertHeijnError."""
    client = _client(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"bonusGroupOrProducts": [{"somethingElse": {}}]}
        ),
    )

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_section(client, "2026-08-24", "Voor de kids")

    assert "access-secret" not in str(excinfo.value)


# --- Group expansion (GraphQL) ----------------------------------------------


def test_bonus_promotions_maps_segments_to_product_ids(monkeypatch) -> None:
    """The no-argument bonusPromotions query maps segment ids to product ids;
    segments without products have no entry."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "data": {
                    "bonusPromotions": [
                        {"id": "s1", "products": [{"id": 1}, {"id": 2}]},
                        {"id": "s2", "products": [{"id": 3}]},
                        {"id": "s3", "products": []},
                    ]
                }
            },
        )

    mapping = fetch_bonus_promotions(_client(monkeypatch, handler))

    assert mapping == {"s1": [1, 2], "s2": [3]}
    request = seen["request"]
    assert request.method == "POST"
    assert str(request.url) == GRAPHQL_URL
    body = json.loads(request.content)
    assert "variables" not in body
    assert "bonusPromotions" in body["query"]
    assert request.headers["Authorization"] == AUTHORIZATION


def test_bonus_promotions_empty_list_maps_to_nothing(monkeypatch) -> None:
    """An empty bonusPromotions list maps to an empty segment mapping."""
    client = _client(
        monkeypatch,
        lambda request: httpx.Response(200, json={"data": {"bonusPromotions": []}}),
    )

    assert fetch_bonus_promotions(client) == {}


def test_bonus_promotions_error_payload_raises_without_token(monkeypatch) -> None:
    """A GraphQL errors payload raises AlbertHeijnError without leaking the
    token."""
    client = _client(
        monkeypatch,
        lambda request: httpx.Response(200, json={"errors": [{"message": "boom"}]}),
    )

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_promotions(client)

    assert "access-secret" not in str(excinfo.value)


def test_bonus_promotions_http_error_raises_with_status(monkeypatch) -> None:
    """A non-200 raises AlbertHeijnError naming the failing status."""
    client = _client(monkeypatch, lambda request: httpx.Response(503))

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_promotions(client)

    assert "503" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


# --- Group products (products by ids) -----------------------------------------


def test_bonus_products_fetch_ids_in_batches_of_one_hundred(monkeypatch) -> None:
    """150 ids produce two requests: 100 ids, then 50; raw objects by id."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        ids = [int(value) for value in request.url.params.get_list("ids")]
        return httpx.Response(200, json=[_product(product_id) for product_id in ids])

    client = _client(monkeypatch, handler)

    products = fetch_bonus_products(client, list(range(1, 151)))

    assert len(products) == 150
    assert products[42] == _product(42)
    assert len(requests_seen) == 2
    expected_batches = [
        [str(product_id) for product_id in range(1, 101)],
        [str(product_id) for product_id in range(101, 151)],
    ]
    for request, expected in zip(requests_seen, expected_batches, strict=True):
        assert request.method == "GET"
        assert str(request.url).startswith(PRODUCTS_BY_IDS_URL)
        assert request.url.params.get_list("ids") == expected
        assert request.url.params["sortOn"] == "INPUT_PRODUCT_IDS"
        assert request.headers["Authorization"] == AUTHORIZATION


def test_bonus_products_omits_ids_the_endpoint_skips(monkeypatch) -> None:
    """Ids the endpoint does not return have no entry in the mapping."""
    client = _client(
        monkeypatch,
        lambda request: httpx.Response(200, json=[_product(1), {"webshopId": None}]),
    )

    assert fetch_bonus_products(client, [1, 2, 3]) == {1: _product(1)}


def test_bonus_products_http_error_raises_with_status(monkeypatch) -> None:
    """A non-200 raises AlbertHeijnError naming the failing status."""
    client = _client(monkeypatch, lambda request: httpx.Response(503))

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_products(client, [1])

    assert "503" in str(excinfo.value)
    assert "access-secret" not in str(excinfo.value)


def test_bonus_products_unexpected_body_raises(monkeypatch) -> None:
    """A 200 body that is not a product list raises AlbertHeijnError."""
    client = _client(
        monkeypatch, lambda request: httpx.Response(200, json={"products": []})
    )

    with pytest.raises(AlbertHeijnError) as excinfo:
        fetch_bonus_products(client, [1])

    assert "access-secret" not in str(excinfo.value)
