# Design: sparse-purchase-histogram

## Context

The purchase-history tool (added 2026-08-24) returns a dense per-product
histogram. See proposal.md for the motivation. The current shape and the
code paths it spans:

- `src/happie/albertheijn/_models.py` — frozen `PurchaseStat` dataclass with
  `key`, `name`, `total_quantity`, `purchase_days`, `total_spend`,
  `window_start: date`, and `daily_counts: tuple[float, ...]` (one entry per
  window day, zero where nothing was bought).
- `src/happie/albertheijn/_history.py` — pure `aggregate(records,
  window_start, days)`: for each product key it fills a fixed-length
  `[0.0] * days` list indexed by `(record.day - window_start).days`, counts
  `purchase_days` as the number of non-zero slots, and packages the dense
  tuple.
- `src/happie/albertheijn/_client.py` — `get_purchase_history(days)` computes
  `window_start` and delegates to `aggregate`; no change needed here except
  that the result shape changes.
- `src/happie/server/__init__.py` — the `purchase_frequency` tool docstring
  describes the dense array and the window start.
- Tests: `tests/albertheijn/test_history.py`,
  `tests/albertheijn/test_client.py`, `tests/server/test_server.py` all assert
  on `daily_counts`, `purchase_days`, and `window_start`.

Two facts constrain the design. First, `PurchaseStat` already carries a
`date` field (`window_start`), so serialising `datetime.date` through
FastMCP/pydantic into the MCP tool's JSON output is already proven — the
sparse histogram needs no new serialisation path. Second, this tool was added
a day ago and has no external consumers, so the return-shape change is a
clean cutover rather than a compatibility migration.

## Goals / Non-Goals

**Goals:**

- Replace the dense `daily_counts` array with a sparse, date-stamped
  histogram: one entry per purchased day, each entry carrying that day's
  date and that day's summed quantity, ordered by date ascending, empty when
  nothing was purchased.
- Drop the two now-redundant fields (`purchase_days`, `window_start`) so the
  model has no derived-duplicate state and no alignment anchor.
- Keep cross-source merging, window-boundary filtering, and the
  by-total-quantity sort untouched.

**Non-Goals:**

- No change to how records are fetched, keyed, name-enriched, or filtered in
  `_receipts.py` / `_orders.py`; the unified `PurchaseRecord` shape is
  unchanged.
- No change to the tool's `days`/`limit` parameters or to the top-level
  sort order of the returned statistics.
- No caching, no new endpoint, no timezone handling beyond the existing
  UTC-vs-local day convention.

## Decisions

### 1. Histogram entry type: `(date, float)` tuple, not a nested dataclass

The field becomes `histogram: tuple[tuple[date, float], ...]`. Each element
is a two-tuple `(day, quantity)`. This matches the requested shape directly
("a date ... and then the total count for that date") and keeps the model
to a single dataclass. A nested frozen `PurchaseDay(date, quantity)`
dataclass was considered and rejected: it buys little for a two-field value
and adds a second public type to export from the package `__init__`, with no
readability win over a documented tuple.

### 2. Aggregation accumulator: day-keyed dict instead of a dense list

`aggregate` switches its per-key accumulator from a fixed-length `[0.0] *
days` list to a `dict[date, float]` that maps each purchase day to that day's
summed quantity. The window-boundary filter
(`0 <= (record.day - window_start).days < days`) is kept — it is what
excludes out-of-window records. After the loop, the histogram is
`tuple(sorted(entry["by_day"].items()))` (dict items are `(date, quantity)`,
and sorting gives date-ascending order). `total_quantity`, `total_spend`,
and the longest-name rule are unchanged.

### 3. `aggregate` signature: drop the now-unused dense-array coupling

`aggregate(records, window_start, days)` still needs `window_start` and
`days` for the window-boundary filter, so the signature is unchanged. Only
the internal representation and the `PurchaseStat` construction change: no
more `purchase_days` count and no more `window_start` pass-through. The
returned statistics carry `key`, `name`, `total_quantity`, `total_spend`,
and `histogram`.

### 4. Public model shape

`PurchaseStat` (frozen) becomes:

```python
key: str
name: str
total_quantity: float
total_spend: float
histogram: tuple[tuple[date, float], ...]
```

Exported from `happie.albertheijn.__init__` exactly as before (still
`PurchaseStat`; no new public symbol). `purchase_days` is intentionally not
kept: it is `len(stat.histogram)`, and re-exposing a derivable value would be
the "weightless state" this change is meant to remove.

### 5. Tool docstring and spec alignment

The `purchase_frequency` docstring, the `albertheijn` "Purchase history
aggregation" requirement, and the `server` "Purchase frequency tool"
requirement are all updated to describe the sparse, date-stamped histogram
and the two dropped fields (the spec deltas are in this change's `specs/`
directory).
The `albertheijn` delta is a `MODIFIED` requirement. OpenSpec refuses to drop
a scenario in a `MODIFIED` block, so the existing scenario title
"Dense per-day counts cover the whole window" is preserved verbatim and its
body reworded to describe the sparse behaviour; the now-inaccurate title can
be tidied by a direct edit to the main spec after archive.

## Risks / Trade-offs

- **Breaking change to the tool's JSON output** → The `purchase_frequency`
  tool is a day old with no external consumers; the cutover is clean. The
  MCP client-visible fields go from `{key, name, total_quantity,
  purchase_days, total_spend, window_start, daily_counts}` to `{key, name,
  total_quantity, total_spend, histogram}`.
- **Clients that wanted the purchase-day count or the window start** → Both
  are trivially derivable: `purchase_days == len(histogram)` and
  `window_start == today - (days - 1)` (the caller already knows `days`).
  Documented in the proposal's "What Changes" so no data is silently lost.
- **Payload size** → Strictly smaller: a 90-day window no longer ships a
  90-element array per product; only the actually-purchased days are sent. No
  new risk.
- **Date serialisation through the tool** → `datetime.date` inside the tuple
  is already serialised by the existing `window_start: date` field, so
  FastMCP/pydantic handling is proven; no new code path.
