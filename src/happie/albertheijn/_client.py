"""Client for the Albert Heijn product search and purchase-history APIs.

Attaches the required application headers and the user's bearer token to
every request. The product search endpoint is wrapped directly here; the
purchase-history endpoints live in the ``_receipts``, ``_orders``, and
``_history`` submodules, orchestrated by
:meth:`AlbertHeijnClient.get_purchase_history`.
"""

from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime, timedelta

import httpx

from happie.albertheijn._bonus import (
    BonusGroup,
    fetch_bonus_products,
    fetch_bonus_promotions,
    fetch_bonus_section,
    fetch_national_categories,
)
from happie.albertheijn._errors import AlbertHeijnError
from happie.albertheijn._history import PurchaseRecord, aggregate
from happie.albertheijn._models import Product, PurchaseStat, product_from_api
from happie.albertheijn._orders import fetch_order_history
from happie.albertheijn._receipts import enrich_product_names, fetch_receipt_history
from happie.auth import get_access_token

__all__ = ["SEARCH_URL", "AlbertHeijnClient"]

SEARCH_URL = "https://api.ah.nl/mobile-services/product/search/v2"

#: Application headers required by api.ah.nl, applied to every request.
_APP_HEADERS = {
    "User-Agent": "Appie/8.22.3",
    # The product search endpoint rejects requests without an application
    # context (500 "Can not find application"); `x-application` alone suffices.
    "x-application": "AHWEBSHOP",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class AlbertHeijnClient:
    """Client for the Albert Heijn product search endpoint.

    The client takes no arguments and obtains its bearer token lazily at
    request time, so constructing it never touches the network or the token
    store.
    """

    def get_purchase_history(self, days: int = 90) -> list[PurchaseStat]:
        """Summarise the user's purchases over a trailing window of days.

        Merges in-store receipt items and delivered webshop order items
        into one statistic per product, with a dense per-day purchase
        quantity covering the whole window. Products bought in-store and
        online under the same webshop id merge into one statistic;
        receipt items without a webshop conversion stay separate under
        their point-of-sale id.

        Parameters
        ----------
        days : int
            The length of the window in days, ending today. Defaults
            to 90.

        Returns
        -------
        list[PurchaseStat]
            One :class:`PurchaseStat` per purchased product, sorted by
            total quantity descending.

        Raises
        ------
        AuthenticationError
            If no usable stored token exists. No request is made in
            that case.
        AlbertHeijnError
            If any purchase-history request fails. No partial result
            is returned.
        """  # noqa: DOC502, RUF100
        token = get_access_token()
        window_start = datetime.now(UTC).date() - timedelta(days=days - 1)
        http = httpx.Client(
            headers={**_APP_HEADERS, "Authorization": f"Bearer {token}"}
        )
        try:
            receipt_items, conversion = fetch_receipt_history(http, window_start)
            order_items = fetch_order_history(http, window_start, days)
            converted_ids = sorted(set(conversion.values()))
            titles = enrich_product_names(http, converted_ids) if converted_ids else {}
            records = [
                PurchaseRecord(
                    day=item.date,
                    key=(
                        f"wi{conversion[item.pos_id]}"
                        if item.pos_id in conversion
                        else f"pos{item.pos_id}"
                    ),
                    name=titles.get(conversion.get(item.pos_id), item.name),
                    quantity=item.quantity,
                    amount=item.amount,
                )
                for item in receipt_items
            ]
            records.extend(
                PurchaseRecord(
                    day=item.date,
                    key=f"wi{item.webshop_id}",
                    name=item.name,
                    quantity=item.quantity,
                    amount=item.amount,
                )
                for item in order_items
            )
            return aggregate(records, window_start, days)
        finally:
            http.close()

    def search_products(self, query: str, limit: int = 10) -> list[Product]:
        """Search the Albert Heijn assortment for a query.

        Parameters
        ----------
        query : str
            The search term.
        limit : int
            The maximum number of products to return, in the API's
            relevance order. Defaults to 10.

        Returns
        -------
        list[Product]
            The matching products, at most `limit` of them.

        Raises
        ------
        AuthenticationError
            If no usable stored token exists. No request is made in
            that case.
        AlbertHeijnError
            If the endpoint returns a status other than 200, or a 200
            with an unexpected body.
        """  # noqa: DOC503, RUF100
        token = get_access_token()
        http = httpx.Client()
        try:
            response = http.get(
                SEARCH_URL,
                params={
                    "query": query,
                    "page": "0",
                    "size": str(limit),
                    "sortOn": "RELEVANCE",
                },
                headers={**_APP_HEADERS, "Authorization": f"Bearer {token}"},
            )
        finally:
            http.close()

        if response.status_code != 200:
            raise AlbertHeijnError(
                f"Product search failed with status {response.status_code}."
            )
        try:
            products = response.json()["products"]
            # The API may return slightly more products than requested
            # (injected sponsored products); keep only the first ``limit``.
            return [product_from_api(product) for product in products][:limit]
        except (KeyError, TypeError, ValueError) as exc:
            raise AlbertHeijnError(
                "Product search returned an unexpected response."
            ) from exc

    def get_bonus_offers(self) -> list[Product]:
        """Return the products on bonus during the current bonus period.

        Walks every national bonus category's section and expands each
        multi-product bonus group into its concrete products. A product
        listed in more than one category, or both in a category section
        and inside a group, is returned exactly once, first occurrence
        first, keeping the API's category order. Folder products the API
        does not flag as bonus are dropped.

        Returns
        -------
        list[Product]
            One :class:`Product` per on-bonus product, each flagged as
            being on bonus with the deal text as its bonus mechanism. An
            empty list when the current bonus period has no products in
            any national category.

        Raises
        ------
        AuthenticationError
            If no usable stored token exists. No request is made in
            that case.
        AlbertHeijnError
            If the bonus metadata, any category-section, any bonus-group
            resolution, or any bonus-product request fails. No partial
            result is returned.
        """  # noqa: DOC502, RUF100
        token = get_access_token()
        http = httpx.Client(
            headers={**_APP_HEADERS, "Authorization": f"Bearer {token}"}
        )
        try:
            period_start, categories = fetch_national_categories(http)
            if not categories:
                return []
            entries = _fetch_bonus_entries(http, period_start, categories)
            promotions = _resolve_promotions(http, entries)
            group_ids = _group_product_ids(entries, promotions)
            raw_by_id = fetch_bonus_products(http, group_ids) if group_ids else {}
            return _products_from_raws(
                _expand_bonus_entries(entries, promotions, raw_by_id)
            )
        finally:
            http.close()


def _fetch_bonus_entries(
    http: httpx.Client, period_start: str, categories: Sequence[str]
) -> list[dict | BonusGroup]:
    """Fetch every category's bonus section as one ordered entry list.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    period_start : str
        The active bonus period's start date, as the metadata endpoint
        formats it.
    categories : Sequence[str]
        The national bonus categories, in the metadata's order.

    Returns
    -------
    list[dict | BonusGroup]
        The section entries of every category, in category order and,
        within a category, in the section's own order.

    Raises
    ------
    AlbertHeijnError
        If any category-section request fails.
    """  # noqa: DOC502, RUF100
    sections = [
        fetch_bonus_section(http, period_start, category) for category in categories
    ]
    return [entry for section in sections for entry in section]


def _resolve_promotions(
    http: httpx.Client, entries: Sequence[dict | BonusGroup]
) -> dict[str, list[int]]:
    """Resolve the bonus groups' segments, skipping the request when none.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    entries : Sequence[dict | BonusGroup]
        The flattened section entries, in order.

    Returns
    -------
    dict[str, list[int]]
        The segment id to product id mapping, or an empty mapping when
        no section entry is a bonus group.

    Raises
    ------
    AlbertHeijnError
        If the bonus-promotions request fails.
    """  # noqa: DOC502, RUF100
    if not any(isinstance(entry, BonusGroup) for entry in entries):
        return {}
    return fetch_bonus_promotions(http)


def _first_seen(values: Iterable[int]) -> list[int]:
    """Return the given values deduplicated in first-seen order.

    Parameters
    ----------
    values : Iterable[int]
        The values, possibly with duplicates.

    Returns
    -------
    list[int]
        The values with each distinct value kept at its first position.
    """
    seen: set[int] = set()
    unique: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _group_product_ids(
    entries: Sequence[dict | BonusGroup], promotions: dict[str, list[int]]
) -> list[int]:
    """Collect the product ids the bonus groups expand to.

    Parameters
    ----------
    entries : Sequence[dict | BonusGroup]
        The flattened section entries, in order.
    promotions : dict[str, list[int]]
        The segment id to product id mapping.

    Returns
    -------
    list[int]
        The resolved product ids in first-seen order: each group
        contributes its segment's ids in the promotions' order, a
        product in more than one group is listed once, and groups whose
        segment has no entry contribute nothing.
    """
    return _first_seen(
        product_id
        for entry in entries
        if isinstance(entry, BonusGroup)
        for product_id in promotions.get(entry.segment_id, [])
    )


def _expand_bonus_entries(
    entries: Sequence[dict | BonusGroup],
    promotions: dict[str, list[int]],
    raw_by_id: dict[int, dict],
) -> Iterator[dict]:
    """Yield the raw product objects behind the section entries.

    Parameters
    ----------
    entries : Sequence[dict | BonusGroup]
        The flattened section entries, in order.
    promotions : dict[str, list[int]]
        The segment id to product id mapping.
    raw_by_id : dict[int, dict]
        The raw product objects the product lookup returned.

    Yields
    ------
    dict
        Plain entries as-is; each bonus group yields its resolved
        products in the promotions' order, skipping ids the product
        lookup did not return.
    """
    for entry in entries:
        if isinstance(entry, BonusGroup):
            for product_id in promotions.get(entry.segment_id, []):
                if product_id in raw_by_id:
                    yield raw_by_id[product_id]
        else:
            yield entry


def _products_from_raws(raws: Iterable[dict]) -> list[Product]:
    """Build the bonus products from raw product objects.

    Parameters
    ----------
    raws : Iterable[dict]
        The raw product objects in emission order.

    Returns
    -------
    list[Product]
        One product per distinct on-bonus webshop id, first occurrence
        first; products the API does not flag as bonus contribute
        nothing.

    Raises
    ------
    AlbertHeijnError
        If a raw object has an unexpected shape.
    """
    products: list[Product] = []
    emitted: set[int] = set()
    for raw in raws:
        try:
            product = product_from_api(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise AlbertHeijnError(
                "Bonus offers returned an unexpected response."
            ) from exc
        if not product.is_bonus:
            continue
        if product.webshop_id in emitted:
            continue
        emitted.add(product.webshop_id)
        products.append(product)
    return products
