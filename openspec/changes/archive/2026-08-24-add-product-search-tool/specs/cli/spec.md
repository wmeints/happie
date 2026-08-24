## MODIFIED Requirements

### Requirement: MCP server command
The CLI SHALL provide a `happie serve` command that starts the MCP server on
stdio so that an MCP client can communicate with it.

#### Scenario: Running `happie serve`
- **WHEN** the user runs `happie serve`
- **THEN** the MCP server runs and reads tool calls from stdin until the
  client disconnects
