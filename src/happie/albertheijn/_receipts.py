"""GraphQL fetch of in-store receipt (kassabon) purchase history.

Pages the receipt list until the requested window is covered, fetches the
line items of the in-window receipts in aliased batches, resolves the POS
product ids to webshop ids in aliased batches, and enriches converted
webshop ids with the current product titles.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from happie.albertheijn._errors import AlbertHeijnError

__all__ = [
    "GRAPHQL_URL",
    "ReceiptItem",
    "enrich_product_names",
    "fetch_receipt_history",
]

GRAPHQL_URL = "https://api.ah.nl/graphql"

#: Number of receipts requested per page of the receipt list.
_PAGE_SIZE = 100
#: Receipts per aliased ``posReceiptDetails`` batch.
_DETAIL_BATCH = 50
#: Product ids per aliased ``productConvertId`` batch and per products-by-ids
#: enrichment request.
_ID_BATCH = 100

#: Webshop product endpoint used to enrich POS short names with webshop titles.
PRODUCTS_BY_IDS_URL = "https://api.ah.nl/mobile-services/product/search/v2/products"

_RECEIPTS_PAGE_QUERY = """
query FetchPosReceipts($offset: Int!, $limit: Int!) {
  posReceiptsPage(pagination: {offset: $offset, limit: $limit}) {
    posReceipts {
      id
      dateTime
      totalAmount {
        amount
      }
    }
  }
}
"""


@dataclass(frozen=True)
class ReceiptItem:
    """One in-store receipt line item.

    Attributes
    ----------
    date : date
        The calendar day of the receipt (the UTC date of its time).
    pos_id : int
        The store point-of-sale product id.
    quantity : float
        The quantity on the receipt.
    name : str
        The POS short name of the product.
    amount : float
        The amount charged for the line.
    """

    date: date
    pos_id: int
    quantity: float
    name: str
    amount: float


def fetch_receipt_history(
    http: httpx.Client, window_start: date
) -> tuple[list[ReceiptItem], dict[int, int]]:
    """Fetch in-window receipt items and their POS-to-webshop id mapping.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    window_start : date
        The first calendar day to include.

    Returns
    -------
    tuple[list[ReceiptItem], dict[int, int]]
        A pair of:

        - the in-window receipt line items, oldest receipt first;
        - the POS-to-webshop id mapping, holding only successfully
          converted ids (null and non-positive values are unresolved).

    Raises
    ------
    AlbertHeijnError
        If any request returns a status other than 200, a GraphQL
        ``errors`` payload, or an unexpected body.
    """  # noqa: DOC502, RUF100
    receipts = _window_receipts(http, window_start)
    items = _receipt_items(http, receipts)
    return items, _id_conversion(http, items)


def _window_receipts(http: httpx.Client, window_start: date) -> list[tuple[str, date]]:
    """Page the receipt list until a page reaches before the window.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    window_start : date
        The first calendar day to include.

    Returns
    -------
    list[tuple[str, date]]
        The in-window ``(receipt id, day)`` pairs, newest receipt first.

    Raises
    ------
    AlbertHeijnError
        If any page request fails or carries an unparsable receipt
        entry.
    """  # noqa: DOC502, RUF100
    receipts: list[tuple[str, date]] = []
    offset = 0
    while True:
        entries = _receipt_page(http, offset)
        if not entries:
            break
        batch, reached_before_window = _in_window_entries(entries, window_start)
        receipts.extend(batch)
        if reached_before_window:
            break
        offset += _PAGE_SIZE
    return receipts


def _receipt_page(http: httpx.Client, offset: int) -> list[dict]:
    """Fetch one page of the receipt list."""
    data = _graphql(
        http,
        _RECEIPTS_PAGE_QUERY,
        "posReceiptsPage",
        variables={"offset": offset, "limit": _PAGE_SIZE},
    )
    return (data.get("posReceiptsPage") or {}).get("posReceipts") or []


def _in_window_entries(
    entries: Sequence[dict], window_start: date
) -> tuple[list[tuple[str, date]], bool]:
    """Split one page into its in-window prefix and a window-boundary flag.

    Parameters
    ----------
    entries : Sequence[dict]
        The page entries, newest receipt first.
    window_start : date
        The first calendar day to include.

    Returns
    -------
    tuple[list[tuple[str, date]], bool]
        A pair of the in-window ``(receipt id, day)`` pairs and whether
        the page reached an entry older than the window (which ends the
        paging).
    """
    batch: list[tuple[str, date]] = []
    for entry in entries:
        day = _receipt_day(entry)
        if day < window_start:
            return batch, True
        batch.append((str(entry["id"]), day))
    return batch, False


def _receipt_items(
    http: httpx.Client, receipts: Sequence[tuple[str, date]]
) -> list[ReceiptItem]:
    """Fetch the line items of the given receipts in aliased batches."""
    items: list[ReceiptItem] = []
    for chunk in _chunked(receipts, _DETAIL_BATCH):
        receipt_ids = [receipt_id for receipt_id, _ in chunk]
        data = _graphql(http, _details_query(receipt_ids), "posReceiptDetails")
        items.extend(_batch_items(data, chunk))
    return items


def _batch_items(data: dict, chunk: Sequence[tuple[str, date]]) -> list[ReceiptItem]:
    """Read one aliased detail batch back into items, keyed by position."""
    items: list[ReceiptItem] = []
    for index, (_, day) in enumerate(chunk):
        for product in _batch_products(data, f"d{index}"):
            items.append(_receipt_item(day, product))
    return items


def _batch_products(data: dict, alias: str) -> list[dict]:
    """Return the products under one aliased receipt-detail payload."""
    details = data.get(alias)
    if not details:
        return []
    return list(details.get("products") or [])


def _id_conversion(http: httpx.Client, items: Sequence[ReceiptItem]) -> dict[int, int]:
    """Resolve the batched POS product ids in aliased batches."""
    conversion: dict[int, int] = {}
    pos_ids = sorted({item.pos_id for item in items if item.pos_id > 0})
    for chunk in _chunked(pos_ids, _ID_BATCH):
        data = _graphql(http, _convert_query(chunk), "productConvertId")
        conversion.update(_conversion_entries(data, chunk))
    return conversion


def _conversion_entries(data: dict, pos_ids: Sequence[int]) -> dict[int, int]:
    """Read one aliased conversion batch into resolved id pairs."""
    conversion: dict[int, int] = {}
    for index, pos_id in enumerate(pos_ids):
        value = data.get(f"p{index}")
        if isinstance(value, int) and value > 0:
            conversion[pos_id] = value
    return conversion


def enrich_product_names(
    http: httpx.Client, webshop_ids: Sequence[int]
) -> dict[int, str]:
    """Fetch current webshop titles for the given product ids.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    webshop_ids : Sequence[int]
        The webshop product ids to look up, in any order and with
        duplicates.

    Returns
    -------
    dict[int, str]
        The webshop id to title mapping for the ids the endpoint
        returned; ids the endpoint omits have no entry.

    Raises
    ------
    AlbertHeijnError
        If a request returns a status other than 200 or a body that is
        not a product list.
    """  # noqa: DOC502, RUF100
    names: dict[int, str] = {}
    for chunk in _chunked(list(dict.fromkeys(webshop_ids)), _ID_BATCH):
        names.update(_batch_titles(http, chunk))
    return names


def _batch_titles(http: httpx.Client, webshop_ids: Sequence[int]) -> dict[int, str]:
    """Fetch the titles the products endpoint returns for one id batch."""
    params = [("ids", str(product_id)) for product_id in webshop_ids]
    response = http.get(
        PRODUCTS_BY_IDS_URL, params=[*params, ("sortOn", "INPUT_PRODUCT_IDS")]
    )
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"Product title enrichment failed with status {response.status_code}."
        )
    return _titles_from_products(_product_list(response))


def _product_list(response: httpx.Response) -> list:
    """Return the product list of a products-by-ids response."""
    try:
        products = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(
            "Product title enrichment returned an unexpected response."
        ) from exc
    if not isinstance(products, list):
        raise AlbertHeijnError(
            "Product title enrichment returned an unexpected response."
        )
    return products


def _titles_from_products(products: Sequence) -> dict[int, str]:
    """Map products to titles, skipping the entries missing a usable id."""
    names: dict[int, str] = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        try:
            names[int(product["webshopId"])] = str(product.get("title") or "")
        except (KeyError, TypeError, ValueError):
            continue
    return names


def _graphql(
    http: httpx.Client, query: str, operation: str, variables: dict | None = None
) -> dict:
    """POST one GraphQL query and return its ``data`` payload.

    Parameters
    ----------
    http : httpx.Client
        The preconfigured client carrying the application headers and
        the user's bearer token.
    query : str
        The GraphQL query string.
    operation : str
        The operation name, used to identify the failing request in
        error messages.
    variables : dict | None
        The GraphQL variables, if the query takes any.

    Returns
    -------
    dict
        The response's ``data`` payload.

    Raises
    ------
    AlbertHeijnError
        If the response is not 200, carries a GraphQL ``errors``
        payload, or has an unexpected shape.
    """
    payload: dict[str, object] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    response = http.post(GRAPHQL_URL, json=payload)
    if response.status_code != 200:
        raise AlbertHeijnError(
            f"{operation} failed with status {response.status_code}."
        )
    return _graphql_data(response, operation)


def _graphql_data(response: httpx.Response, operation: str) -> dict:
    """Return the validated ``data`` payload of a GraphQL response."""
    body = _json_object(response, operation)
    if body.get("errors"):
        raise AlbertHeijnError(
            f"{operation} returned an error payload (status {response.status_code})."
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    return data


def _json_object(response: httpx.Response, operation: str) -> dict:
    """Parse a response body that must be a JSON object."""
    try:
        body = response.json()
    except ValueError as exc:
        raise AlbertHeijnError(f"{operation} returned an unexpected response.") from exc
    if not isinstance(body, dict):
        raise AlbertHeijnError(f"{operation} returned an unexpected response.")
    return body


def _details_query(receipt_ids: Sequence[str]) -> str:
    """Build one aliased ``posReceiptDetails`` batch query."""
    aliases = " ".join(
        f"d{index}: posReceiptDetails(id: {json.dumps(receipt_id)})"
        " { products { id quantity name price { amount } amount { amount } } }"
        for index, receipt_id in enumerate(receipt_ids)
    )
    return f"query {{ {aliases} }}"


def _convert_query(pos_ids: Sequence[int]) -> str:
    """Build one aliased ``productConvertId`` batch query."""
    aliases = " ".join(
        f"p{index}: productConvertId(sourceId: {pos_id})"
        for index, pos_id in enumerate(pos_ids)
    )
    return f"query {{ {aliases} }}"


def _receipt_day(entry: dict) -> date:
    """Extract the calendar day from a receipt page entry."""
    try:
        return datetime.fromisoformat(str(entry["dateTime"])).date()
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(
            "posReceiptsPage returned an unexpected response."
        ) from exc


def _receipt_item(day: date, product: dict) -> ReceiptItem:
    """Translate one receipt detail product into a :class:`ReceiptItem`."""
    try:
        return ReceiptItem(
            date=day,
            pos_id=int(product["id"]),
            quantity=float(product.get("quantity") or 0.0),
            name=str(product.get("name") or ""),
            amount=float((product.get("amount") or {}).get("amount") or 0.0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AlbertHeijnError(
            "posReceiptDetails returned an unexpected response."
        ) from exc


def _chunked(items: Sequence, size: int) -> Iterable[list]:
    """Split a sequence into consecutive chunks of at most a fixed size."""
    for start in range(0, len(items), size):
        yield list(items[start : start + size])
