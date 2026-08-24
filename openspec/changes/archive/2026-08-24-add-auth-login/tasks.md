## 1. Dependency

- [x] 1.1 Add `httpx` as a direct runtime dependency in `[project] dependencies` and refresh the lockfile. Verify: `uv lock` succeeds and `uv run python -c "import httpx"` exits 0; `httpx` appears under `[project] dependencies` rather than only transitively.

## 2. Token store (`src/happie/auth/_store.py`)

- [x] 2.1 Create the `happie.auth` package and add a `Token` model plus `save_token(token, path=DEFAULT_TOKEN_PATH)` that writes `{"access_token", "refresh_token", "expires_at"}` as JSON to `~/.config/happie/token`, creates the `~/.config/happie` directory (`0700`) when missing, writes the file `0600` (explicit `chmod` after write so umask cannot weaken the mode), and replaces any pre-existing token. Verify: `tests/auth/test_store.py` against `tmp_path` asserts the file contents and the `0600`/`0700` modes, and that a pre-existing token is fully replaced by a new one.

## 3. Authorization code parsing (`src/happie/auth/_flow.py`)

- [x] 3.1 Add a pure `extract_code(raw) -> str | None` that returns the code whether the input is a bare value, an `appie://login-exit?code=...` URL, or a `?code=...` query string, and returns `None` when a URL- or query-like input yields no code value. Verify: `tests/auth/test_flow.py` covers the bare, full-URL, and bare-query-string acceptance cases plus a URL-without-code case that returns `None`.

## 4. Token exchange (`src/happie/auth/_flow.py`)

- [x] 4.1 Add `exchange_code(code, *, client=None)` that sends `POST https://api.ah.nl/mobile-auth/v1/auth/token` with a JSON body `{"clientId": "appie", "code": <code>}` and the `User-Agent: Appie/8.22.3` header and no `Authorization` header, then returns the parsed access token, refresh token, and `expires_in`. Verify: `tests/auth/test_flow.py` against `httpx.MockTransport` asserts the request method, path, `User-Agent` header, absence of `Authorization`, and the JSON body, and that the returned tokens match the mocked response.
- [x] 4.2 Raise `AuthenticationError` (defined in the `happie.auth` package) for any non-2xx response or a 2xx body missing a required field, without embedding the code or tokens in the message. Verify: `tests/auth/test_flow.py` asserts the error is raised for a 4xx/5xx `MockTransport` and for a 200 body missing a field, and asserts the message does not contain the code or any token.

## 5. Browser open and orchestration (`src/happie/auth/__init__.py`)

- [x] 5.1 Expose `login()` that opens the authorization URL (`https://login.ah.nl/secure/oauth/authorize?client_id=appie&redirect_uri=appie://login-exit&response_type=code`) with stdlib `webbrowser`; when the URL cannot be opened (`webbrowser.open` returns `False`) it raises `AuthenticationError` and performs no exchange or store. Verify: `tests/auth/test_auth.py` patches `webbrowser.open` to return `False` and asserts the error is raised and no exchange or store call occurs.
- [x] 5.2 In `login()`, prompt on the terminal with `typer.prompt`, run the input through `extract_code`, re-prompt without echoing the input when it yields no code, then exchange and save the resulting token on success; no secret (code or token) may reach a log record. Verify: `tests/auth/test_auth.py` patches the browser, prompt, exchange, and save seams and asserts the loop re-prompts on a code-less URL, stores exactly once on a valid code, and that no captured log record contains the code or any token value.

## 6. CLI wiring (`src/happie/cli/__init__.py`)

- [x] 6.1 Rewire the `login` command to run `happie.auth.login()` instead of the stand-in: catch `AuthenticationError`, log the failure (no secrets) with guidance to log in again, and exit non-zero; update the module docstring so it no longer claims every command is a stand-in. Verify: `tests/cli/test_cli.py` replaces `test_auth_login_logs_stand_in` with a wiring test that patches the `happie.auth` entry point and asserts `happie auth login` invokes the flow and exits non-zero when it raises `AuthenticationError`.

## 7. Verification

- [x] 7.1 Run the full test suite and linter clean. Verify: `uv run pytest -q` passes and `uv run ruff check .` reports no issues.
