## ADDED Requirements

### Requirement: Access token retrieval
The authentication capability SHALL expose `get_access_token()`, which
returns a usable access token for API requests. If the stored access token
is still valid, the stored access token SHALL be returned. If the stored
token is expired, the capability SHALL refresh it by sending
`POST https://api.ah.nl/mobile-auth/v1/auth/token/refresh` with the
`clientId` `appie` and the stored refresh token, together with the
`User-Agent: Appie/8.22.3` header and no `Authorization` header, store the
refreshed access token and refresh token as specified by the token storage
requirement, and return the new access token.

#### Scenario: Valid stored token is returned
- **WHEN** `get_access_token()` is called while the stored access token has
  not expired
- **THEN** the stored access token is returned and no request is sent to the
  refresh endpoint

#### Scenario: Expired token is refreshed
- **WHEN** `get_access_token()` is called while the stored access token has
  expired
- **THEN** the refresh endpoint is called with the stored refresh token,
  the refreshed access token and refresh token are stored, and the new
  access token is returned

#### Scenario: No token is stored
- **WHEN** `get_access_token()` is called and no token file exists
- **THEN** an authentication error is raised telling the user to log in

#### Scenario: Refresh is rejected
- **WHEN** `get_access_token()` is called with an expired token and the
  refresh endpoint returns an error status
- **THEN** an authentication error is raised and no token is stored
