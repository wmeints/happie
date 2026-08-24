# server Specification

## Purpose

The MCP server exposes the Albert Heijn grocery domain — the product
assortment, the shopping list, and the ordering history — to MCP clients as
tools, and it can be started from the command line over stdio.

## Requirements

### Requirement: Product search tool
The server SHALL expose a `search_products` tool that takes a search term
and an optional result limit defaulting to ten, and returns a list of
matching products with each product's identifier, name, brand, current and
pre-bonus price, bonus information, package size, online availability, and
main category, as provided by the Albert Heijn API client capability.

#### Scenario: Tool returns matching products
- **WHEN** an MCP client calls `search_products` with a search term that
  matches products
- **THEN** the tool returns up to the requested limit of products, each
  carrying its identifier, name, brand, prices, bonus information, package
  size, online availability, and main category

#### Scenario: Tool with no matches
- **WHEN** an MCP client calls `search_products` with a search term that
  matches no products
- **THEN** the tool returns an empty list

#### Scenario: Tool failure does not stop the server
- **WHEN** a `search_products` call fails, for example because no token is
  stored or the API returns an error
- **THEN** the tool reports the error to the MCP client and the server keeps
  running for further tool calls

### Requirement: Running the server
The server SHALL be runnable via `serve()`, which starts the server on
stdio so that an MCP client can communicate with it.

#### Scenario: Server starts on stdio
- **WHEN** `serve()` is called
- **THEN** the MCP server reads tool calls from stdin and writes responses
  to stdout until the client disconnects
