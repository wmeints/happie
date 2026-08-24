## Purpose

The command-line interface (CLI) is the user's entry point into happie. It
exposes commands to authenticate the user, manage the stored access token, and
start the MCP server, and it controls how log messages reach the terminal.

## ADDED Requirements

### Requirement: Authentication login command
The CLI SHALL provide a `happie auth login` command that authenticates the
user through the browser to obtain an access token. Until authentication is
implemented, running the command SHALL log a message describing that it is
starting browser-based authentication to obtain an access token.

#### Scenario: Running `happie auth login`
- **WHEN** the user runs `happie auth login`
- **THEN** the CLI logs a message stating that it is authenticating the user via the browser to obtain an access token

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
