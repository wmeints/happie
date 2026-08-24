## Context

`src/happie/__init__.py` currently exposes a single `main()` that prints a
greeting. The `happie` console script in `pyproject.toml` points at it. The
architecture (`docs/architecture/05-building-block-view.md`) already prescribes
a `happie.cli` package holding the typer app and the command definitions, and
`typer>=0.23` is already a declared dependency. This change adds that package
and wires the real entry point to it.

## Goals / Non-Goals

**Goals:**
- A typer app exposing `happie auth login`, `happie auth logout`, and
  `happie serve`.
- Each command logs what it will do instead of doing it (logging stand-in).
- Application logging configured once, at startup, to emit readable messages
  to the terminal.

**Non-Goals:**
- No real OAuth/browser flow, no token file read or write, and no FastMCP
  server startup. Those belong to later changes.
- No log files, log-level filtering flags, or structured (JSON) output.

## Decisions

- **Package layout: `src/happie/cli/` with a top-level `app` and an `auth`
  sub-app.** The `auth` group bundles `login` and `logout` under one parent so
  they surface as `happie auth <command>`, matching the architecture's `happie
  cli` module. `serve` hangs off the root app. `happie/__init__.py` keeps a
  thin `main()` that forwards to `cli.app()` so the `pyproject.toml` entry point
  is unchanged in shape.
  - Alternative: a flat app with `login`/`logout`/`serve` as top-level commands.
    Rejected because the spec and architecture name the auth pair `happie auth
    …`, and a sub-app is the idiomatic typer way to get a command group.

- **Logging configured in the entry point, not per command.** A single
  `logging.basicConfig` (or a small `configure_logging()` helper in
  `happie.cli`) runs once when the app starts, installing a `StreamHandler` to
  stderr with a `Formatter` of `[%(asctime)s] [%(levelname)s] [%(message)s]`
  and level `INFO`. Commands then just call
  `logging.getLogger(__name__).info(...)`.
  - Alternative: use typer's `echo` for user-facing text. Rejected because the
    requirement is explicitly to use the `logging` module; it also keeps the
    seam clear when real implementations replace the stand-ins and log at
    varying levels.

- **Log level: `INFO` by default.** The stand-in messages are the primary
  signal right now, so `INFO` is the floor. No CLI flag is added to change it
  (non-goal).

## Risks / Trade-offs

- [Logging configured too late] → If `basicConfig` runs after the first
  `logger` call, the handler can be missed. Mitigation: call the logging setup
  in `main()` before any command body runs (typer invokes callbacks after
  argument parsing, so the setup is at the top of the entry point).
- [Placeholder behavior read as real] → Users may assume `serve` starts a
  server. Mitigation: the log messages say plainly that this is a stand-in
  (e.g. "would start the MCP server" / "not yet implemented"), and the
  proposal/Non-Goals state the real work is deferred.
- [Output stream ambiguity] → Deciding between stdout and stderr for logs.
  Mitigation: use stderr (the conventional stream for logs/diagnostics), keeping
  stdout free for data.


