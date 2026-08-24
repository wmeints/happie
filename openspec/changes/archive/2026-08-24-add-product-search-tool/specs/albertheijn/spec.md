# Purpose

The Albert Heijn API client is the single point of contact with `api.ah.nl`:
it attaches the required application headers and the user's bearer token to
every request, and translates the API responses into typed models.

## ADDED Requirements

### Requirement: Product search
The client SHALL search the Albert Heijn product assortment by calling
`GET https://api.ah.nl/mobile-services/product/search/v2` with the search
term, page `0`, the requested result size, and the relevance sort. For a
search term it SHALL return the products in the API's relevance order, at
most the requested number of results.

#### Scenario: Search returns products
- **WHEN** a search is requested for a term that matches products
- **THEN** the client returns the matching products, sorted by relevance, up
  to the requested result count

#### Scenario: Search returns no matches
- **WHEN** a search is requested for a term that matches no products
- **THEN** the client returns an empty list of products

### Requirement: Product model
Each returned product SHALL expose its webshop identifier, title, brand,
current price, price before any bonus promotion, bonus flag, bonus mechanism
text, package size, online availability, and main category.

#### Scenario: Product fields are translated from the API response
- **WHEN** the search API returns a product with a bonus promotion
- **THEN** the returned product carries the webshop identifier, the name and
  brand, both the current and the pre-bonus price, the flag that it is on
  bonus, and the bonus mechanism text (for example "2e halve prijs")

#### Scenario: Non-bonus product
- **WHEN** the search API returns a product without a bonus promotion
- **THEN** the returned product reports that it is not on bonus and its
  current price equals its price before bonus

### Requirement: Authenticated requests
Every request the client makes to `api.ah.nl` SHALL carry the application
headers `User-Agent: Appie/8.22.3`, `Content-Type: application/json`, and
`x-application: AHWEBSHOP` (the search endpoint rejects requests without
an application context), together with the bearer token returned by the
authentication capability.

#### Scenario: Search without a usable token
- **WHEN** no stored token exists, or the stored token cannot be refreshed
- **THEN** the client reports an authentication error and makes no request to
  the product search endpoint

### Requirement: API errors are reported
If the product search endpoint returns an error response, the client SHALL
report the failure as an error including the HTTP status, without printing
the request's bearer token.

#### Scenario: Search endpoint fails
- **WHEN** the product search endpoint returns a status other than 200
- **THEN** the client raises an error that identifies the failing request
  and its status, and no log output contains the bearer token
