## MODIFIED Requirements

### Requirement: Authentication login command
The CLI SHALL provide a `happie auth login` command that starts the
browser-based authentication flow to obtain and store an access token, as
specified by the `auth` capability.

#### Scenario: Running `happie auth login`
- **WHEN** the user runs `happie auth login`
- **THEN** the CLI opens the Albert Heijn authorization page in the user's
  default browser and prompts the user for the authorization code
