# auth (delta)

## MODIFIED Requirements

### Requirement: Browser-based code acquisition
The authentication flow SHALL install the `appie://` protocol handler (as
specified by the `protocol-handler` capability), open the Albert Heijn
authorization URL
(`https://login.ah.nl/secure/oauth/authorize?client_id=appie&redirect_uri=appie://login-exit&response_type=code`)
in the user's default browser so the user can log in, and SHALL then wait for
the code-completion entrypoint to store the token by watching the token file,
instead of prompting the user in the terminal.

#### Scenario: Login opens the authorization page
- **WHEN** the user starts the login flow
- **THEN** the authorization URL is opened in the user's default browser and the flow waits for the token file to be updated without prompting the user for input

#### Scenario: No browser available
- **WHEN** the system cannot open a browser for the authorization URL
- **THEN** the flow stops, reports the failure, and no token is exchanged or stored

### Requirement: Authorization code input
The code-completion entrypoint SHALL accept the authorization code as a bare
value, as the full `appie://login-exit?code=...` deep-link URL, or as a query
string containing `code=...`. When invoked without an argument, the
entrypoint SHALL prompt the user on the terminal to provide the input. Input
that looks like a URL or query string but yields no code value SHALL be
rejected and the user SHALL be prompted again. No form of input acceptance or
error reporting SHALL reveal the code value.

#### Scenario: Bare code is accepted
- **WHEN** the entrypoint receives only the code value, as an argument or prompted input
- **THEN** it uses that code for the token exchange

#### Scenario: Full deep-link URL is accepted
- **WHEN** the entrypoint receives `appie://login-exit?code=CODE`
- **THEN** it extracts `CODE` and uses it for the token exchange

#### Scenario: Query string is accepted
- **WHEN** the entrypoint receives a query string containing `code=CODE`
- **THEN** it extracts `CODE` and uses it for the token exchange

#### Scenario: URL-like input without a code is rejected
- **WHEN** the user is prompted and provides a URL or query string that contains no code value
- **THEN** the entrypoint reports that no code was found and prompts again

## ADDED Requirements

### Requirement: Code completion entrypoint
The authentication capability SHALL expose a code-completion entrypoint that
takes an authorization code (from an argument or the terminal prompt, as
specified by the authorization code input requirement), exchanges it for
tokens, and stores them. The entrypoint SHALL report a failure without storing
any token when the code cannot be used, and SHALL NOT write the code or any
token to logs.

#### Scenario: Completion stores the token
- **WHEN** the code-completion entrypoint receives a usable authorization code
- **THEN** it exchanges the code and stores the resulting token as specified
  by the token storage requirement

#### Scenario: Unusable code fails without storing
- **WHEN** the code-completion entrypoint's token exchange fails
- **THEN** it reports the failure, no token is stored, and it exits
  non-zero

### Requirement: Token file watching
While waiting after opening the browser, the login flow SHALL check the token
file every 10 milliseconds for a change. A change SHALL count as login
success only if the updated file parses as stored-token JSON whose expiry
(`expires_at`) is in the future; any other updated content SHALL keep the
flow waiting. Upon success the flow SHALL exit successfully. If no valid
change occurs within five minutes, the flow SHALL fail with an error
indicating the login timed out.

#### Scenario: Handler-stored token ends the wait
- **WHEN** the code-completion entrypoint stores a token while the login flow is waiting
- **THEN** the login flow detects the token file change within one polling interval and exits successfully

#### Scenario: Stale or invalid token content does not end the wait
- **WHEN** the token file changes but its stored expiry is not in the future
- **THEN** the login flow keeps waiting

#### Scenario: No token within the timeout
- **WHEN** five minutes elapse without a valid token file change
- **THEN** the login flow reports a timeout error and exits non-zero
