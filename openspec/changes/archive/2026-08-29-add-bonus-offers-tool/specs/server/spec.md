# server Delta: add-bonus-offers-tool

## ADDED Requirements

### Requirement: Bonus offers tool
The server SHALL expose a `bonus_offers` tool that takes an optional result
limit and returns the products on bonus during the current Albert Heijn
bonus period, as provided by the Albert Heijn API client capability's
bonus-offers method: the bonus products of all national categories, with
every multi-product bonus group expanded to its concrete products, each
product carrying its identifier, name, brand, prices, bonus mechanism
text, package size, online availability, and bonus category. When a limit
is given, the tool SHALL return at most that many products, keeping the
API's order; without a limit it SHALL return all products.

#### Scenario: Tool returns the week's bonus products
- **WHEN** an MCP client calls `bonus_offers` without arguments and the
  current bonus period has national bonus products
- **THEN** the tool returns one product per on-bonus product, each carrying
  its identifier, name, brand, prices, the deal text as bonus mechanism,
  package size, online availability, and bonus category

#### Scenario: Limit trims the result
- **WHEN** an MCP client calls `bonus_offers` with a limit smaller than the
  number of on-bonus products
- **THEN** the tool returns at most the limited number of products, in the
  API's order

#### Scenario: No bonus products in the period
- **WHEN** the current bonus period has no national bonus products
- **THEN** the tool returns an empty list

#### Scenario: Tool failure does not stop the server
- **WHEN** a `bonus_offers` call fails, for example because no token is
  stored or one of the bonus endpoints returns an error
- **THEN** the tool reports the error to the MCP client and the server
  keeps running for further tool calls
