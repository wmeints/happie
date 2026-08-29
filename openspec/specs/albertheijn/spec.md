# albertheijn Specification

## Purpose

The Albert Heijn API client is the single point of contact with `api.ah.nl`:
it attaches the required application headers and the user's bearer token to
every request, and translates the API responses into typed models.

## Requirements

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

### Requirement: Purchase history aggregation
The client SHALL provide a purchase-history method that, for a requested
time window in days (default 90, ending today), returns one purchase
statistic per unique product purchased during the window, merging two
sources: in-store receipt items (kassabon) and delivered webshop order
items. Each statistic SHALL expose a product key, a product name, the total
quantity purchased in the window, the total amount spent on the product in
the window, and a sparse per-day histogram: one entry per calendar day on
which the product was actually purchased, each entry carrying that day's
date and the total quantity purchased on that day, ordered by date
ascending. The histogram SHALL be empty when the product was not purchased
on any day of the window.

Products whose receipt line items are identified by a store point-of-sale
product id SHALL be converted to the Albert Heijn webshop product id; when
the same webshop product id is bought in-store and online it SHALL appear as
a single statistic. Webshop order items already carry the webshop product
id. Receipt items whose point-of-sale id cannot be converted to a webshop
product id SHALL still be reported, keyed by their point-of-sale id instead.
The result SHALL be sorted by total quantity in descending order.

#### Scenario: Product bought in-store and online merges into one statistic
- **WHEN** the same webshop product is purchased on an in-store receipt and
  in a delivered webshop order within the window
- **THEN** exactly one statistic is returned for that product, and its total
  quantity is the sum of the quantities from both sources

#### Scenario: Unconvertible receipt product keeps a fallback key
- **WHEN** a receipt line item's point-of-sale id has no webshop product id
  conversion
- **THEN** the product still appears in the result, keyed by its
  point-of-sale id rather than a webshop id

#### Scenario: Dense per-day counts cover the whole window
- **WHEN** a product was purchased on only two days of a 90-day window
- **THEN** its histogram has exactly two entries, one per purchased day,
  each entry carrying that day's date and that day's total quantity, ordered
  by date; no entries are returned for the days with no purchase

#### Scenario: Purchases before the window are excluded
- **WHEN** a receipt or a delivered order falls before the window start date
- **THEN** its items contribute nothing to the result

### Requirement: Only completed purchases count
Delivered webshop orders SHALL contribute to the purchase history; cancelled
and still-open (confirmed or active) webshop orders SHALL NOT contribute.
In-store receipts are by definition completed transactions and SHALL all
count when they fall inside the window.

#### Scenario: Cancelled webshop order is excluded
- **WHEN** a webshop order within the window has the cancelled state
- **THEN** none of its products appear in the result because of that order

#### Scenario: No purchases in the window
- **WHEN** no receipts and no delivered orders fall inside the window
- **THEN** the method returns an empty list of statistics

### Requirement: Purchase history failure handling
If no usable access token exists, the purchase-history method SHALL report an
authentication error and make no request. If any of the purchase-history
endpoints returns an error response, the method SHALL report the failure,
identifying the failing request and its HTTP status, and SHALL NOT return a
partially aggregated result. No error or log output SHALL contain the bearer
token.

#### Scenario: One failed detail request fails the whole call
- **WHEN** fetching the line items of one order or receipt fails while other
  purchases were read successfully
- **THEN** the method raises an error for the failing request instead of
  returning a partial histogram, and no output contains the bearer token

### Requirement: Bonus offers
The client SHALL provide a bonus-offers method that returns the products on
bonus during the current bonus period, across all national bonus categories.
For each product listed directly in a category's bonus section it SHALL
return the product with its webshop identifier, title, brand, prices,
package size, online availability, and bonus category; and for every
multi-product bonus group (a segment offer such as "Alle Galbani") it SHALL
resolve the group and return its concrete products instead. Every returned
product SHALL be flagged as being on bonus and SHALL carry the deal text
(for example "1+1 gratis", "30% korting", or "2 VOOR 5.00") as its bonus
mechanism. A product that appears in more than one category, or both in a
category section and inside a bonus group, SHALL be returned exactly once.
Products whose group resolves to no products SHALL contribute nothing to
the result. The result SHALL be empty when the current bonus period has no
products in any national category.
Folder products that the API does not flag as being on bonus SHALL
contribute nothing to the result.

#### Scenario: Bonus product listed in a category section
- **WHEN** a product is listed directly in the bonus section of a national
  category
- **THEN** the method returns that product with its webshop identifier,
  title, brand, prices, and package size, flagged as being on bonus, with
  the deal text as its bonus mechanism and the bonus category as its
  category

#### Scenario: Multi-product bonus group is expanded
- **WHEN** a national category's bonus section contains a multi-product
  bonus group with concrete products
- **THEN** the method returns each of the group's products, flagged as
  being on bonus, each carrying the group's deal text as its bonus
  mechanism

#### Scenario: Product in two categories appears once
- **WHEN** the same webshop product appears in the bonus sections of two
  different national categories
- **THEN** the method returns exactly one entry for that product

#### Scenario: Group without resolvable products contributes nothing
- **WHEN** a multi-product bonus group resolves to no products
- **THEN** no entry is returned for that group

#### Scenario: Folder product not flagged as bonus contributes nothing
- **WHEN** a product listed in a national category's bonus section or
  bonus group is not flagged as being on bonus by the API
- **THEN** the method returns no entry for that product

#### Scenario: Empty bonus period
- **WHEN** the current bonus period has no products in any national
  category
- **THEN** the method returns an empty list

### Requirement: Bonus offers failure handling
If no usable access token exists, the bonus-offers method SHALL report an
authentication error and make no request. If the bonus metadata request,
any category-section request, or any bonus-group resolution request returns
an error response, the method SHALL report the failure, identifying the
failing request and its status, and SHALL NOT return a partial result. No
error or log output SHALL contain the bearer token.

#### Scenario: One failed section request fails the whole call
- **WHEN** fetching the bonus section of one category fails while the other
  categories were read successfully
- **THEN** the method raises an error for the failing request instead of
  returning a partial product list, and no output contains the bearer
  token

#### Scenario: Bonus group resolution fails
- **WHEN** resolving one multi-product bonus group returns an error
- **THEN** the method raises an error for the failing request instead of
  returning a partial product list
