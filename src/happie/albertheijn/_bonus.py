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

#: Message raised for any bonus metadata body that cannot be used.
_UNEXPECTED_METADATA = "Bonus metadata returned an unexpected response."

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

    Attributes
    ----------
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

    Returns
    -------
        A pair of:

        - the active period's start date as a plain ``YYYY-MM-DD`` string,
          or ``""`` when no period contains today;
        - the descriptions of the ``NATIONAL`` bonus categories, in the
          metadata's order.

    Raises
    ------
        AlbertHeijnError: If the request returns a status other than 200 or
            an unexpected body.
    """
    active = _active_period(_metadata_periods(http))
    if active is None:
        return "", []
    return str(active["bonusStartDate"]), _national_categories(active)


def _metadata_periods(http: httpx.Client) -> list:
    """Fetch the bonus metadata and return its raw periods list."""
    response = http.get(METADATA_URL)
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Bonus metadata failed with status {response.status_code}."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(_UNEXPECTED_METADATA) from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError(_UNEXPECTED_METADATA)
    periods = body.get("periods")
    if not isinstance(periods, list):
        raise AlbertHeijnError(_UNEXPECTED_METADATA)
    return periods


def _active_period(periods: list) -> dict | None:
    """Return the first period whose bonus range contains today (UTC)."""
    today = datetime.now(UTC).date()
    for period in periods:
        if not isinstance(period, dict):
            raise AlbertHeijnError(_UNEXPECTED_METADATA)
        if _covers_today(period, today):
            return period
    return None


def _covers_today(period: dict, today: date) -> bool:
    """Check whether the period's start/end dates contain ``today``."""
    try:
        start = date.fromisoformat(str(period["bonusStartDate"]))
        end = date.fromisoformat(str(period["bonusEndDate"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(_UNEXPECTED_METADATA) from exc
    return start <= today <= end


def _national_categories(active: dict) -> list[str]:
    """Collect the NATIONAL descriptions of the active period's tabs."""
    tabs = active.get("tabs")
    if not isinstance(tabs, list):
        raise AlbertHeijnError(_UNEXPECTED_METADATA)
    categories: list[str] = []
    for tab in tabs:
        categories.extend(_national_tab(tab))
    return categories


def _national_tab(tab: dict) -> list[str]:
    """Return the NATIONAL category descriptions served by one tab."""
    try:
        entries = tab["urlMetadataList"]
    except (KeyError, TypeError) as exc:
        raise AlbertHeijnError(_UNEXPECTED_METADATA) from exc
    if not isinstance(entries, list):
        raise AlbertHeijnError(_UNEXPECTED_METADATA)
    return [_category_description(entry) for entry in entries if _is_national(entry)]


def _is_national(entry: object) -> bool:
    """Check whether a metadata entry is a NATIONAL bonus tab entry."""
    return isinstance(entry, dict) and entry.get("bonusType") == "NATIONAL"


def _category_description(entry: dict) -> str:
    """Return one NATIONAL entry's non-empty category description."""
    description = entry.get("description")
    if not isinstance(description, str) or not description:
        raise AlbertHeijnError(_UNEXPECTED_METADATA)
    return description


def fetch_bonus_section(
    http: httpx.Client, period_start: str, category: str
) -> list[dict | BonusGroup]:
    """Fetch one national category's bonus section.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        period_start: The bonus period's start date (``YYYY-MM-DD``).
        category: The national category's description.

    Returns
    -------
        The section's ``bonusGroupOrProducts`` entries in the API's order,
        unwrapped from their one-key containers: raw product objects (the
        search API's shape) and :class:`BonusGroup` objects.

    Raises
    ------
        AlbertHeijnError: If the request returns a status other than 200 or
            an unexpected body.
    """
    body = _section_response(http, period_start, category)
    entries = body.get("bonusGroupOrProducts")
    if not isinstance(entries, list):
        raise AlbertHeijnError(
            f"Bonus section for {category} returned an unexpected response."
        )
    section: list[dict | BonusGroup] = []
    for entry in entries:
        section.append(_section_entry(entry, category))
    return section


def _section_response(http: httpx.Client, period_start: str, category: str) -> dict:
    """Request one category's section and return its decoded object body."""
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
    return body


def _section_entry(entry: dict, category: str) -> dict | BonusGroup:
    """Unwrap one section entry into its raw product or bonus group."""
    _require_product_or_group(entry, category)
    if "product" in entry:
        return entry["product"]
    return _bonus_group(entry["bonusGroup"], category)


def _require_product_or_group(entry: object, category: str) -> None:
    """Raise unless the entry carries a product or a bonus group object."""
    if isinstance(entry, dict) and (
        isinstance(entry.get("product"), dict)
        or isinstance(entry.get("bonusGroup"), dict)
    ):
        return
    raise AlbertHeijnError(
        f"Bonus section for {category} returned an unexpected response."
    )


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

    Returns
    -------
        The segment id to product (webshop) id mapping, with each
        segment's product ids in the API's order; segments serving no
        products have no entry.

    Raises
    ------
        AlbertHeijnError: If the response is not 200, carries a GraphQL
            ``errors`` payload, or has an unexpected shape.
    """
    data = _graphql(http, _BONUS_PROMOTIONS_QUERY, "Bonus promotions")
    promotions = data.get("bonusPromotions")
    if not isinstance(promotions, list):
        raise AlbertHeijnError("Bonus promotions returned an unexpected response.")
    mapping: dict[str, list[int]] = {}
    for promotion in promotions:
        segment_id, product_ids = _promotion_segment(promotion)
        if product_ids:
            mapping[segment_id] = product_ids
    return mapping


def _promotion_segment(promotion: dict) -> tuple[str, list[int]]:
    """Return one promotion's segment id and its usable product ids."""
    try:
        segment_id = str(promotion["id"])
        products = promotion["products"]
    except (KeyError, TypeError) as exc:
        raise AlbertHeijnError(
            "Bonus promotions returned an unexpected response."
        ) from exc
    if not isinstance(products, list):
        raise AlbertHeijnError("Bonus promotions returned an unexpected response.")
    return segment_id, _promotion_product_ids(products)


def _promotion_product_ids(products: list) -> list[int]:
    """Collect the numeric ids of the promotion's products, in order."""
    product_ids: list[int] = []
    for product in products:
        product_id = _numeric_id(product, "id")
        if product_id is not None:
            product_ids.append(product_id)
    return product_ids


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

    Returns
    -------
        The webshop id to raw product object mapping for the ids the
        endpoint returned; ids the endpoint omits have no entry.

    Raises
    ------
        AlbertHeijnError: If a request returns a status other than 200 or
            a body that is not a product list.
    """
    products: dict[int, dict] = {}
    for chunk in _chunked(list(dict.fromkeys(webshop_ids)), _ID_BATCH):
        products.update(_product_batch(http, chunk))
    return products


def _product_batch(http: httpx.Client, chunk: list) -> dict[int, dict]:
    """Fetch one batch of product ids and index the served products."""
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
        raise AlbertHeijnError("Bonus product lookup returned an unexpected response.")
    return _indexed_products(body)


def _indexed_products(body: list) -> dict[int, dict]:
    """Index the returned product objects by their webshop id."""
    products: dict[int, dict] = {}
    for product in body:
        webshop_id = _numeric_id(product, "webshopId")
        if webshop_id is not None:
            products[webshop_id] = product
    return products


def _graphql(http: httpx.Client, query: str, operation: str) -> dict:
    """POST one no-argument GraphQL query and return its ``data`` payload.

    Args:
        http: The preconfigured client carrying the application headers and
            the user's bearer token.
        query: The GraphQL query string.
        operation: The operation name, used to identify the failing
            request in error messages.

    Returns
    -------
        The response's ``data`` payload.

    Raises
    ------
        AlbertHeijnError: If the response is not 200, carries a GraphQL
            ``errors`` payload, or has an unexpected shape.
    """
    response = http.post(GRAPHQL_URL, json={"query": query})
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"{operation} failed with status {response.status_code}."
        )
    body = _graphql_body(response, operation)
    if body.get("errors"):
        raise AlbertHeijnError(
            f"{operation} returned an error payload (status {response.status_code})."
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    return data


def _graphql_body(response: httpx.Response, operation: str) -> dict:
    """Return the GraphQL response's decoded object body."""
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(f"{operation} returned an unexpected response.") from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    return body


def _numeric_id(entry: object, key: str) -> int | None:
    """Return one product entry's ``key`` as an int, or ``None``."""
    if not isinstance(entry, dict):
        return None
    try:
        return int(entry[key])
    except (KeyError, TypeError, ValueError):
        return None


def _chunked(items: Sequence, size: int) -> list[list]:
    """Yield ``items`` in consecutive chunks of at most ``size``."""
    return [list(items[start : start + size]) for start in range(0, len(items), size)]
