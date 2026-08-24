## Why

`happie auth login` currently asks the user to manually copy and paste the
authorization code from the browser after the `appie://login-exit?code=...`
deep-link redirect. On Linux the browser cannot hand that deep link to any
application because no `appie://` scheme handler is registered, so login
always degrades to fragile copy/paste from the address bar.

## What Changes

- **New** `happie auth complete` command: accepts an `appie://` URL, a bare
  code, or a query string, exchanges the code for tokens, and stores them.
  With no argument it prompts for input — this becomes the manual
  copy/paste recovery path.
- **New** Linux `appie://` protocol handler installed at
  `~/.local/share/applications/happie.desktop`
  (`MimeType=x-scheme-handler/appie`, `Exec=<abs path> auth complete "%u"`,
  `NoDisplay=true`), installed/refreshed by `auth login` and marked trusted
  for desktop environments that require it.
- **Changed** `happie auth login` flow: after opening the authorization page
  it no longer prompts. It instead polls the token file
  (`~/.config/happie/token`) every 10 ms, treats a change whose parsed
  `expires_at` is in the future as success, and exits. A 5-minute timeout
  fails the login with an error.
- **BREAKING** the interactive code prompt is removed from `auth login`; the
  "prompt until a code is supplied" behavior moves to no-arg
  `auth complete`. Linux is the only supported platform; no
  macOS/Windows handler mechanics are added.

## Capabilities

### New Capabilities

- `protocol-handler`: Registration of the Linux `appie://` scheme handler —
  desktop file location and content, idempotent installation, absolute
  `Exec` resolution, and trusted-marking semantics.

### Modified Capabilities

- `auth`: Code acquisition becomes protocol-handler-driven (login watches the
  token file instead of prompting); a new `auth complete` entrypoint handles
  code input (arg or prompt) plus exchange and storage; new token-file watch
  requirement with timeout and freshness guard.
- `cli`: New `happie auth complete` command; `auth login` behavior changes
  from prompt-based to watch-based.
