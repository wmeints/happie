# Design: add-bonus-offers-tool

## Context

`happie.albertheijn` wraps the product-search REST call and the
purchase-history endpoints (REST + GraphQL), with raw-to-model translation
in `_models.py`, private submodules per endpoint concern, and the bearer
token obtained lazily via `happie.auth.get_access_token`. Tests monkeypatch
the `httpx` transport seam.

All endpoint facts below were verified live against `api.ah.nl` with the
existing stored token and the client's existing header set
(`User-Agent: Appie/8.22.3`, `x-application: AHWEBSHOP`, JSON headers):

- `GET /mobile-services/bonuspage/v3/metadata` → `periods[]` with
  `bonusStartDate`/`bonusEndDate` (plain `YYYY-MM-DD` strings; usually one
  active period, possibly joined by a next period via
  `nextPeriodVisibleFrom`); each period carries its own `tabs[]` with
  `urlMetadataList[]`: `{bonusType, description, count, url}` (verified
  live 2026-08-29: the tabs are nested per period, not top-level).
  `bonusType` values: `NATIONAL`
  (~27 categories this week), `SPOTLIGHT`, `PERSONAL`,
  `PREVIOUSLY_BOUGHT`, `AHONLINE`, `GALL`, `GALLCARD`, `ETOS`. Only the
  `NATIONAL` entries are in scope.
- `GET /mobile-services/bonuspage/v2/section`
  (`application=AHWEBSHOP`, `date=<period-start>`,
  `promotionType=NATIONAL`, `category=<category>`) → `{sectionType,
  sectionDescription, sectionImage, bonusGroupOrProducts[]}`. Each entry
  is a wrapper: `{"product": {...}}` — the product object has the same
  shape as the search API (so `product_from_api` applies verbatim) — or
  `{"bonusGroup": {id, segmentDescription, discountDescription, category,
  exampleFromPrice, exampleForPrice, products: []}}`, where `id` is the
  segment id as a string and the `products` array is always empty (the
  REST endpoint does not expand groups). Observed this week: 27
  categories, 21 section products, 112 groups.
- `POST /graphql` with the no-argument `bonusPromotions` query →
  `data.bonusPromotions[]`: one entry per promotion segment the API
  currently serves (~196 this week — a superset of the national folder's
  groups), each with `id` (segment id, string) and `products[]` carrying
  `id` (webshop id), `title`, `brand`, `category`, `salesUnitSize`.
  Verified 2026-08-25: the field takes no arguments (no
  `id`/`periodStart`/`periodEnd`/`filterUnavailableProducts`/
  `forcePromotionVisibility`/`showAllPromotionSegments` exist on it, and
  introspection is disabled), and its `priceV2`/`availability` subfields
  fail deterministically with a gateway "Subgraph errors redacted" error —
  prices, availability, and deal text are not obtainable from this query.
