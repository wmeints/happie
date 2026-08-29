"""I/O for the bonus-page (bonus aanbiedingen) endpoints of the Albert Heijn API.

Holds the fetches behind the weekly bonus folder: the bonus metadata (the
active period and its national categories), one category's bonus section
(raw product objects and bonus-group objects, in the API's order), the
GraphQL resolution of every promotion segment to its product ids, and the
batched lookup of the group products' full product objects. Every function
takes a preconfigured ``httpx.Client`` and returns plain data; no
authentication or model translation happens here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._receipts import GRAPHQL_URL, PRODUCTS_BY_IDS_URL

__all__ = [
    "METADATA_URL",
    "SECTION_URL",
    "BonusGroup",
    "fetch_bonus_products",
    "fetch_bonus_promotions",
    "fetch_bonus_section",
    "fetch_national_categories",
]

METADATA_URL = "https://api.ah.nl/mobile-services/bonuspage/v3/metadata"
SECTION_URL = "https://api.ah.nl/mobile-services/bonuspage/v2/section"

#: Product ids per products-by-ids batch.
_ID_BATCH = 100

_BONUS_PROMOTIONS_QUERY = """
query {
  bonusPromotions {
    id
    products {
      id
    }
  }
}
"""


@dataclass(frozen=True)
class BonusGroup:
    """One multi-product bonus group (a segment offer) from a section.

    Attributes:
        segment_id: The promotion segment id, as a string.
        description: The group's description (for example "Alle Galbani").
        discount: The group's deal text (for example "1+1 gratis").
        category: The national category the group is listed under.
    """

    segment_id: str
    description: str
    discount: str
    category: str


def fetch_national_categories(http: httpx.Client) -> tuple[str, list[str]]:
    """Fetch the bonus metadata and select the active period's categories.

    The active period is the first metadata period whose
    ``bonusStartDate``..``bonusEndDate`` range contains today (UTC).

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.

    Returns:
        A pair of:

        - the active period's start date as a plain ``YYYY-MM-DD`` string,
          or ``""`` when no period contains today;
        - the descriptions of the ``NATIONAL`` bonus categories, in the
          metadata's order.

    Raises:
        AlbertHeijnError: If the request returns a status other than 200 or
            an unexpected body.
    """
    response = http.get(METADATA_URL)
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Bonus metadata failed with status {response.status_code}."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(
            "Bonus metadata returned an unexpected response."
        ) from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError("Bonus metadata returned an unexpected response.")
    periods = body.get("periods")
    if not isinstance(periods, list):
        raise AlbertHeijnError("Bonus metadata returned an unexpected response.")
    today = datetime.now(UTC).date()
    active: dict | None = None
    for period in periods:
        if not isinstance(period, dict):
            raise AlbertHeijnError("Bonus metadata returned an unexpected response.")
        try:
            start = date.fromisoformat(str(period["bonusStartDate"]))
            end = date.fromisoformat(str(period["bonusEndDate"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AlbertHeijnError(
                "Bonus metadata returned an unexpected response."
            ) from exc
        if start <= today <= end:
            active = period
            break
    if active is None:
        return "", []

    tabs = active.get("tabs")
    if not isinstance(tabs, list):
        raise AlbertHeijnError("Bonus metadata returned an unexpected response.")

    categories: list[str] = []
    for tab in tabs:
        try:
            entries = tab["urlMetadataList"]
        except (KeyError, TypeError) as exc:
            raise AlbertHeijnError(
                "Bonus metadata returned an unexpected response."
            ) from exc
        if not isinstance(entries, list):
            raise AlbertHeijnError("Bonus metadata returned an unexpected response.")
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("bonusType") != "NATIONAL":
                continue
            description = entry.get("description")
            if not isinstance(description, str) or not description:
                raise AlbertHeijnError(
                    "Bonus metadata returned an unexpected response."
                )
            categories.append(description)
    return str(active["bonusStartDate"]), categories


def fetch_bonus_section(
    http: httpx.Client, period_start: str, category: str
) -> list[dict | BonusGroup]:
    """Fetch one national category's bonus section.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        period_start: The bonus period's start date (``YYYY-MM-DD``).
        category: The national category's description.

    Returns:
        The section's ``bonusGroupOrProducts`` entries in the API's order,
        unwrapped from their one-key containers: raw product objects (the
        search API's shape) and :class:`BonusGroup` objects.

    Raises:
        AlbertHeijnError: If the request returns a status other than 200 or
            an unexpected body.
    """
    response = http.get(
        SECTION_URL,
        params={
            "application": "AHWEBSHOP",
            "date": period_start,
            "promotionType": "NATIONAL",
            "category": category,
        },
    )
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Bonus section for {category} failed with status {response.status_code}."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(
            f"Bonus section for {category} returned an unexpected response."
        ) from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError(
            f"Bonus section for {category} returned an unexpected response."
        )
    entries = body.get("bonusGroupOrProducts")
    if not isinstance(entries, list):
        raise AlbertHeijnError(
            f"Bonus section for {category} returned an unexpected response."
        )

    section: list[dict | BonusGroup] = []
    for entry in entries:
        if not isinstance(entry, dict) or not (
            isinstance(entry.get("product"), dict)
            or isinstance(entry.get("bonusGroup"), dict)
        ):
            raise AlbertHeijnError(
                f"Bonus section for {category} returned an unexpected response."
            )
        if "product" in entry:
            section.append(entry["product"])
        else:
            section.append(_bonus_group(entry["bonusGroup"], category))
    return section


def _bonus_group(group: dict, category: str) -> BonusGroup:
    """Translate one raw bonus-group entry into a :class:`BonusGroup`."""
    try:
        return BonusGroup(
            segment_id=str(group["id"]),
            description=str(group.get("segmentDescription") or ""),
            discount=str(group.get("discountDescription") or ""),
            category=str(group.get("category") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(
            f"Bonus section for {category} returned an unexpected response."
        ) from exc


def fetch_bonus_promotions(http: httpx.Client) -> dict[str, list[int]]:
    """Resolve every served promotion segment to its product ids.

    Uses the no-argument ``bonusPromotions`` GraphQL query, which returns
    every segment the API currently serves.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.

    Returns:
        The segment id to product (webshop) id mapping, with each
        segment's product ids in the API's order; segments serving no
        products have no entry.

    Raises:
        AlbertHeijnError: If the response is not 200, carries a GraphQL
            ``errors`` payload, or has an unexpected shape.
    """
    data = _graphql(http, _BONUS_PROMOTIONS_QUERY, "Bonus promotions")
    promotions = data.get("bonusPromotions")
    if not isinstance(promotions, list):
        raise AlbertHeijnError("Bonus promotions returned an unexpected response.")

    mapping: dict[str, list[int]] = {}
    for promotion in promotions:
        try:
            segment_id = str(promotion["id"])
            products = promotion["products"]
        except (KeyError, TypeError) as exc:
            raise AlbertHeijnError(
                "Bonus promotions returned an unexpected response."
            ) from exc
        if not isinstance(products, list):
            raise AlbertHeijnError("Bonus promotions returned an unexpected response.")
        product_ids: list[int] = []
        for product in products:
            if not isinstance(product, dict):
                continue
            try:
                product_ids.append(int(product["id"]))
            except (KeyError, TypeError, ValueError):
                continue
        if product_ids:
            mapping[segment_id] = product_ids
    return mapping


def fetch_bonus_products(
    http: httpx.Client, webshop_ids: Sequence[int]
) -> dict[int, dict]:
    """Fetch the full product objects for the given product ids.

    Requests the ids in batches at the products-by-ids endpoint, the same
    endpoint the receipt enrichment uses.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        webshop_ids: The product ids to look up, in any order and with
            duplicates.

    Returns:
        The webshop id to raw product object mapping for the ids the
        endpoint returned; ids the endpoint omits have no entry.

    Raises:
        AlbertHeijnError: If a request returns a status other than 200 or
            a body that is not a product list.
    """
    products: dict[int, dict] = {}
    for chunk in _chunked(list(dict.fromkeys(webshop_ids)), _ID_BATCH):
        params = [("ids", str(product_id)) for product_id in chunk]
        response = http.get(
            PRODUCTS_BY_IDS_URL, params=[*params, ("sortOn", "INPUT_PRODUCT_IDS")]
        )
        if response.status_code != 200:
            raise AlbertHeijnError(
                f"Bonus product lookup failed with status {response.status_code}."
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AlbertHeijnError(
                "Bonus product lookup returned an unexpected response."
            ) from exc
        if not isinstance(body, list):
            raise AlbertHeijnError(
                "Bonus product lookup returned an unexpected response."
            )
        for product in body:
            if not isinstance(product, dict):
                continue
            try:
                products[int(product["webshopId"])] = product
            except (KeyError, TypeError, ValueError):
                continue
    return products


def _graphql(http: httpx.Client, query: str, operation: str) -> dict:
    """POST one no-argument GraphQL query and return its ``data`` payload.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        query: The GraphQL query string.
        operation: The operation name, used to identify the failing
            request in error messages.

    Returns:
        The response's ``data`` payload.

    Raises:
        AlbertHeijnError: If the response is not 200, carries a GraphQL
            ``errors`` payload, or has an unexpected shape.
    """
    response = http.post(GRAPHQL_URL, json={"query": query})
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"{operation} failed with status {response.status_code}."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(f"{operation} returned an unexpected response.") from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    if body.get("errors"):
        raise AlbertHeijnError(
            f"{operation} returned an error payload (status {response.status_code})."
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    return data


def _chunked(items: Sequence, size: int) -> list[list]:
    """Yield ``items`` in consecutive chunks of at most ``size``."""
    return [list(items[start : start + size]) for start in range(0, len(items), size)]
