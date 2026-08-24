# Design — add-product-search-tool

## Context

`happie.cli` and `happie.auth` exist (browser login stores a token at
`~/.config/happie/token`); `happie.server` and `happie.albertheijn` do not.
The AH search endpoint, its response shape, and the anonymous-token behavior
are documented in the community-reverse-engineered
[appie-go](https://github.com/gwillem/appie-go) project
(`doc/search-api.md`, `products.go`). Existing code is sync `httpx`
(`happie.auth._flow`) with a private-submodule-per-seam layout
(`_flow`, `_store`) and mirrored tests in `tests/`.

## Goals / Non-Goals

**Goals:**

- Prove the full vertical slice: CLI `serve` → FastMCP tool → AH client →
  `api.ah.nl`.
- Keep both new packages deep modules with narrow public interfaces.
- Token semantics stay in `happie.auth`; the client only asks for a token.

**Non-Goals:**

- Anonymous access, shopping list, ordering history, product detail lookup,
  GraphQL faceted search (see proposal — Out of scope).

## Decisions

1. **Stored token only, no anonymous fallback** (user decision).
   `get_access_token()` raises `AuthenticationError` when no token is stored
   or the refresh fails; the client never attempts an anonymous token.
   Alternative considered: anonymous fallback, rejected — the user wants
   logged-in behavior (personalization, future tools require login anyway),
   and a fallback would mask a misconfigured setup behind degraded results.

2. **Refresh lives in `get_access_token()`, not in the client.** When the
   stored `expires_at` has passed, it calls
   `POST /mobile-auth/v1/auth/token/refresh` (`clientId: "appie"`,
   `refreshToken`, `User-Agent: Appie/8.22.3`, no `Authorization` header),
   re-stores the refreshed pair via the existing `save_token`, and returns the
   new access token. A 5-minute safety skew means a token within 5 minutes
   of expiry is refreshed early, so long-running MCP processes do not race
   the exact expiry instant. The token exchange and refresh are one seam in a
   private `happie.auth._token` module next to the existing `save_token`,
   keeping `Token`/store semantics in one place. Alternative: client-side
   refresh, rejected — it would duplicate expiry/refresh semantics in a
   second package.

3. **Sync `httpx` end to end, matching `happie.auth`.** `AlbertHeijnClient`
   (public in `happie.albertheijn`) wraps a sync `httpx.Client`; the
   `search_products` tool is a sync function. FastMCP offloads sync tools to
   a worker thread, so blocking calls are fine for this single-user local
   tool. Alternative: async client, rejected — no other part of the codebase
   is async, and the added `async`/`await`/`to_thread` seams buy nothing
   here.

4. **`AlbertHeijnClient` takes no arguments; it obtains its token lazily.**
   `AlbertHeijnClient.search_products(query, limit=10)` calls
   `auth.get_access_token()` at request time and attaches the app headers
   (`User-Agent: Appie/8.22.3`, `Accept`/`Content-Type: application/json`,
   `Authorization: Bearer <token>`). Constructing the client never touches
   the network or the token file, so a missing token only surfaces when a
   tool is actually called — the server keeps running as specified.

5. **The tool returns client models directly.** The FastMCP tool wraps
   `AlbertHeijnClient.search_products` with no field mapping, so one model
   serves both seams. `Product` is a frozen `dataclass` in a private
   `happie.albertheijn._models` module with: `webshop_id` (int), `title`,
   `brand`, `price`, `price_before_bonus` (float), `is_bonus` (bool),
   `bonus_mechanism` (str), `sales_unit_size`, `unit_price_description`
   (str), `available_online` (bool), `main_category` (str). Images,
   nutriscore, and ad/injected-product handling are dropped at parse time.
   Errors propagate unchanged: an API failure or authentication failure
   raised inside the tool is reported to the MCP client by FastMCP and the
   server keeps running, which is the specified failure behavior.

6. **`serve()` runs the FastMCP instance on stdio.** `happie.server` exposes
   `mcp` (the FastMCP instance) and `serve()` (calls `mcp.run()`, whose
   default transport is stdio). The CLI `serve` command becomes
   `server.serve()`; logging stays configured by the existing
   `configure_logging`.

## Risks / Trade-offs

- [Unofficial API: field or endpoint drift] → all response parsing sits in
  `happie.albertheijn._models`/the client's parse step, one seam; the
  endpoint path and header set are module constants.
- [Refresh response shape unknown] → assumed identical to the code-exchange
  response (`access_token`, `refresh_token`, `expires_in`); the first task is
  a live spike against both endpoints, and any drift shows up in the red
  tests before the implementation.
- [Search responses may contain injected sponsored products, slightly
  exceeding `size`] → return the first `limit` products in API order;
  correctness of "at most limit" is what matters, not which products.
- [Token file written by two processes (login CLI, long-running server)] →
  both write the same JSON shape with `0600`; last-writer-wins is acceptable
  for a single-user local tool.

## Migration Plan

None — new feature. Rollback is a revert; no stored data or external state
is affected beyond the already-existing token file.

## Open Questions

- Whether the search endpoint additionally requires `x-client-name` /
  `x-client-version` / `x-application` headers (appie-go sends them, but our
  token exchange has worked with `User-Agent` alone). Answered by the live
  spike task; add the header only if the endpoint rejects requests without
  it.
  **Answered by the live spike (task 1.1):** the endpoint rejects requests
  without `x-application: AHWEBSHOP` (HTTP 500 "Can not find application: 'null'");
  `x-client-name`/`x-client-version` are not required. The header was added
  to the client's module constant header set.
