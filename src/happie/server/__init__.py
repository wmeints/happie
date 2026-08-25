"""MCP server exposing the Albert Heijn grocery domain.

Exposes ``mcp``, the FastMCP instance with the registered tools, and
``serve()``, which runs the server on stdio. The tools are thin wraps
around the Albert Heijn API client, so one model serves both the client
and the MCP seams.
"""

from fastmcp import FastMCP

from happie.albertheijn import AlbertHeijnClient, Product, PurchaseStat

__all__ = ["mcp", "serve"]

mcp = FastMCP("happie")


@mcp.tool
def search_products(query: str, limit: int = 10) -> list[Product]:
    """Search the Albert Heijn assortment for a product.

    Args:
        query: The search term.
        limit: The maximum number of products to return.

    Returns:
        The matching products, at most ``limit`` of them, in the API's
        relevance order. Each product carries its webshop identifier, name,
        brand, current and pre-bonus price, bonus information, package
        size, online availability, and main category.

    Raises:
        AuthenticationError: If no usable stored token exists.
        AlbertHeijnError: If the search endpoint fails.
    """
    return AlbertHeijnClient().search_products(query, limit)


@mcp.tool
def purchase_frequency(days: int = 90, limit: int | None = None) -> list[PurchaseStat]:
    """Show how often each product was purchased in a recent time window.

    Merges in-store receipts and delivered webshop orders, so a product
    bought in both places appears once, with the combined quantities.

    Args:
        days: The length of the window in days, ending today.
        limit: The maximum number of statistics to return; the highest
            total quantities come first. None returns all statistics.

    Returns:
        One statistic per purchased product, sorted by total quantity
        descending. Each carries its product key, name, total quantity,
        total spend, and a sparse per-day histogram with one entry per
        purchased day, each entry carrying that day's date and that day's
        total quantity, ordered by date.

    Raises:
        AuthenticationError: If no usable stored token exists.
        AlbertHeijnError: If the purchase-history endpoints fail.
    """
    stats = AlbertHeijnClient().get_purchase_history(days)
    if limit is not None:
        stats = stats[:limit]
    return stats


def serve() -> None:
    """Run the MCP server on stdio until the client disconnects."""
    mcp.run()
