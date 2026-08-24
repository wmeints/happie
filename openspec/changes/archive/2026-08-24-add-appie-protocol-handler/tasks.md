## 1. Protocol handler install

- [x] 1.1 Add `happie/auth/_handler.py` with `ensure_handler()` that writes
  `~/.local/share/applications/happie.desktop` (dir `0755` when created, file
  `0644`): `Type=Application`, `Name=happie`, `NoDisplay=true`,
  `Exec="<abs> auth complete %u"` with the CLI path from
  `shutil.which("happie")`, and `MimeType=x-scheme-handler/appie;`. No-op when
  the existing file already matches; rewrite when the `Exec` path is stale.
  Mark the file trusted via `gio set <file> trusted true` (best effort,
  failures ignored) only on first write.
  Verify: `tests/auth/test_handler.py` asserts file content (scheme,
  `NoDisplay`, quoted `%u`, absolute path), no-rewrite on unchanged re-run,
  rewrite on path change, and modes; `uv run pytest tests/auth/test_handler.py`
  passes.
- [x] 1.2 Export `ensure_handler` from `happie.auth` (`__all__`).
  Verify: `uv run pytest` passes; import works in a `uv run python -c`
  smoke check.

## 2. Auth flow split

- [x] 2.1 Add `complete(raw: str | None = None) -> Token` to
  `happie/auth/__init__.py`: when `raw` is `None`, run the prompt loop
  (moved from the current `login`, keeping the re-prompt-on-code-less-input
  behavior and never logging raw input); then `extract_code`, `exchange_code`,
  `save_token`; raise `AuthenticationError` on failure without logging the
  code.
  Verify: `tests/auth/test_auth.py` covers arg URL/bare code/query, no-arg
  prompt (monkeypatched prompt), exchange failure (no save, error raised),
  and that no logged message contains the code; `uv run pytest
  tests/auth/test_auth.py` passes.
- [x] 2.2 Add the token-file watcher used by `login`: snapshot
  `(st_ino, st_mtime_ns)` (or absent) and poll every 10 ms up to 5 minutes;
  success only when the state differs from the snapshot AND the file parses
  as stored-token JSON with `expires_at` in the future (30 s grace); raise
  `AuthenticationError` on timeout. Add the JSON parse helper to
  `happie/auth/_store.py`.
  Verify: `tests/auth/test_auth.py` (or `tests/auth/test_store.py` for the
  parse helper) covers file-absent-then-written, in-place rewrite, stale
  `expires_at` keeps waiting, malformed JSON keeps waiting, and timeout
  raises (monkeypatch `time.sleep` to advance the clock); `uv run pytest`
  passes.
- [x] 2.3 Rewrite `login()`: `ensure_handler()`, snapshot token file,
  `webbrowser.open(AUTHORIZATION_URL)` (error if it fails), run the watcher,
  return on success. Remove the prompt from `login`; keep
  `AuthenticationError` as the failure type.
  Verify: `tests/auth/test_auth.py` login test asserts handler ensured,
  browser opened, watcher exit on token update, and failure when the browser
  cannot open; `uv run pytest` passes.

## 3. CLI wiring

- [x] 3.1 Add `happie auth complete` to `happie/cli/__init__.py` with an
  optional `raw` argument (`typer.Argument(None)`), calling
  `auth.complete(raw)`; `AuthenticationError` → error log (no code value in
  the message) + exit 1; success → log a stored-token confirmation without
  secrets.
  Verify: `tests/cli/test_cli.py` adds a wiring test: `happie auth complete
  "appie://login-exit?code=CODE"` with mocked exchange stores the token and
  exits 0; a failing exchange exits 1 with no token and no code in output;
  `uv run pytest tests/cli/test_cli.py` passes.
- [x] 3.2 Update the existing `auth login` CLI test to the new contract:
  handler ensured, browser opened, watcher-driven exit — no prompt.
  Verify: `uv run pytest tests/cli/test_cli.py` passes.

## 4. Final verification

- [x] 4.1 Run the full suite plus lint/format: `uv run pytest` and
  `uv run ruff check .` and `uv run ruff format --check .` all clean.
  Verify: all three commands exit 0.
- [x] 4.2 Manual smoke on the dev machine: run `happie auth login`, confirm
  `~/.local/share/applications/happie.desktop` is written with the absolute
  CLI path, complete a real browser login (or invoke
  `happie auth complete <url>` manually with a fresh code), and confirm the
  login process exits 0 and `~/.config/happie/token` holds a fresh token
  without the code or token appearing in either process's output.
  Verify: observed terminal output; `stat ~/.config/happie/token` shows a
  new mtime and `expires_at` in the future.
