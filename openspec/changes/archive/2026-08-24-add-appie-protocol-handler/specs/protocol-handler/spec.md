# protocol-handler

## Purpose

Registration of a Linux protocol handler for the `appie://` URL scheme so
the Albert Heijn login redirect is delivered to the CLI instead of dead-ending
in the browser.

## ADDED Requirements

### Requirement: Protocol handler installation
The login flow SHALL install a Linux protocol handler for the `appie` URL
scheme at `~/.local/share/applications/happie.desktop` before opening the
authorization page. The desktop entry SHALL declare
`MimeType=x-scheme-handler/appie`, SHALL be hidden from application menus
(`NoDisplay=true`), and SHALL not require elevated permissions. Installation
SHALL be idempotent: re-running it with unchanged content SHALL leave the
file untouched, and the entry's `Exec` line SHALL reference the CLI by
absolute path.

#### Scenario: Handler is installed on first login
- **WHEN** the user runs the login flow and no `happie.desktop` entry exists yet
- **THEN** a desktop entry at `~/.local/share/applications/happie.desktop` exists, declares the `appie` scheme handler, and its `Exec` line contains an absolute path to the CLI binary

#### Scenario: Handler install is idempotent
- **WHEN** the user runs the login flow again and the handler entry is already installed and up to date
- **THEN** the existing desktop entry is not rewritten

#### Scenario: Handler path is refreshed when the CLI moved
- **WHEN** the login flow runs and the installed handler's `Exec` path no longer points at the current CLI binary location
- **THEN** the desktop entry is rewritten so its `Exec` line uses the current absolute CLI path

### Requirement: Scheme handler delivery
The installed handler SHALL be invoked by the desktop environment when a
browser redirects to `appie://login-exit?code=...`, passing the full URL, so
that completing the login requires no user interaction in the terminal.

#### Scenario: Browser redirect reaches the handler
- **WHEN** the browser redirects to `appie://login-exit?code=CODE` and the handler is registered
- **THEN** the CLI's code-completion entrypoint runs with the redirect URL and completes the login without further user input
