"""Tests for the happie.server MCP tools."""

import asyncio
from dataclasses import asdict

import pytest
from fastmcp.exceptions import ToolError

from happie.albertheijn import Product
from happie.auth import AuthenticationError
from happie.server import mcp


class StubClient:
    """Records search calls and returns canned products or raises an error."""

    def __init__(
        self, products: list[Product] | None = None, error: Exception | None = None
    ):
        self.products = products or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search_products(self, query: str, limit: int = 10) -> list[Product]:
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.products


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
