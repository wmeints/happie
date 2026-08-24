## Why

happie has no entry point for users yet. The architecture design calls for a
command-line interface (`happie.cli`) that wires authentication to the token
store and `happie serve` to the MCP server, but `src/happie/__init__.py` still
just prints a greeting and no commands exist. We need the CLI skeleton so users
can authenticate, manage their token, and start the server.

## What Changes

- Add a typer-based CLI application that exposes three commands:
  - `happie auth login` — authenticate the user to obtain an access token via
    the browser.
  - `happie auth logout` — remove the stored access token.
  - `happie serve` — run the MCP server.
- For now the commands do not perform their real work; each one logs a
  message describing what it would do.
- Configure Python's `logging` module so commands emit readable, human-friendly
  log messages to the terminal.
- Point the `happie` console script (declared in `pyproject.toml`) at the new
  CLI entry point instead of the placeholder greeting.

This is a logging stand-in: real authentication and server behavior are
intentionally out of scope and will follow in later changes.

## Capabilities

### New Capabilities
- `cli`: the command-line interface — the three commands and how the app
  configures terminal logging.

### Modified Capabilities

## Impact

- `src/happie/__init__.py` — the `happie` console script entry point.
- `src/happie/cli/` (new) — the typer app and the `auth` sub-app with `login`
  and `logout`, plus the `serve` command.
- No new runtime dependencies (`typer` is already declared). No breaking
  changes; the placeholder `main()` is replaced.
