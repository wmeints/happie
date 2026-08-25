# Proposal: sparse-purchase-histogram

## Why

The purchase-history tool currently returns a dense per-day histogram:
`PurchaseStat.daily_counts` is one float per window day, zero where nothing
was bought. For a 90-day window that is a 90-element array per product,
almost entirely zeros for most items, and the client must hold on to
`window_start` just to map array indexes back to calendar dates. A sparse
histogram — one entry per day the product was actually purchased, each entry
carrying its own date and that day's total quantity — is smaller, has no
padding, and is self-describing (no separate alignment anchor needed).

## What Changes

- **BREAKING**: `PurchaseStat` replaces the dense `daily_counts:
  tuple[float, ...]` field with a sparse `histogram: tuple[tuple[date,
  float], ...]` — one `(date, total quantity)` entry per calendar day the
  product was actually purchased, ordered by date ascending, and empty when
  the product was never purchased in the window.
- **BREAKING**: `PurchaseStat` drops two fields that the dense design
  required and the sparse design makes redundant:
  - `purchase_days` (the count of distinct purchase days — now simply the
    number of histogram entries, `len(histogram)`).
  - `window_start` (the window's first calendar day — used only to align the
    dense array to dates; now each histogram entry already carries its date).
- The pure aggregation in `happie.albertheijn._history` buckets quantities
  per calendar day into a dict keyed by the purchase day (instead of a
  fixed-length dense list) and builds the sparse histogram by sorting the
  purchased days. Window-boundary filtering and cross-source merging are
  unchanged.
- The `purchase_frequency` MCP tool and the `albertheijn` / `server` specs
  update to the sparse, date-stamped histogram and the trimmed
  `PurchaseStat` shape.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `albertheijn`: the purchase-history method now returns one statistic per
  purchased product carrying a sparse, date-stamped histogram (one `(date,
  quantity)` entry per purchased day, ordered by date) instead of a dense
  per-day array, and the `PurchaseStat` model no longer exposes
  `purchase_days` or `window_start`.
- `server`: the `purchase_frequency` tool now returns the trimmed
  `PurchaseStat` whose per-product per-day detail is the sparse,
  date-stamped histogram.
