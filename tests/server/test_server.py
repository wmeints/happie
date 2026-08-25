"""Tests for the happie.server MCP tools."""

import asyncio
import json
from dataclasses import asdict
from datetime import date

import pytest
from fastmcp.exceptions import ToolError

from happie.albertheijn import Product, PurchaseStat
from happie.auth import AuthenticationError
from happie.server import mcp


class StubClient:
    """Records search calls and returns canned products or raises an error."""

    def __init__(
        self,
        products: list[Product] | None = None,
        error: Exception | None = None,
        stats: list[PurchaseStat] | None = None,
        stats_error: Exception | None = None,
    ):
        self.products = products or []
        self.error = error
        self.calls: list[tuple[str, int]] = []
        self.stats = stats or []
        self.stats_error = stats_error
        self.history_calls: list[int] = []

    def search_products(self, query: str, limit: int = 10) -> list[Product]:
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.products

    def get_purchase_history(self, days: int = 90) -> list[PurchaseStat]:
        self.history_calls.append(days)
        if self.stats_error is not None:
            raise self.stats_error
        return self.stats


def _product() -> Product:
    return Product(
        webshop_id=111,
        title="Melk",
        brand="AH",
        price=1.19,
        price_before_bonus=1.19,
        is_bonus=False,
        bonus_mechanism="",
        sales_unit_size="1 L",
        unit_price_description="per 1 L",
        available_online=True,
        main_category="Melk",
    )


def _patch_client(monkeypatch, stub: StubClient) -> None:
    """Make the server module's client lookups return ``stub``."""
    from happie import server

    monkeypatch.setattr(server, "AlbertHeijnClient", lambda: stub)


def test_search_products_passes_arguments_to_client(monkeypatch) -> None:
    """The tool forwards its arguments to the client and returns its products."""
    stub = StubClient(products=[_product()])
    _patch_client(monkeypatch, stub)

    result = asyncio.run(
        mcp.call_tool("search_products", {"query": "melk", "limit": 3})
    )

    assert stub.calls == [("melk", 3)]
    assert result.is_error is False
    assert result.structured_content["result"] == [asdict(_product())]


def test_search_products_defaults_limit_to_ten(monkeypatch) -> None:
    """Omitting the limit uses the tool's default of ten."""
    stub = StubClient()
    _patch_client(monkeypatch, stub)

    asyncio.run(mcp.call_tool("search_products", {"query": "melk"}))

    assert stub.calls == [("melk", 10)]


def test_search_products_returns_empty_list_when_no_matches(monkeypatch) -> None:
    """No matching products yields an empty list, not an error."""
    stub = StubClient()
    _patch_client(monkeypatch, stub)

    result = asyncio.run(mcp.call_tool("search_products", {"query": "zzzznotthere"}))

    assert result.is_error is False
    assert result.structured_content["result"] == []


def test_search_products_propagates_client_errors(monkeypatch) -> None:
    """A client error (e.g. missing token) surfaces as a tool error."""
    stub = StubClient(error=AuthenticationError("No stored token."))
    _patch_client(monkeypatch, stub)

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(mcp.call_tool("search_products", {"query": "melk"}))

    assert isinstance(excinfo.value.__cause__, AuthenticationError)


def _stat(key: str = "wi111", total_quantity: float = 3.0, **overrides) -> PurchaseStat:
    """A canned purchase statistic, with ``key``/``total_quantity`` set."""
    data = {
        "key": key,
        "name": "Melk",
        "total_quantity": total_quantity,
        "total_spend": 3.57,
        "histogram": ((date(2026, 6, 1), 1.0), (date(2026, 6, 2), 2.0)),
    }
    data.update(overrides)
    return PurchaseStat(**data)


def _json_round_trip(value: object) -> object:
    """Normalise a dataclass dict the way the MCP JSON transport does."""
    return json.loads(json.dumps(value, default=str))


def test_purchase_frequency_passes_arguments_and_returns_stats(monkeypatch) -> None:
    """The tool forwards its window and trims the result to the top quantities."""
    stats = [
        _stat("wi1", total_quantity=9.0),
        _stat("wi2", total_quantity=4.0),
        _stat("wi3", total_quantity=1.0),
    ]
    stub = StubClient(stats=stats)
    _patch_client(monkeypatch, stub)

    result = asyncio.run(mcp.call_tool("purchase_frequency", {"days": 30, "limit": 2}))

    assert stub.history_calls == [30]
    assert result.is_error is False
    assert result.structured_content["result"] == [
        _json_round_trip(asdict(stat)) for stat in stats[:2]
    ]


def test_purchase_frequency_defaults_days_to_ninety(monkeypatch) -> None:
    """Omitting the window uses the tool's default of ninety days."""
    stub = StubClient()
    _patch_client(monkeypatch, stub)

    asyncio.run(mcp.call_tool("purchase_frequency", {}))

    assert stub.history_calls == [90]


def test_purchase_frequency_returns_empty_list_when_no_purchases(monkeypatch) -> None:
    """An empty window yields an empty list, not an error."""
    stub = StubClient()
    _patch_client(monkeypatch, stub)

    result = asyncio.run(mcp.call_tool("purchase_frequency", {}))

    assert result.is_error is False
    assert result.structured_content["result"] == []


def test_purchase_frequency_propagates_client_errors(monkeypatch) -> None:
    """A client error (e.g. missing token) surfaces as a tool error."""
    stub = StubClient(stats_error=AuthenticationError("No stored token."))
    _patch_client(monkeypatch, stub)

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(mcp.call_tool("purchase_frequency", {}))

    assert isinstance(excinfo.value.__cause__, AuthenticationError)
