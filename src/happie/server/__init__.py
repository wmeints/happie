"""MCP server exposing the Albert Heijn grocery domain.

Exposes ``mcp``, the FastMCP instance with the registered tools, and
``serve()``, which runs the server on stdio. The tools are thin wraps
around the Albert Heijn API client, so one model serves both the client
and the MCP seams.
"""

from fastmcp import FastMCP

from happie.albertheijn import AlbertHeijnClient, Product

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


def serve() -> None:
    """Run the MCP server on stdio until the client disconnects."""
    mcp.run()
