# Proposal: add-purchase-frequency-tool

## Why

The architecture's third goal is "Provide access to the ordering history to
retrieve past purchases so we can optimize the shopping list", but so far only
the product search endpoint is implemented. An MCP agent planning a weekly
shopping list needs to know what the user actually buys and how often; a
per-product purchase-frequency histogram over a recent window (default 90
days) is the direct input for that.

## What Changes

- The Albert Heijn API client gains a purchase-history capability:
  `AlbertHeijnClient.get_purchase_history(days=90)` returns, for every unique
  product purchased in the window, its total quantity, the number of distinct
  purchase days, total spend, and a dense per-day purchase count covering the
  whole window. It merges two verified data sources:
  - In-store receipts (kassabon) via GraphQL `posReceiptsPage`,
    `posReceiptDetails` (batched with aliased fields), and
    `productConvertId` for POS-to-webshop id conversion.
  - Webshop delivery orders via REST `GET /mobile-services/order/v1/summaries`
    (filtered to delivered orders) and
    `GET /mobile-services/order/v1/<orderId>/details-grouped-by-taxonomy`.
- A new frozen `PurchaseStat` model in `happie.albertheijn` (product key,
  name, totals, window start, dense per-day counts), exported alongside
  `Product`.
- The MCP server gains a `purchase_frequency` tool (window in days, optional
  result limit) that returns the `PurchaseStat` list, sorted by total
  quantity.
- No CLI commands and no authentication changes: the existing stored bearer
  token and the existing application header set are accepted by both the
  GraphQL and REST endpoints.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `albertheijn`: the client must fetch and merge in-store receipt history and
  webshop order history, convert POS product ids to webshop ids with a
  documented fallback, and aggregate both into per-product dense
  day-by-day purchase counts for a requested time window.
- `server`: the server must expose a `purchase_frequency` tool returning the
  per-product purchase statistics for a requested time window.
