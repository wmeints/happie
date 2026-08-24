## Context

`happie auth login` opens the AH authorization URL in the browser and prompts
the user to paste the authorization code. The AH redirect is a deep link
(`appie://login-exit?code=...`); on Linux no app claims the `appie` scheme, so
the browser dead-ends and the user must copy the URL out of the address bar.
See proposal.md for the motivation.

Constraints that shape the design:

- Token file: `~/.config/happie/token`, written by `save_token` via
  in-place `write_text` (inode stable, `st_mtime_ns` changes); no atomic
  replace to worry about.
- `extract_code` already accepts bare code / full URL / query string.
- Project convention: keep dependencies minimal (Playwright was explicitly
  rejected); no new runtime dependencies.
- Linux is the only supported platform for the handler mechanic.
- Secrets never appear in logs (existing spec requirement).

## Goals / Non-Goals

**Goals:**

- `happie auth login` completes hands-free on Linux: browser redirect reaches
  a CLI handler that exchanges and stores the token; the main process exits
  when the token file is validly updated.
- `happie auth complete` is a dedicated entrypoint that also serves as the
  manual paste fallback.
- Handler registration is self-healing and idempotent.

**Non-Goals:**

- macOS/Windows scheme-handler registration.
- Token refresh, logout, or server integration (existing stand-ins unchanged).
- Detecting *which* process wrote the token file (the watcher trusts any
  valid fresh update; the later refresh slice may write here too — accepted).
- Atomic token writes (current in-place `write_text` semantics preserved).

## Decisions

### 1. Split the flow into `login` (orchestrator) and `complete` (worker)

`happie.auth` gains:

- `complete(raw: str | None = None) -> Token` — when `raw` is `None`, prompt
  until `extract_code` yields a value (the current `_prompt_for_code` loop
  moves here, verbatim behavior: bare code / URL / query string, re-prompt on
  code-less input, raw input never logged). Then `exchange_code` + `save_token`.
  Raises `AuthenticationError` on any failure.
- `login() -> None` — (re)install the handler, snapshot the token file, open
  the browser, poll the token file, return on valid update or raise
  `AuthenticationError` on timeout. The code never enters this process.

`_flow.py` keeps `extract_code`/`exchange_code` unchanged; the prompt loop and
`webbrowser.open` orchestration move out of the current `login()`.

**Alternative considered:** main process does the exchange after capturing
the code itself (e.g. via a local HTTP redirect). Rejected — the AH flow is
pinned to the `appie://` deep link (vendor constraint), so a loopback server
is impossible; a scheme handler is the only hands-free delivery path.

### 2. Desktop file install

New private module `happie/auth/_handler.py`:

- Path: `~/.local/share/applications/happie.desktop` (fixed, no
  `XDG_DATA_HOME` — consistent with the fixed token path convention).
- Content:

  ```ini
  [Desktop Entry]
  Type=Application
  Name=happie
  NoDisplay=true
  Exec=<abs> auth complete %u
  MimeType=x-scheme-handler/appie;
  ```

  `%u` must be wrapped in `"` per the desktop-entry spec so URLs containing
  spaces/`&` survive DE exec parsing. `<abs>` is `shutil.which("happie")`
  resolved at install time — DEs spawn handlers with a restricted `PATH`, so
  a bare name is unreliable.
- `ensure_handler()`: resolve the current CLI path; if the desktop file
  exists, its `Exec` line already uses that path, and `NoDisplay`/`MimeType`
  are present → no-op. Otherwise (re)write with modes `0644` (directory
  `0755` when created — the file is not a secret). Idempotency check on the
  content, not on mere existence: a stale path (reinstall/uv update) triggers
  a rewrite, which is the self-heal.
- After a write (first-time only, or when path changed): run
  `gio set <file> trusted true` via `subprocess.run` with a short timeout,
  swallowing `FileNotFoundError`/non-zero exit — GNOME requires the trusted
  mark, Plasma does not, and `gio` is absent on both minimal systems where it
  doesn't matter. Best effort, never fatal.

**Alternative considered:** a separate `happie auth install-handler` command.
Rejected — an extra step the user must know about; `login` auto-ensuring is
idempotent and user-writable, so the side effect is acceptable.

