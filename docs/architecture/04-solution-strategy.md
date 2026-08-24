# Solution strategy

This section covers the solution strategy for the application. It lists key
decisions needed to implement the application successfully.

## Requesting an access token

We'll use a dedicated command `happie auth login` to authenticate and get an 
access token. This access token is then stored in `~/.config/happie/token`
for use by the MCP server.

If the MCP server can't find the token file, or can't refresh an expired token,
we'll notify the user via a log message. The MCP server can keep running, 
because the user can get a new authentication token via the command-line.

## Communicating with the Albert Heijn API

The Albert Heijn API is hosted at https://api.ah.nl/ with different endpoints
for various functionality. It requires specific API headers to be present
for it to work normally.

- `User-Agent: Appie/8.22.3`
- `Content-Type: application/json`

The API also expects the `Authorization: Bearer <token>` to authorize requests.
Use the token value stored in `~/.config/happie/token` as the value for the 
bearer token.

See https://gist.github.com/jabbink/8bfa44bdfc535d696b340c46d228fdd1 for more
details on how to access the Albert Heijn API.

## Technology choices

The MCP server is implemented using [FastMCP][fastmcp] in Python. We're using
[typer][typer] to implement the command-line interface. The command 
`happie serve` will run the MCP server.

We'll use [pytest][pytest] to run automated tests for validating the 
functionality in the MCP server. We'll use [ruff][ruff] for linting the
code to ensure good quality code.

We use [uv][uv] to manage the python packages needed for the application

[fastmcp]: https://gofastmcp.com/getting-started/welcome
[typer]: https://typer.tiangolo.com/
[pytest]: https://docs.pytest.org/en/stable/
[ruff]: https://docs.astral.sh/ruff/
[uv]: https://astral.sh/uv

