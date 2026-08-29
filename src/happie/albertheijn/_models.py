"""Typed models for Albert Heijn API responses.

Holds the public ``Product`` model — the shape both the API client and the
MCP tools speak — and translates raw API product objects into it.
"""

from dataclasses import dataclass
from datetime import date

__all__ = ["Product", "product_from_api"]


@dataclass(frozen=True)
class Product:
    """A single Albert Heijn product as returned by the search API.

    Attributes
    ----------
    webshop_id : int
        The webshop identifier used to order the product.
    title : str
        The product name.
    brand : str
        The brand name.
    price : float
        The current price.
    price_before_bonus : float
        The price before any bonus promotion; equals `price` for
        products that are not on bonus.
    is_bonus : bool
        Whether the product is currently on bonus.
    bonus_mechanism : str
        The bonus mechanism text (for example "2e halve prijs"); empty
        when not on bonus.
    sales_unit_size : str
        The package size (for example "250 g").
    unit_price_description : str
        The unit price description (for example "per 100 g").
    available_online : bool
        Whether the product is available for online order.
    main_category : str
        The main category of the product.
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

    A non-bonus product always reports `price == price_before_bonus`; a
    missing ``currentPrice`` falls back to the pre-bonus price. Fields the
    tool does not surface (images, nutriscore, ad flags) are dropped.

    Parameters
    ----------
    data : dict
        One entry of the API's ``products`` array.

    Returns
    -------
    Product
        The translated :class:`Product`.

    Raises
    ------
    KeyError
        If the ``webshopId`` field is missing.
    TypeError
        If a field has an unexpected type.
    """  # noqa: DOC502, RUF100
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


@dataclass(frozen=True)
class PurchaseStat:
    """Purchase statistics for one product over a time window.

    Attributes
    ----------
    key : str
        The canonical product key: ``wi<webshop_id>`` for products
        resolved to a webshop id, ``pos<pos_id>`` for receipt items
        whose store point-of-sale id has no webshop conversion.
    name : str
        The product name.
    total_quantity : float
        The total quantity purchased in the window.
    total_spend : float
        The total amount spent on the product in the window.
    histogram : tuple[tuple[date, float], ...]
        The sparse per-day purchase quantities: one ``(date,
        quantity)`` entry per calendar day on which the product was
        purchased, the quantity summed across that day's records,
        ordered by date ascending. Empty when the product was not
        purchased in the window.
    """

    key: str
    name: str
    total_quantity: float
    total_spend: float
    histogram: tuple[tuple[date, float], ...]
