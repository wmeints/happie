# Add a bonus offers tool to the MCP server

## Why

The weekly Albert Heijn bonus deals (bonus aanbiedingen) are the main
price-saving signal when building a shopping list, but the server has no way
to fetch them: `search_products` only finds products by name and cannot
enumerate what is on offer this week. The Albert Heijn API exposes
`bonuspage` endpoints that return the whole weekly bonus folder; surfacing
them as a tool lets an agent build the shopping list around the deals.

## What Changes

- New `AlbertHeijnClient.get_bonus_offers()` method, orchestrated from a new
  private `_bonus.py` submodule: reads the current bonus period and the
  national bonus categories from
  `GET api.ah.nl/mobile-services/bonuspage/v3/metadata`, fetches each
  category's section from
  `GET api.ah.nl/mobile-services/bonuspage/v2/section`, and expands every
  multi-product bonus group (segments such as "Alle Galbani") into its
  concrete products via the GraphQL `bonusPromotions` query on
  `api.ah.nl/graphql`. The result is a flat, deduplicated `list[Product]`
  that reuses the existing product model, with the deal text
  ("1+1 gratis", "30% korting", "2 VOOR 5.00") in `bonus_mechanism` and
  `is_bonus` set for every entry.
- New MCP tool `bonus_offers(limit=None)` on the server: returns the
  products on bonus this week, at most `limit` when a limit is given.
- Out of scope: the spotlight ("Uit de Bonusfolder") tab, the personalized
  tabs (personal bonus, previously bought), the non-bonus programs
  (AH Online, Gall & Gall, Etos), and group-level summary entries — groups
  are always expanded to their concrete products.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `albertheijn`: a new "Bonus offers" requirement — the metadata and
  section endpoints plus the GraphQL group expansion, translated to a
  deduplicated list of products, with the same failure-handling contract as
  the other endpoints.
- `server`: a new "Bonus offers tool" requirement — the `bonus_offers`
  tool returning a list of products.

## Impact

- **Code**: `src/happie/albertheijn/` (new `_bonus.py` submodule with the
  metadata/section/group expansion, a new `get_bonus_offers()` method on
  `AlbertHeijnClient`, and a GraphQL-product-to-`Product` translator);
  `src/happie/server/__init__.py` (the new tool); new
  `tests/albertheijn/test_bonus.py` and new tool tests in
  `tests/server/test_server.py`.
- **Dependencies**: none — `httpx` is already a direct dependency, and the
  GraphQL endpoint is a plain JSON POST with the existing application
  headers.
- **External systems**: `api.ah.nl/mobile-services/bonuspage/v3/metadata`,
  `api.ah.nl/mobile-services/bonuspage/v2/section`, and
  `api.ah.nl/graphql` (the `bonusPromotions` query). All three were verified
  live with the client's existing header set and the stored token; the
  section endpoint additionally works with an anonymous token.
- **User data**: read-only; the token store is untouched.
