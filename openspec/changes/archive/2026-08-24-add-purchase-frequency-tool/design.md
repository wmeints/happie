# Design: add-purchase-frequency-tool

## Context

`happie.albertheijn` currently wraps one endpoint: the product search REST
call, with inline `httpx` in `AlbertHeijnClient.search_products`, raw-to-model
translation in `_models.py`, and the bearer token obtained lazily via
`happie.auth.get_access_token`. Tests monkeypatch the transport (see
`tests/albertheijn/test_client.py`). This change adds two more API surfaces
and a pure aggregation step.

All endpoint facts below were verified live against `api.ah.nl` with the
existing stored token and the client's existing header set
(`User-Agent: Appie/8.22.3`, `x-application: AHWEBSHOP`, JSON headers):

- GraphQL at `POST https://api.ah.nl/graphql` accepts those headers plus the
  bearer token. Server-side introspection is disabled.
- `posReceiptsPage(pagination: {offset, limit})` → receipts with `id`,
  `dateTime` (ISO-8601 UTC, e.g. `2026-08-22T07:23:00.000Z`),
  `totalAmount.amount`. History verified back more than a year; 100 receipts
  per page.
- `posReceiptDetails(id: String!)` → `products` with POS `id`, `quantity`,
  `name` (POS short name, e.g. `KAISERBROOD`), `price` (nullable),
  `amount.amount`; plus `discounts` and `payments`.
- `productConvertId(sourceId: Int)` → webshop product id, or a non-positive /
  null value when unresolved. Both queries support aliased batching
  (`p0: productConvertId(sourceId: 624318) p1: ...` in one request).
- `GET /mobile-services/order/v1/summaries?sortBy=DEFAULT` → list of up to
  24 orders with `orderId`, `deliveryDate` (`YYYY-MM-DD`), `state`
  (`DELIVERED`, `CONFIRMED`, `CANCELLED`). The GraphQL alternative
  `orderFulfillments(status: CLOSED)` caps at 10 orders, so the REST list is
  the source.
- `GET /mobile-services/order/v1/<orderId>/details-grouped-by-taxonomy` →
  `orderState`, `deliveryDate`, and `groupedProductsInTaxonomy[].
  orderedProducts[]` with `quantity` and `product` (`webshopId`, `title`,
  `brand`, prices).
- `GET /mobile-services/product/search/v2/products?ids=<id>&ids=<id>&sortOn=INPUT_PRODUCT_IDS`
  → full product objects for a batch of webshop ids (used to enrich POS
  names).

## Goals / Non-Goals

**Goals:**

- One deep client method `AlbertHeijnClient.get_purchase_history(days=90)`
  that hides pagination, aliased batching, the two source protocols, and id
  conversion, returning `list[PurchaseStat]`.
- One thin MCP tool `purchase_frequency(days=90, limit=None)` mirroring the
  existing `search_products` tool.
- A dense per-day histogram per product (exactly one count per window day)
  plus aggregate fields, so both machine analysis and LLM summarization work
  from the same result.
- A bounded request budget: roughly 15 HTTP requests for a 90-day window
  (2–3 receipt requests, 1 summaries request, ~10 order-detail requests,
  1–2 enrichment requests).
- Everything unit-testable without a network through the existing
  monkeypatched-transport seam, with the pure aggregation tested without any
  HTTP at all.

**Non-Goals:**

- No order placement or modification — the architecture forbids the MCP
  server from completing purchases.
- No separate MCP tools for raw receipt or order listings; the only new tool
  is the frequency view.
- No history beyond what the API exposes (order summaries cap at 24 entries;
  no pagination parameter was found on that endpoint).
- No timezone-aware day bucketing beyond the documented UTC-vs-local
  convention; no caching of fetched history.

## Decisions

### 1. Source selection

In-store purchases come from the GraphQL `posReceipts*` operations; webshop
purchases come from the REST order endpoints. `orderFulfillments(status:
CLOSED)` was rejected because it returned only 10 orders where the REST
summaries endpoint returned 24 with older history;
`orderFulfillmentsByDateRange` was rejected because it returns a single
`Fulfillment`, not a list; `orderExpandFulfillments` was rejected because its
arguments are unknown and the single-order variant returns subgraph errors.
The REST per-order details endpoint is the same one the Go reference client
and the existing ah-mcp project use for past orders.

### 2. Module layout

One module per concern, matching the existing private-submodule pattern:

- `_receipts.py` (new) — GraphQL I/O only: page the receipt list until the
  window is covered, fetch receipt details in one aliased batch query per
  chunk of 50 receipts, fetch `productConvertId` in one aliased batch query
  per chunk of 100 unique POS ids. Returns plain records:
  `(receipt_date, pos_id, quantity, name, amount)` plus the
  `pos_id -> webshop_id` mapping.
