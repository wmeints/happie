# Add a product search tool to the MCP server

## Why

The MCP server is still a stand-in (`happie serve` logs "not yet implemented")
and no tool exists yet. The first concrete use of the server is letting an
agent search the Albert Heijn assortment by term so it can pick products for
the shopping list; this is the vertical slice that proves
CLI → MCP server → API client → api.ah.nl end to end.

## What Changes

- New `happie.albertheijn` package: an `AlbertHeijnClient` that calls
  `GET api.ah.nl/mobile-services/product/search/v2` with the required app
  headers (`User-Agent: Appie/8.22.3`, `Accept`/`Content-Type: application/json`)
  and a bearer token, and translates the response into a `Product` model
  (webshop id, title, brand, price, price before bonus, bonus flag and
  mechanism, package size, online availability, main category).
- New `happie.server` package: a FastMCP server exposing the first tool,
  `search_products(query, limit=10)`, returning a list of products.
- `happie auth` gains `get_access_token()`: reads the stored token and returns
  the access token, refreshing it with the refresh token
  (`POST api.ah.nl/mobile-auth/v1/auth/token/refresh`) when expired and
  persisting the refreshed pair. Without a stored token, or when the refresh
  fails, it raises `AuthenticationError`. No anonymous fallback: the tool is
  deliberately limited to logged-in users.
- `happie serve` now starts the FastMCP server on stdio instead of logging a
  stand-in message.
- Out of scope: `happie auth logout`, shopping list and ordering history tools,
  anonymous access, GraphQL faceted search, product detail lookups.

## Capabilities

### New Capabilities

- `albertheijn`: the Albert Heijn API client — app headers, bearer-token
  requests, the product search endpoint, and the product model.
- `server`: the MCP server — the FastMCP instance, the
  `search_products` tool, and running the server on stdio via `serve()`.

### Modified Capabilities

- `auth`: new requirement for `get_access_token()` — read the stored token,
  refresh it on expiry, and fail when no usable token exists.
- `cli`: the `serve` command changes from a logging stand-in to actually
  starting the MCP server.

## Impact

- **Code**: new `src/happie/albertheijn/` and `src/happie/server/` packages;
  `src/happie/auth/__init__.py` gains `get_access_token()` (refresh logic in a
  private submodule); `src/happie/cli/__init__.py` (the `serve` command is
  rewired); new `tests/albertheijn/` and `tests/server/`; updated
  `tests/auth/` and `tests/cli/test_cli.py`.
- **Dependencies**: none — `fastmcp` and `httpx` are already direct
  dependencies.
- **External systems**: `api.ah.nl/mobile-services/product/search/v2`
  (product search) and `api.ah.nl/mobile-auth/v1/auth/token/refresh`
  (token refresh).
- **User data**: rewrites `~/.config/happie/token` with refreshed tokens when
  the stored token is expired; permissions stay user-only.
