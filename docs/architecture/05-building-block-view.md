# Building block view

## Context

This is the context diagram from [the context and scope](03-context-and-scope.md)
zoomed in on the happie MCP server. The surrounding actors stay the same, but
the system is now broken down into its top-level building blocks.

```mermaid
C4Container
    title Top-level building blocks of the happie MCP server

    Person(user, "User", "Wants a shopping list for the coming week's groceries.")
    System_Ext(hermes, "Hermes", "Agent that talks to the user and composes the weekly shopping list.")

    System_Boundary(happie, "happie") {
        Container(cli, "Command-line interface", "Python, typer", "Offers the `happie auth login` and `happie serve` commands.")
        Container(auth, "Authentication", "Python", "Runs the OAuth flow via the local browser and refreshes expired tokens.")
        Container(mcp, "MCP server", "Python, FastMCP", "Exposes the assortment, shopping list, and ordering history as MCP tools.")
        Container(client, "Albert Heijn API client", "Python", "Adds the required API headers and the bearer token to every request.")
        ContainerDb(store, "Token store", "File, ~/.config/happie/token", "Holds the access token, readable by the user only.")
    }

    System_Ext(ah, "Albert Heijn API", "api.ah.nl. Owns the product assortment, the shopping list, and the ordering history.")

    Rel(user, cli, "Runs `happie auth login` and `happie serve`")
    Rel(hermes, mcp, "Searches products, reviews past purchases, and updates the shopping list", "MCP")
    Rel(cli, auth, "Starts the login flow")
    Rel(cli, mcp, "Starts the server")
    Rel(auth, store, "Writes the access token")
    Rel(auth, ah, "Requests and refreshes the access token", "OAuth")
    Rel(mcp, client, "Calls the assortment, shopping list, and order history endpoints")
    Rel(client, store, "Reads the access token")
    Rel(client, ah, "Reads the assortment and ordering history, and maintains the shopping list", "HTTPS")
    Rel(user, ah, "Reviews the shopping list and completes the purchase")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

| Building block          | Responsibility                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Command-line interface  | Entry point for the user. Wires `happie auth login` to the authentication flow and `happie serve` to the MCP server.           |
| Authentication          | Performs the OAuth flow in the local browser, refreshes expired tokens, and hands the result to the token store.               |
| MCP server              | Exposes the assortment, shopping list, and ordering history as MCP tools. Deliberately offers no tool for placing an order.    |
| Albert Heijn API client | Single point of contact with api.ah.nl. Applies the required headers and the bearer token, and translates responses to models. |
| Token store             | Keeps the access token in `~/.config/happie/token` with user-only permissions.                                                 |

The MCP server keeps running when the token is missing or cannot be refreshed;
it logs the problem so the user can obtain a new token from the command line.

## Application module structure

Every building block from the previous section maps onto exactly one package
under `src/happie`. Each package is a deep module: it keeps its HTTP calls,
parsing, and file handling internal and exposes a handful of names through its
`__init__.py`.

```mermaid
C4Component
    title Packages of the happie MCP server

    Container_Boundary(happie, "happie") {
        Component(root, "happie", "__init__.py", "Entry point for the `happie` script. Hands control to the CLI.")
        Component(cli, "happie.cli", "typer", "Defines the `auth login` and `serve` commands and their options.")
        Component(server, "happie.server", "FastMCP", "Builds the MCP server and registers the assortment, shopping list, and order history tools.")
        Component(ah, "happie.albertheijn", "Python", "Wraps the Albert Heijn API and returns typed models.")
        Component(auth, "happie.auth", "Python", "Runs the OAuth flow, stores the token, and refreshes it when it expires.")
    }

    Rel(root, cli, "Runs the typer app")
    Rel(cli, auth, "login()")
    Rel(cli, server, "serve()")
    Rel(server, ah, "Calls the API client")
    Rel(ah, auth, "get_access_token()")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

| Package              | Public interface                              | Contains                                                                                |
| -------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `happie`             | `main()`                                      | The console script declared in `pyproject.toml`. Nothing else.                           |
| `happie.cli`         | `app`                                         | The typer application and the command definitions.                                       |
| `happie.server`      | `serve()`                                     | The FastMCP instance and the tool functions, one module per group of tools.              |
| `happie.albertheijn` | `AlbertHeijnClient` and the models it returns | The required API headers, the endpoint calls, and the response models.                   |
| `happie.auth`        | `login()`, `get_access_token()`               | The OAuth flow, the browser redirect handler, and the token file in `~/.config/happie`.  |

Dependencies point in one direction only: `happie` → `happie.cli` →
`happie.server` → `happie.albertheijn` → `happie.auth`. The CLI also calls
`happie.auth` directly for the login command. No package imports a package that
sits above it, so there are no import cycles.

Tests live in `tests/` and mirror this structure, with one module per package,
so a failing test points at a single building block.
