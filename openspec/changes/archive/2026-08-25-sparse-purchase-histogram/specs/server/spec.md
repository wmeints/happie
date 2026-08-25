# server Delta: sparse-purchase-histogram

## MODIFIED Requirements

### Requirement: Purchase frequency tool
The server SHALL expose a `purchase_frequency` tool that takes a window
length in days, defaulting to 90, and an optional result limit. It SHALL
return the per-product purchase statistics provided by the Albert Heijn API
client capability's purchase-history method: for each unique product, its
product key, name, total quantity purchased in the window, total amount
spent, and a sparse per-day histogram with one entry per purchased day, each
entry carrying that day's date and that day's total quantity, ordered by
date. When a limit is given, the tool SHALL return at most that many
statistics, keeping the highest total quantities first; without a limit it
SHALL return all statistics.

#### Scenario: Default window returns purchase statistics
- **WHEN** an MCP client calls `purchase_frequency` without arguments and
  the account purchased products in the last 90 days
- **THEN** the tool returns one statistic per purchased product, sorted by
  total quantity in descending order, each carrying its product key, name,
  total quantity, total spend, and a sparse per-day histogram whose entries
  are date-stamped

#### Scenario: Limit trims the result
- **WHEN** an MCP client calls `purchase_frequency` with a limit smaller
  than the number of purchased products
- **THEN** the tool returns at most the limited number of statistics,
  starting with the highest total quantities

#### Scenario: No purchases in the window
- **WHEN** no in-store receipts or delivered webshop orders fall inside the
  window
- **THEN** the tool returns an empty list

#### Scenario: Tool failure does not stop the server
- **WHEN** a `purchase_frequency` call fails, for example because no token is
  stored or one of the purchase-history endpoints returns an error
- **THEN** the tool reports the error to the MCP client and the server keeps
  running for further tool calls
