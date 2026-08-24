# cli

## Purpose

The command-line interface (CLI) is the user's entry point into happie. It
exposes commands to authenticate the user, manage the stored access token, and
start the MCP server, and it controls how log messages reach the terminal.

## Requirements

### Requirement: Authentication login command
The CLI SHALL provide a `happie auth login` command that starts the
browser-based authentication flow to obtain and store an access token, as
specified by the `auth` capability. The command SHALL install the `appie://`
protocol handler, open the authorization page, and wait for the token file to
be updated by the code-completion entrypoint; it SHALL NOT prompt the user
for the authorization code.

#### Scenario: Running `happie auth login`
- **WHEN** the user runs `happie auth login`
- **THEN** the CLI installs the protocol handler, opens the Albert Heijn
  authorization page in the user's default browser, and waits for the token
  file to be updated without prompting for the authorization code

### Requirement: Authentication code completion command
The CLI SHALL provide a `happie auth complete` command that completes the
browser-based authentication flow by exchanging an authorization code and
storing the resulting token, as specified by the `auth` capability. The
command SHALL accept an optional argument containing the deep-link URL,
query string, or bare code; with no argument it SHALL prompt for the input.

#### Scenario: Running `happie auth complete` with the deep-link URL
- **WHEN** the user runs `happie auth complete appie://login-exit?code=CODE`
- **THEN** the CLI exchanges the code, stores the token, and exits
  successfully without printing the code or any token value

#### Scenario: Running `happie auth complete` interactively
- **WHEN** the user runs `happie auth complete` without an argument
- **THEN** the CLI prompts for the code input on the terminal and completes
  the flow from the supplied value

#### Scenario: `happie auth complete` with an unusable code
- **WHEN** the code cannot be exchanged for a token
- **THEN** the CLI reports the failure, stores no token, and exits non-zero

### Requirement: Authentication logout command
The CLI SHALL provide a `happie auth logout` command that removes the stored
access token. Until token removal is implemented, running the command SHALL
log a message describing that it is removing the stored access token.

#### Scenario: Running `happie auth logout`
- **WHEN** the user runs `happie auth logout`
- **THEN** the CLI logs a message stating that it is removing the stored access token

### Requirement: MCP server command
The CLI SHALL provide a `happie serve` command that runs the MCP server. Until
the server is implemented, running the command SHALL log a message describing
that it is starting the MCP server.

#### Scenario: Running `happie serve`
- **WHEN** the user runs `happie serve`
- **THEN** the CLI logs a message stating that it is starting the MCP server

### Requirement: Readable terminal logging
The CLI SHALL configure application logging so that log messages are written
to the terminal in the human-readable format `[timestamp] [level] [message]`,
rather than raw or machine-oriented output.

#### Scenario: Log output is human-readable
- **WHEN** any command emits a log message
- **THEN** the message is written to the terminal in the format `[timestamp] [level] [message]`
