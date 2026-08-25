# Tasks: sparse-purchase-histogram

## 1. Model and pure aggregation

- [x] 1.1 Update the frozen `PurchaseStat` dataclass in
  `src/happie/albertheijn/_models.py`: remove the `purchase_days` and
  `window_start` fields and replace `daily_counts: tuple[float, ...]` with
  `histogram: tuple[tuple[date, float], ...]` (one `(date, total quantity)`
  entry per purchased day, date-ascending); rewrite the numpy-style
  `Attributes` docstring to describe the sparse histogram and no longer
  mention the dropped fields. The package `__init__.py` export is unchanged.
  Verify: `uv run python -c "from happie.albertheijn import PurchaseStat"`
  succeeds and `ruff check` / `ruff format --check` are clean.
- [x] 1.2 Rewrite the pure-aggregation tests in
  `tests/albertheijn/test_history.py` for the sparse histogram and make them
  fail first: one entry per purchased day only (no entries for unpurchased
  days), same-day quantities summed into a single entry, entries ordered by
  date, empty histogram when nothing falls in the window, window-boundary
  exclusion, spend totals, cross-source merge per key, the `pos`/`wi`
  fallback-key rule, sorting by total quantity, and that the number of
  histogram entries equals the number of distinct purchase days. Then update
  `aggregate` in `src/happie/albertheijn/_history.py` to accumulate into a
  `dict[date, float]` (keeping the window-boundary filter and the
  by-total-quantity sort) and build `histogram = tuple(sorted(by_day.items()))`,
  and rewrite its module/function docstring to drop the dense-array wording.
  Verify: `uv run pytest tests/albertheijn/test_history.py` passes.

## 2. Client orchestration and MCP tool

- [x] 2.1 Update
  `tests/albertheijn/test_client.py::test_purchase_history_merges_receipt_and_order_records`
  to assert the sparse histogram instead of the dense array: the merged
  product carries a two-entry histogram with the correct dates and summed
  quantities, and the assertions on `purchase_days`, `window_start`, and
  `daily_counts` are removed. No change is expected in
  `src/happie/albertheijn/_client.py` (it only computes the window and
  delegates to `aggregate`).
  Verify: `uv run pytest tests/albertheijn/test_client.py` passes.
- [x] 2.2 Update the `purchase_frequency` tool docstring in
  `src/happie/server/__init__.py` to describe the sparse, date-stamped
  histogram and stop describing the dropped fields; update the `_stat` helper
  and any assertions in `tests/server/test_server.py` from `daily_counts` /
  `purchase_days` / `window_start` to the new `histogram` shape (a
  date-stamped tuple, not a dense list).
  Verify: `uv run pytest tests/server/test_server.py` passes.

## 3. Verification

- [x] 3.1 Run the full test suite and linters: `uv run pytest`,
  `ruff check src tests`, and `ruff format --check src tests`; all green.
- [x] 3.2 Smoke-test against the live API with a stored token: call
  `get_purchase_history(90)` and the MCP `purchase_frequency` tool, and
  confirm the result still contains in-store and webshop products with a
  sparse, date-stamped histogram (one entry per purchased day, no zero
  padding) and that the payload no longer carries `daily_counts`,
  `purchase_days`, or `window_start`.
  Verify: the printed top statistics' histograms match manual spot-checks of
  recent receipts and orders.