- `GET /mobile-services/product/search/v2/products?ids=...&sortOn=INPUT_PRODUCT_IDS`
  — the existing products-by-ids endpoint already used by the receipt
  enrichment (100 ids per batch) — returns the full search-API product
  shape for the expanded group products: `currentPrice`,
  `priceBeforeBonus`, `bonusMechanism` (the deal text, for example "1 + 1
  gratis"), `isBonus`, `salesUnitSize`, `unitPriceDescription`,
  `mainCategory`, `availableOnline`, so `product_from_api` applies
  verbatim. Verified this week: all 2092 fetched group products carry
  `isBonus` and a `bonusMechanism`.
- The section endpoint also accepts an anonymous token; the client keeps
  using `get_access_token()` for consistency with the other endpoints.

## Goals / Non-Goals

**Goals:**

- One deep client method `AlbertHeijnClient.get_bonus_offers()` that hides
  the metadata walk, the per-category section fetches, the group
  expansion, and the deduplication, returning a flat `list[Product]`.
- One thin MCP tool `bonus_offers(limit=None)` mirroring the existing
  tools.
- Reuse the existing `Product` model and the existing `product_from_api`
  translator: no new model, no new translator.
- Everything unit-testable without a network through the existing
  monkeypatched-transport seam.

**Non-Goals:**

- No spotlight, personal, previously-bought, or non-bonus-program
  (AH Online / Gall & Gall / Etos) offers.
- No group-level summary entries in the result; a group is either expanded
  to its products or contributes nothing.
- No caching of the bonus data; one call fetches a fresh week.
- No anonymous-token fallback in the client (the endpoint accepts one, but
  the client's existing token contract stays untouched).

## Decisions

### 1. Flat expansion of groups into their products

The result is a flat product list in which every multi-product bonus group
is replaced by its concrete products, each flagged `is_bonus` with the
deal text in `bonus_mechanism`. This was chosen over (a) keeping groups as
first-class named entries ("Alle Galbani — 1+1 gratis") and (b) a
two-tool design (`bonus_offers` plus a group-expansion follow-up),
because the consumer of this tool is an LLM composing a shopping list:
concrete SKUs are directly actionable, and one call returns everything.
Accepted cost: the multi-buy relationship ("1+1 gratis") is only implicit
in the repeated mechanism text, and for those deals the API reports
`now == was` (in practice `currentPrice` is null and the pre-bonus price
is reported), so the price fields carry no discount delta — the mechanism
text is the discount signal.

### 2. Reuse `Product` and `product_from_api` for both product shapes

Section products and expanded group products both arrive as REST
search-API-shaped objects: section products directly from the section
endpoint, group products via the products-by-ids endpoint. Both go
through the existing `product_from_api` unchanged — including its
`currentPrice` null fallback to `priceBeforeBonus`. No second translator
is needed.

### 3. Module layout

- `_bonus.py` (new) — the bonus endpoints' I/O: fetch the metadata and
  return the active period plus the national categories; fetch one
  category's section and return its raw product objects and bonus-group
  objects; resolve all bonus-group (segment) product mappings with the
  no-argument GraphQL `bonusPromotions` query; fetch the full product
  objects of the group products in batches at the products-by-ids
  endpoint. Returns plain data (dicts, lists, strings), no models.
- `_client.py` — gains `get_bonus_offers()`: obtain the token lazily, open
  one `httpx.Client` with the app headers and bearer token (same
  construction as `get_purchase_history`), walk metadata → sections →
  groups, translate both product shapes with `product_from_api`,
  deduplicate, and return `list[Product]`. Any failure raises
  `AlbertHeijnError` (or `AuthenticationError` before the first request)
  — no partial results.
- `src/happie/server/__init__.py` — the `bonus_offers` tool.

### 4. Category walk and request plan

Only `bonusType == "NATIONAL"` metadata entries are walked; each section
request is built from the metadata parameters (`application`, `date` =
the active period's start date, `promotionType=NATIONAL`, `category` =
the entry's description). The active period is the first metadata period
whose `bonusStartDate`..`bonusEndDate` range contains today (UTC); when no
period contains today (for example when only the next folder is
visible), the metadata step yields no categories and the result is empty.
All section products and groups are collected first; then one no-argument
`bonusPromotions` GraphQL request resolves every segment's product ids at
once (segments are deduplicated by id, so a segment appearing in two
categories is looked up once), and the distinct group product ids are
fetched from products-by-ids in batches of 100 (the existing
enrichment pattern). No GraphQL or products-by-ids request is made at all
when no section contains a group. No pagination is needed — the section
endpoint returns a category's full list. Request budget per call:
1 metadata + one per national category (~27 observed) + at most one
GraphQL + one products-by-ids batch per 100 group products (~52 requests
this week).

### 5. Deduplication

Products are deduplicated by webshop id; the first occurrence wins, so
the result order is the API's category order — section entries in their
order within a category, and a group's products in the segment's product
order at the group's position. Groups are deduplicated by segment id
before expansion (a segment appearing in two categories is resolved once
and contributes its products at each occurrence, deduplicated against
everything already emitted). A product that appears both directly in a
section and inside a group is therefore returned exactly once.

Products the API does not flag as bonus are dropped from the result
(verified live 2026-08-29: a national section listed a folder product
without an `isBonus` flag and deal text; the products-by-ids endpoint
omits it as well). Only products flagged `is_bonus` are returned.

### 6. Error handling

All-or-nothing, consistent with the purchase-history contract: a non-200
REST response, a GraphQL `errors` payload, or an unexpected body shape
raises `AlbertHeijnError` naming the failing request and its status;
`AuthenticationError` propagates before any request when no usable token
exists. A segment that is absent from the `bonusPromotions` response, or
a group product that the products-by-ids endpoint omits, is not an error
— it contributes nothing. Error and log output never contains the bearer
token.

### 7. Testing

- `tests/albertheijn/test_bonus.py` through the monkeypatched transport:
  metadata parsing (active-period selection by date range,
  `NATIONAL`-only category filter, no active period yields no categories,
  unexpected bodies and non-200 statuses raising without token leakage),
  section request URL/parameters/headers, section-entry unwrapping into
  raw product and bonus-group objects, group expansion (no-argument
  `bonusPromotions` query, segment-to-product-id mapping, empty
  `bonusPromotions` list, GraphQL `errors` payload and non-200 raising
  without token leakage), group-products fetch (batches of 100,
  `sortOn=INPUT_PRODUCT_IDS`, ids the endpoint omits get no entry, error
  statuses raising).
- `AlbertHeijnClient.get_bonus_offers` orchestration test with the
  transport seam: end-to-end metadata → sections → groups flow into
  `Product` results, dedup across categories and between section products
  and group products, segments absent from the GraphQL response
  contributing nothing, no-token `AuthenticationError` without any
  request, and one failed request (section, GraphQL, or products-by-ids)
  failing the whole call without a token in the output.
- `tests/server/test_server.py` gains `bonus_offers` cases mirroring the
  existing tool tests: passes through the client result, trims with a
  limit, empty list, and failure keeps the server running.

## Risks / Trade-offs

- **Lost group framing** → Accepted (decision 1): the deal's multi-buy
  relationship survives only as the repeated mechanism text on each SKU,
  and multi-buy prices carry no discount delta. The group's product names
  remain reachable through `search_products`.
- **Request volume** → ~52 requests per call this week (1 + ~27 sections
  + 1 GraphQL + ~24 products-by-ids batches). Accepted: the tool is
  read-only and invoked infrequently by an LLM, not polled; the
  purchase-history flow already makes ~18 requests per call.
- **Superset segment list** → the no-argument `bonusPromotions` returns
  every segment the API serves, including non-national and possibly
  next-period segments. Accepted: only the segment ids found in the
  national sections are looked up, so the extras are inert.
- **Undocumented API drift** → the `bonusPromotions` query and the
  `bonuspage` endpoints are reverse-engineered. The GraphQL `errors`
  payload, non-200 statuses, and unexpected bodies are surfaced as
  `AlbertHeijnError`, so drift fails loudly instead of returning a
  silently wrong list.
- **Weekly variation** → category counts, group counts, and the
  product/group mix change every week (e.g. a category may be all groups
  one week and all products the next). The walk is data-driven from the
  metadata, so no per-week tuning is needed; the empty-period case
  returns an empty list.
