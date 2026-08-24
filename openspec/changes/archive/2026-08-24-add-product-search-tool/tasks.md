# Tasks — add-product-search-tool

## 1. Spike: confirm the API against the real endpoints

- [x] 1.1 Manually verify `GET api.ah.nl/mobile-services/product/search/v2?query=melk&page=0&size=5&sortOn=RELEVANCE` (headers: `User-Agent: Appie/8.22.3`, `Accept`/`Content-Type: application/json`, bearer token from `~/.config/happie/token`) returns `products` with the fields the model expects, and note whether any extra `x-client-*` headers are required (design: Open Questions). **Finding:** the endpoint rejects requests without `x-application: AHWEBSHOP` (HTTP 500 "Can not find application: 'null'"); `x-client-name`/`x-client-version` are not required. The header was added to the client's header constants. `currentPrice` may be null for non-bonus products (falls back to `priceBeforeBonus`).
- [x] 1.2 Manually verify `POST api.ah.nl/mobile-auth/v1/auth/token/refresh` with the stored refresh token returns `access_token`, `refresh_token`, and `expires_in`, confirming the refresh-response assumption (design: Risks). **Finding:** confirmed — HTTP 200 with exactly `access_token`, `refresh_token`, `expires_in`; the refreshed pair was persisted via `save_token` (0600).

## 2. Token retrieval in happie.auth (red → green)

- [x] 2.1 Write failing tests in `tests/auth/test_token.py` for `get_access_token()`: valid stored token returned without a refresh call; expired token refreshed via a mocked `httpx` transport and re-stored; missing token file raises `AuthenticationError`; refresh failure raises `AuthenticationError`; and no token value appears in log records
- [x] 2.2 Implement `get_access_token()` in a new private `src/happie/auth/_token.py` (5-minute safety skew, reuse `save_token` for the refreshed pair) and export it from `happie.auth.__init__`; verify `tests/auth/test_token.py` and the existing `tests/auth/` suite pass

## 3. Product model and search in happie.albertheijn (red → green)

- [x] 3.1 Write failing tests in `tests/albertheijn/test_client.py` using an `httpx` mock transport: request URL, query parameters (`query`, `page=0`, `size`, `sortOn=RELEVANCE`), and headers (`User-Agent`, `Content-Type`, `Accept`, bearer token); response parsing into `Product` (bonus product with mechanism text, and a non-bonus product where `price == price_before_bonus`); at-most-`limit` results; empty result; HTTP error status raises with the status and no token in logs; missing token raises `AuthenticationError` without making a request
- [x] 3.2 Implement `src/happie/albertheijn/_models.py` (frozen `Product` dataclass) and `_client.py` (`AlbertHeijnClient` with `search_products(query, limit=10)`, endpoint path and headers as module constants, token obtained lazily via `happie.auth.get_access_token()`), and export `AlbertHeijnClient` and `Product` from `happie.albertheijn`; verify `tests/albertheijn/test_client.py` passes. **Update (task 1.1/6.2):** added the required `x-application` header; null optional API fields now translate to empty strings (regression test `test_search_translates_null_optional_fields`).

## 4. MCP server and tool in happie.server (red → green)

- [x] 4.1 Write failing tests in `tests/server/test_server.py`: the `search_products` tool passes its arguments to the client, returns an empty list for no matches, and propagates client errors (e.g. `AuthenticationError`) as tool errors; verify by calling the registered tool through the FastMCP instance with a stubbed client
- [x] 4.2 Implement `src/happie/server/__init__.py` (FastMCP instance `mcp`, `search_products` tool with `limit` defaulting to 10, `serve()` running `mcp` on stdio); verify `tests/server/test_server.py` passes

## 5. CLI wiring

- [x] 5.1 Update `tests/cli/test_cli.py` so the `serve` stand-in test becomes a wiring test asserting `happie serve` invokes `happie.server.serve`; make it fail against the current stub
- [x] 5.2 Rewire the `serve` command in `src/happie/cli/__init__.py` to call `server.serve()` (and update the module docstring); verify the CLI test suite passes

## 6. Integration verification

- [x] 6.1 Run the full suite and linters: `uv run pytest` and `uv run ruff check src tests` plus `uv run ruff format --check src tests`, all clean
- [x] 6.2 End-to-end smoke test: with a stored token, run the MCP server (e.g. via `fastmcp`'s client or `happie serve` under a script) and call `search_products` with a real term; verify a real product list comes back and that with no token file the tool reports an authentication error while the server stays up. **Result:** drove `uv run happie serve` over stdio with a raw MCP client — 5 real products for "melk" (bonus and non-bonus), second call works; with `HOME` pointed at an empty dir the tool returned an authentication error and the server kept serving further requests.
