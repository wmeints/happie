# Tasks: add-purchase-frequency-tool

## 1. Model and pure aggregation

- [x] 1.1 Add the frozen `PurchaseStat` dataclass (product key, name,
  total quantity, purchase-day count, total spend, window start date, dense
  per-day count tuple) to `src/happie/albertheijn/_models.py` and export it
  from `src/happie/albertheijn/__init__.py` alongside `Product`.
  Verify: `uv run python -c "from happie.albertheijn import PurchaseStat"`
  succeeds and `ruff check` / `ruff format --check` are clean.
- [x] 1.2 Write failing tests in `tests/albertheijn/test_history.py` for the
  pure aggregation (cross-source merge per key, POS fallback key, dense
  array with one entry per window day, window-boundary exclusion, distinct
  day counting, spend totals, sorting by total quantity, empty input), then
  implement `aggregate` in `src/happie/albertheijn/_history.py` with no I/O.
  Verify: `uv run pytest tests/albertheijn/test_history.py` passes.

## 2. Receipt source (GraphQL)

- [x] 2.1 Write failing tests in `tests/albertheijn/test_receipts.py`
  (monkeypatched transport, following `test_client.py`'s pattern) for the
  receipt-page fetch, the aliased detail batch, and the aliased
  `productConvertId` batch, including header/token usage, chunking at 50
  receipts and 100 ids, and error propagation without token leakage.
- [x] 2.2 Implement `src/happie/albertheijn/_receipts.py`: page
  `posReceiptsPage` until the oldest page entry predates the window start
  (or the page is empty), fetch `posReceiptDetails` for in-window receipts
  in aliased batches of 50, and resolve POS ids via `productConvertId`
  aliased batches of 100 (non-positive or null values are unresolved),
  returning `(receipt_date, pos_id, quantity, name, amount)` records plus
  the id mapping.
  Verify: `uv run pytest tests/albertheijn/test_receipts.py` passes.

## 3. Order source (REST)

- [x] 3.1 Write failing tests in `tests/albertheijn/test_orders.py`
  (monkeypatched transport) for the order-summary fetch (filter to
  `state == "DELIVERED"` and `deliveryDate` inside the window) and the
  per-order details fetch, including header/token usage and error
  propagation without token leakage.
- [x] 3.2 Implement `src/happie/albertheijn/_orders.py`: fetch
  `GET /mobile-services/order/v1/summaries?sortBy=DEFAULT`, keep only
  delivered in-window orders, fetch each order's
  `details-grouped-by-taxonomy`, and return `(delivery_date, webshop_id,
  title, quantity, amount)` records.
  Verify: `uv run pytest tests/albertheijn/test_orders.py` passes.

## 4. Name enrichment

- [x] 4.1 Write failing tests (extending `test_receipts.py` or a shared
  module test) for the batched products-by-ids enrichment: one REST request
  per chunk of 100 ids against
  `GET /mobile-services/product/search/v2/products` with
  `sortOn=INPUT_PRODUCT_IDS`, titles used for returned ids, POS names kept
  for ids the endpoint omits, error propagation on non-2xx.
- [x] 4.2 Implement the enrichment helper in
  `src/happie/albertheijn/_receipts.py` (or `_history.py` if kept I/O-free
  elsewhere).
  Verify: `uv run pytest tests/albertheijn/` passes.

## 5. Client orchestration

- [x] 5.1 Write failing orchestration tests in
  `tests/albertheijn/test_client.py` for
  `AlbertHeijnClient.get_purchase_history(days=90)`: window computation,
  both record streams flowing into `PurchaseStat` results, merged keys
  across sources, `AuthenticationError` before any request when no usable
  token exists, and a failed sub-request raising `AlbertHeijnError` with
  the status and no partial result.
- [x] 5.2 Implement `get_purchase_history` in
  `src/happie/albertheijn/_client.py`: compute `window_start` (today in UTC
  minus `days - 1`), fetch receipt and order records, key receipt records
  via the conversion mapping with the `pos<id>` fallback, enrich receipt
  names, convert records to the unified shape, and call the pure
  aggregation from `_history.py`.
  Verify: `uv run pytest tests/albertheijn/test_client.py` passes.

## 6. MCP tool

- [x] 6.1 Write failing tests in `tests/server/test_server.py` mirroring the
  `search_products` tool tests: default 90-day window, `limit` trimming to
  the top total quantities, empty window returns an empty list, and a
  failing call reports the error while the server keeps running.
- [x] 6.2 Add the `purchase_frequency(days: int = 90, limit: int | None =
  None)` tool to `src/happie/server/__init__.py` as a thin wrapper around
  `AlbertHeijnClient.get_purchase_history`, applying `limit` to the
  already-quantity-sorted result.
  Verify: `uv run pytest tests/server/test_server.py` passes.

## 7. Verification

- [x] 7.1 Run the full test suite and linters:
  `uv run pytest` and `ruff check src tests` plus `ruff format --check
  src tests`; all green.
- [x] 7.2 Smoke-test against the live API with a stored token: call
  `get_purchase_history(90)` and the MCP `purchase_frequency` tool, confirm
  the result contains in-store and webshop products, dense per-day arrays
  aligned to the reported window start, and a request count of roughly 15.
  Verify: the printed top statistics match manual spot-checks of recent
  receipts and orders.
