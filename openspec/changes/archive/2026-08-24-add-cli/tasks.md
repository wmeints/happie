## 1. Logging foundation

- [x] 1.1 Add a `configure_logging()` helper to a new `happie.cli` module that installs a `StreamHandler` on stderr with a `Formatter` of `[%(asctime)s] [%(levelname)s] [%(message)s]` and level `INFO`; write a failing pytest that captures a logged message on stderr in that `[timestamp] [level] [message]` format, then implement until it passes (verify: `uv run pytest tests/cli/` green).

## 2. Typer app and commands

- [x] 2.1 Create the typer `app` and an `auth` sub-app in `happie.cli`; add `login` and `logout` commands on `auth` and a `serve` command on `app`, each logging its stand-in message via the module logger; add a failing `CliRunner` pytest per command asserting the expected log text, then implement until all three pass (verify: `uv run pytest tests/cli/` green).
- [x] 2.2 Register the `auth` sub-app on `app` and verify command discovery: a `CliRunner` test asserts `happie auth --help` lists `login` and `logout`, and `happie --help` lists both `auth` and `serve` (verify: the help test passes).

## 3. Entry point

- [x] 3.1 Replace the placeholder `main()` in `src/happie/__init__.py` so it calls `configure_logging()` and then runs `happie.cli.app`, keeping the `happie` console-script target in `pyproject.toml` unchanged (verify: `uv run happie --help` exits 0 and lists `auth` and `serve`).

## 4. End-to-end verification

- [x] 4.1 Run each command and confirm the stand-in line on the terminal in `[timestamp] [level] [message]` form: `uv run happie auth login`, `uv run happie auth logout`, `uv run happie serve` (verify: each prints `[<timestamp>] [INFO] [<action it would perform>]`).
