# auth Specification

## Purpose
Browser-based authentication against the Albert Heijn mobile-auth API:
captures the authorization code from the user's browser login, exchanges it
for an access token, and keeps the tokens in a user-only store.

## Requirements

### Requirement: Browser-based code acquisition
The authentication flow SHALL open the Albert Heijn authorization URL
(`https://login.ah.nl/secure/oauth/authorize?client_id=appie&redirect_uri=appie://login-exit&response_type=code`)
in the user's default browser so the user can log in, and SHALL then wait for
the user to provide the authorization code that the login flow redirects to
via `appie://login-exit?code=...`.

#### Scenario: Login opens the authorization page
- **WHEN** the user starts the login flow
- **THEN** the authorization URL is opened in the user's default browser and the flow waits for the user's input

#### Scenario: No browser available
- **WHEN** the system cannot open a browser for the authorization URL
- **THEN** the flow stops, reports the failure, and no token is exchanged or stored

### Requirement: Authorization code input
The flow SHALL prompt the user on the terminal to provide the authorization
code. It SHALL accept the code as a bare value, as the full
`appie://login-exit?code=...` deep-link URL, or as a query string containing
`code=...`. Input that looks like a URL or query string but yields no code
value SHALL be rejected and the user SHALL be prompted again.

#### Scenario: Bare code is accepted
- **WHEN** the user provides only the code value
- **THEN** the flow uses that code for the token exchange

#### Scenario: Full deep-link URL is accepted
- **WHEN** the user provides `appie://login-exit?code=CODE`
- **THEN** the flow extracts `CODE` and uses it for the token exchange

#### Scenario: Query string is accepted
- **WHEN** the user provides `?code=CODE`
- **THEN** the flow extracts `CODE` and uses it for the token exchange

#### Scenario: URL-like input without a code is rejected
- **WHEN** the user provides a URL or query string that contains no code value
- **THEN** the flow reports that no code was found and prompts again

### Requirement: Token exchange
The flow SHALL exchange the authorization code for tokens by sending
`POST https://api.ah.nl/mobile-auth/v1/auth/token` with a JSON body whose
`clientId` is `appie` and which contains the code, and with the
`User-Agent: Appie/8.22.3` header. The request SHALL NOT include an
`Authorization` header. A successful response provides an access token, a
refresh token, and an expiry in seconds.

#### Scenario: Successful exchange
- **WHEN** the token endpoint returns an access token, a refresh token, and an expiry
- **THEN** the flow stores that token as specified by the token storage requirement

#### Scenario: Code rejected by the token endpoint
- **WHEN** the token endpoint returns an error status for the code
- **THEN** the flow reports that the code could not be used, no token is stored, and the user must log in again

### Requirement: Token storage
A successful exchange SHALL store the tokens in `~/.config/happie/token` as
JSON containing the access token, the refresh token, and the expiry time
derived from the returned `expires_in` at the moment of the exchange. The
file SHALL be readable and writable by the user only; the
`~/.config/happie` directory SHALL be created if it does not exist. A
successful exchange SHALL replace any previously stored token.

#### Scenario: Tokens are stored user-only
- **WHEN** the token exchange succeeds
- **THEN** `~/.config/happie/token` contains the access token, the refresh token, and the expiry time, and the file is accessible to the user only

#### Scenario: New login replaces the stored token
- **WHEN** a token file already exists and a new exchange succeeds
- **THEN** the file contains only the newly exchanged tokens

### Requirement: Secrets are not written to logs
Authorization codes, access tokens, and refresh tokens SHALL NOT appear in
log messages or any other terminal output.

#### Scenario: Successful login output
- **WHEN** the login flow runs to completion
- **THEN** no log message contains the authorization code or any token value