- `_orders.py` (new) — REST I/O only: fetch the order summaries, filter to
  `state == "DELIVERED"` with `deliveryDate` inside the window, then fetch
  each order's details. Returns `(delivery_date, webshop_id, title,
  quantity, amount)` records.
- `_history.py` (new) — pure aggregation, no I/O: given unified records
  `(day, key, name, quantity, amount)`, the window start, and the window
  length, build the `PurchaseStat` list: merge records per key, keep the
  longest known name, fill the dense per-day array, count distinct purchase
  days, sum spend, and sort by total quantity descending.
- `_models.py` — gains the frozen `PurchaseStat` dataclass, exported through
  the package `__init__.py` alongside `Product`.
- `_client.py` — gains `get_purchase_history(days: int = 90)`: computes the
  window (`window_start = today_utc - (days - 1)` days), fetches both
  record streams, enriches names (decision 4), converts receipt records to
  unified keys, and delegates to the pure aggregation. Any failure in the
  pipeline raises `AlbertHeijnError` (or `AuthenticationError` before any
  request) — no partial results.

### 3. Product keying

The webshop id is the canonical key: receipt POS ids are converted with
`productConvertId` (non-positive or null values count as unresolved);
unresolved items are keyed `pos<pos_id>` and stay separate from any webshop
key. Webshop order items are keyed `wi<webshop_id>` directly. The same
product bought in-store and online therefore merges into one statistic; a
POS item with no conversion never merges incorrectly.

### 4. Name enrichment

Receipt items carry only POS short names. After the conversion step, the
client issues one batched "products by ids" request (chunked at 100 ids) for
all converted receipt ids and uses the returned titles as the names for
those products; ids the endpoint omits keep their POS name. This makes
merged statistics show one clean name instead of `KAISERBROOD`/
"AH Kaiserbrood" split across sources.

### 5. Day bucketing

Window days are calendar days in UTC. A receipt's day is the date part of
its `dateTime` (the API returns UTC); a webshop order's day is its
`deliveryDate` (a local Netherlands calendar date). Purchases within an
hour of midnight can land on the neighbouring day in one source; accepted as
documented behaviour rather than adding per-source timezone conversion.

### 6. Error handling

All-or-nothing: a non-2xx response, a GraphQL `errors` payload for the
requested fields, or an unexpected body shape raises `AlbertHeijnError`
naming the failing request and status; `AuthenticationError` propagates
before any request when no usable token exists. Error text never includes
the token, consistent with the existing client behaviour.

### 7. Testing

- Pure aggregation tests in `tests/albertheijn/test_history.py`: cross-source
  merge, POS fallback key, dense array shape and alignment, window
  exclusion, cancelled-order exclusion, empty window, sorting.
- I/O tests in `tests/albertheijn/test_receipts.py` and
  `test_orders.py` through the monkeypatched transport: correct URLs,
  headers, and token usage; aliased-batch chunking; filtering by state and
  window; error propagation without token leakage.
- `AlbertHeijnClient.get_purchase_history` orchestration tests with the
  transport seam: end-to-end record flow into `PurchaseStat` results.
- `tests/server/test_server.py` gains `purchase_frequency` cases mirroring
  the `search_products` tool tests (default window, limit, empty result,
  failure keeps the server running).

## Risks / Trade-offs

- **Order-history cap**: the summaries endpoint returns at most ~24 orders
  and no pagination parameter was found. A user with more than 24 orders in
  the window (roughly 3+ deliveries per week for 90 days) silently loses
  the oldest ones. Accepted: the window's oldest visible date can be checked
  against the cap at runtime, but no API exists to go further; documented in
  the spec as a data-source limitation.
- **Large dense results**: for a ~300-product account the full 90-day result
  is a large JSON payload. Mitigations: the tool's `limit` parameter, the
  aggregate fields (`total_quantity`, `purchase_days`) that make per-product
  reasoning possible without the arrays, and sorting by total quantity so
  the head of the result is the interesting part.
- **Undocumented API drift**: the endpoint contract was reverse-engineered
  (introspection disabled). The queries are kept minimal and mirror the Go
  reference client's proven shapes; GraphQL `errors` payloads are surfaced
  as `AlbertHeijnError` so drift fails loudly instead of producing wrong
  histograms.
- **Request volume vs rate limiting**: ~15 requests per tool call, aliased
  batches keep it near the floor; unknown server-side rate limits could
  still affect heavy polling, which the read-only use case does not do.
