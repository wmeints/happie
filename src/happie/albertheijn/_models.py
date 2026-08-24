"""Typed models for Albert Heijn API responses.

Holds the public ``Product`` model — the shape both the API client and the
MCP tools speak — and translates raw API product objects into it.
"""

from dataclasses import dataclass

__all__ = ["Product", "product_from_api"]


@dataclass(frozen=True)
class Product:
    """A single Albert Heijn product as returned by the search API.

    Attributes:
        webshop_id: The webshop identifier used to order the product.
        title: The product name.
        brand: The brand name.
        price: The current price.
        price_before_bonus: The price before any bonus promotion; equals
            ``price`` for products that are not on bonus.
        is_bonus: Whether the product is currently on bonus.
        bonus_mechanism: The bonus mechanism text (for example
            "2e halve prijs"); empty when not on bonus.
        sales_unit_size: The package size (for example "250 g").
        unit_price_description: The unit price description (for example
            "per 100 g").
        available_online: Whether the product is available for online order.
        main_category: The main category of the product.
    """

    webshop_id: int
    title: str
    brand: str
    price: float
    price_before_bonus: float
    is_bonus: bool
    bonus_mechanism: str
    sales_unit_size: str
    unit_price_description: str
    available_online: bool
    main_category: str


def product_from_api(data: dict) -> Product:
    """Translate a raw API product object into a :class:`Product`.

    A non-bonus product always reports ``price == price_before_bonus``; a
    missing ``currentPrice`` falls back to the pre-bonus price. Fields the
    tool does not surface (images, nutriscore, ad flags) are dropped.

    Args:
        data: One entry of the API's ``products`` array.

    Returns:
        The translated :class:`Product`.

    Raises:
        KeyError: If the ``webshopId`` field is missing.
        TypeError: If a field has an unexpected type.
    """
    price = float(data.get("currentPrice") or 0.0)
    price_before_bonus = float(data.get("priceBeforeBonus") or 0.0)
    is_bonus = bool(data.get("isBonus", False))
    if price == 0.0:
        price = price_before_bonus
    if not is_bonus:
        price_before_bonus = price
    return Product(
        webshop_id=int(data["webshopId"]),
        title=str(data.get("title") or ""),
        brand=str(data.get("brand") or ""),
        price=price,
        price_before_bonus=price_before_bonus,
        is_bonus=is_bonus,
        bonus_mechanism=str(data.get("bonusMechanism") or ""),
        sales_unit_size=str(data.get("salesUnitSize") or ""),
        unit_price_description=str(data.get("unitPriceDescription") or ""),
        available_online=bool(data.get("availableOnline", False)),
        main_category=str(data.get("mainCategory") or ""),
    )
