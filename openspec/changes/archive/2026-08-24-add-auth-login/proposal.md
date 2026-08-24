# Add `happie auth login` with a real browser OAuth flow

## Why

`happie auth login` is currently a logging stand-in, so no user can obtain an
access token and nothing downstream (API client, MCP server) can progress. The
architecture already pins the token flow, the token store location, and the
package boundaries; this is the first slice of `happie.auth`.

## What Changes

- New `happie.auth` package that performs the browser-based OAuth flow against
  Albert Heijn:
  - Opens the authorization URL
    (`login.ah.nl/secure/oauth/authorize?client_id=appie&redirect_uri=appie://login-exit&response_type=code`)
    in the user's default browser.
  - Prompts the user on the terminal to paste the code the browser receives in
    the `appie://login-exit?code=…` deep-link redirect; accepts a bare code,
    the full deep-link URL, or just the query string.
  - Exchanges the code at `POST api.ah.nl/mobile-auth/v1/auth/token`
    (sending the required `User-Agent: Appie/8.22.3` header) and receives the
    access token, refresh token, and expiry.
- Token store: the result is written as JSON
  (`access_token`, `refresh_token`, `expires_at`) to
  `~/.config/happie/token` with user-only permissions; the parent directory is
  created as needed.
- `happie auth login` now runs this flow instead of logging "not yet
  implemented".
- Adds `httpx` as a runtime dependency for the token exchange.
- Out of scope: `happie auth logout` (stays a stand-in), token refresh /
  `get_access_token()`, the MCP server, and the Albert Heijn API client.

## Capabilities

### New Capabilities

- `auth`: browser-based OAuth code capture, code input parsing, the token
  exchange, and the user-only token store in `~/.config/happie`.

### Modified Capabilities

- `cli`: the "Authentication login command" requirement changes from the
  "log a message until implemented" stand-in to actually starting
  browser-based authentication; its scenario is updated accordingly.

## Impact

- **Code**: new `src/happie/auth/` package; `src/happie/cli/__init__.py` (the
  `login` command is rewired, module docstring no longer claims all commands
  are stand-ins); new `tests/auth/`; updated `tests/cli/test_cli.py` (the
  login stand-in test becomes a wiring test).
- **Dependencies**: `httpx` added to `[project] dependencies` (currently only
  pulled transitively via `fastmcp`).
- **External systems**: `login.ah.nl` (authorization page, opened in the
  user's browser) and `api.ah.nl/mobile-auth` (token exchange). No MCP client
  or server-side impact.
- **User data**: creates `~/.config/happie/token` containing secrets,
  protected by user-only file and directory permissions.
