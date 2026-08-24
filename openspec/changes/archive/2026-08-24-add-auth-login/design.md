# Design: browser OAuth login for `happie auth login`

## Context

See proposal.md for the motivation. Current state: `happie.cli` holds the
`login`/`logout`/`serve` stand-ins, `httpx` is present only transitively via
`fastmcp`, and no `happie.auth` package exists yet.

The Albert Heijn API is not documented by the vendor. Interaction with it is
pinned by the design document referenced from
`docs/architecture/02-constraints.md` (jabbink's gist): the authorization
page is `login.ah.nl`, the code is delivered to the mobile Appie app via the
`appie://login-exit` deep-link redirect, and the token endpoints live under
`api.ah.nl/mobile-auth`. The building-block view
(`docs/architecture/05-building-block-view.md`) assigns the flow, the browser
redirect handling, and the token file to `happie.auth`, with a narrow public
interface.

## Goals / Non-Goals

**Goals:**

- `happie auth login` performs the full flow: open browser → prompt for the
  code → exchange the code → store the tokens.
- `happie.auth` exposes a narrow public interface (`login()`) and keeps the
  HTTP, parsing, and file handling internal.
- The token store is forward-compatible: it persists the refresh token and
  the computed expiry now, so the later refresh slice and the
  `happie.albertheijn` slice can read it without rework.
- Every seam is unit-testable without a browser or network, keeping the
  red-green cycle fast.

**Non-Goals:**

- Token refresh / `get_access_token()`.
- `happie auth logout` (stays a stand-in).
- Browser automation (Playwright or similar).
- `XDG_CONFIG_HOME` support or any configurable token path.

## Decisions

### 1. Code capture: user's default browser plus terminal paste

The CLI opens the authorization URL with the standard-library `webbrowser`
and the user pastes the code after logging in. The code cannot be captured
programmatically because the redirect target is the fixed mobile deep link
`appie://login-exit`; the code only exists in the `303 Location` header the
browser receives.

**Alternatives considered:**

- Playwright, headful: intercept the `303 Location` header in a controlled
  browser. Rejected — large dependency (driver plus a browser binary) and
  automation of a vendor login page carries bot-detection risk, for a UX
  gain limited to skipping a paste.
- One-shot local HTTP server with `redirect_uri=http://127.0.0.1:<port>`:
  rejected — the vendor's OAuth server allow-lists the redirect URI for
  `client_id=appie`, and deviating from the pinned design doc violates the
  project's constraint.

### 2. Lenient code input

Since `webbrowser` cannot hand the code back, the user copies whatever their
browser shows after the failed `appie://` handoff. The parser accepts a bare
code, the full `appie://login-exit?code=...` URL, or a bare query string,
using `urllib.parse` (standard library). Input that looks like a URL or query
string but yields no code is rejected and re-prompted; any other non-empty
input is treated as the bare code.

### 3. httpx for the token exchange

Added as an explicit runtime dependency (currently only transitive via
`fastmcp`). A client is created per invocation; tests inject `MockTransport`.
**Alternative:** `urllib.request` — rejected; httpx is the de facto HTTP
stack of this dependency tree and the upcoming `happie.albertheijn` client
will use it too.

### 4. Token file: JSON with a computed `expires_at`

`~/.config/happie/token` holds
`{"access_token": ..., "refresh_token": ..., "expires_at": <ISO 8601 UTC>}`.
The building-block view's "holds the access token" is insufficient on its
own: `expires_in` is about two hours, so the refresh token and the computed
expiry must be persisted now for the later refresh slice. ISO 8601 UTC keeps
the file human-inspectable. The path is pinned by the architecture doc; no
`XDG_CONFIG_HOME` override in this slice. The file is written `0600` and the
directory created `0700`, with an explicit `chmod` after creation so umask
cannot weaken the modes.

### 5. Module layout and test seams

```
src/happie/auth/__init__.py   # public: login()
src/happie/auth/_flow.py      # authorization URL, code parsing, token exchange
src/happie/auth/_store.py     # Token model, path resolution, save
```

`login()` in `__init__.py` orchestrates: open browser → prompt → parse →
exchange → save. The prompt uses `typer.prompt`; the exchange raises
`AuthenticationError` (defined in the package) on a non-2xx response or a
malformed body. The CLI's `login` command catches it, logs the error, and
exits with a non-zero status. Unit tests target the seams directly: the pure
parse function, the exchange against `MockTransport`, the store against
`tmp_path`, and `login()` with the private seams patched. Tests live in
`tests/auth/`, mirroring the package.

### 6. Error surface

- No browser found (`webbrowser.open` returns `False`) → error, stop,
  non-zero exit.
- Exchange 4xx/5xx → `AuthenticationError` carrying the status; the CLI logs
  guidance to log in again.
- Malformed success response (missing fields) → treated as an exchange
  failure.
- Secrets never appear in logs; the token path may.

## Risks / Trade-offs

- [The code is not visibly retained in some browsers after the `appie://`
  handoff fails] → the prompt text points at where the code appears
  (address bar / failed-URL error page) and mentions the DevTools fallback;
  the first real login confirms it on the user's browser.
- [AH changes the mobile-auth endpoints or the login flow] → every URL,
  header, and body is pinned by the referenced design doc; breakage surfaces
  as a clear exchange error rather than silent failure.
- [Vendor bot detection on the token exchange] → the required
  `User-Agent: Appie/8.22.3` header is sent per the design doc.
- [Secrets on disk] → `0600` file inside a `0700` directory; values are
  never logged.

## Migration Plan

New behavior, no pre-existing data: nothing to migrate. Rollback is reverting
the change; a leftover `~/.config/happie/token` is inert because no code
reads it yet.

## Open Questions

- In the user's actual browser, is the code visibly retained after the
  `appie://login-exit` deep link fails (address bar vs. opaque error page)?
  Verified on the first real login; it does not affect the specs or the task
  breakdown, because the prompt is the code handoff either way.