### 3. Token-file watch: 10 ms stat poll

In `login`, before opening the browser, snapshot the token file state as
`(st_ino, st_mtime_ns)` or `None` when absent. After `webbrowser.open`, loop:

```
deadline = now + 5 minutes
while now < deadline:
    state = stat(token_path)
    if state != initial and token_file_is_fresh():
        return success
    sleep(0.01)
raise AuthenticationError("login timed out")
```

- `stat` every 10 ms as requested: ~100 syscalls/s, negligible; simpler than
  inotify and stdlib-only.
- Change = `(st_ino, st_mtime_ns)` differs from the snapshot. `save_token`
  truncates in place, so the inode is stable and mtime alone would suffice;
  ino is included for the atomic-replace case at zero cost.
- Freshness guard (`token_file_is_fresh`): parse the JSON, require
  `expires_at` to be a parseable, timezone-aware datetime in the future
  (with a small grace, e.g. now + 30 s). Malformed JSON / missing key /
  past expiry → not fresh, keep waiting. This also kills the "someone touched
  the stale file" false positive.
- Timeout: 5 minutes. Codes are single-use and short-lived; on timeout the
  user reruns `happie auth login`. No retry/refresh logic — out of scope.
- KeyboardInterrupt handling: let it propagate; typer exits cleanly.

**Alternative considered:** 500 ms poll to be gentler. Rejected on user
preference for 10 ms; the cost is trivial.

### 4. CLI wiring

`auth_app` gains:

```python
@auth_app.command()
def complete(raw: str | None = typer.Argument(None)) -> None:
    """Complete the browser login by exchanging the authorization code."""
```

- `raw` is accepted as-is (URL / query / bare code) — no shell-quoting
  requirements beyond ordinary arg parsing; the DE passes the URL as one
  argument via the quoted `%u`.
- `AuthenticationError` → log failure (message must not contain the code),
  `typer.Exit(1)`. Success → log "Stored Albert Heijn access token." (no
  secret values).
- `login` unchanged in shape: calls `auth.login()`, same error handling.

The argv exposure (code visible in `ps` while the handler runs) is accepted:
scheme handlers receive input via argv by design; the no-secrets-in-logs
constraint is preserved because neither process logs the URL or code.

### 5. Module layout

```
happie/auth/
├── __init__.py   # re-export complete, login, AuthenticationError, Token, save_token
├── _flow.py      # extract_code, exchange_code, URLs (unchanged)
├── _store.py     # Token, save_token (unchanged); + load/parse helper used by the watcher
└── _handler.py   # NEW: desktop-file ensure_handler()
tests/auth/
├── test_flow.py  # unchanged
├── test_store.py # + parse helper tests
├── test_handler.py # NEW: desktop file content, quoting, idempotency, path refresh
├── test_auth.py  # re-wired: login = watch flow; complete = prompt+exchange
└── test_cli.py   # + complete wiring test; login test updated
```

The watcher lives in `auth` (it's auth behavior); the CLI stays a thin wrapper.

## Risks / Trade-offs

- **DE picks up the desktop file late.** GNOME watches
  `~/.local/share/applications`; the browser redirect happens after the user
  finishes login (seconds–minutes), giving ample time. Worst case: first
  redirect fails, user retries or runs `happie auth complete <url>` manually.
  Accepted — manual path is first-class.
- **Watcher false positive from future features.** When token refresh lands,
  a refresh rewrite during login would end the wait with a valid fresh token.
  Harmless outcome (the stored token is usable); noted in the module
  docstring.
- **`gio` trusted-mark race on headless/first-boot GNOME.** The trusted flag
  may not apply before the first redirect on an interactive session that just
  started. Same manual-recovery path applies.
- **Absolute Exec path staleness.** Self-healed by the per-login content
  check; a login started with a *stale* handler would have failed the
  handler-rewrite before the browser opens, so the stale path is never in
  effect mid-flow.
- **Code in argv.** Visible in `ps` for the duration of the exchange
  (~seconds). Accepted surface; alternative (stdin handoff) would require the
  handler to read a file the main process writes, which inverts the clean
  "handler owns the code" property.
