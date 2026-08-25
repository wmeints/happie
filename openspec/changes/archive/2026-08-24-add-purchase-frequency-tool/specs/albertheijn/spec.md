# albertheijn Delta: add-purchase-frequency-tool

## ADDED Requirements

### Requirement: Purchase history aggregation
The client SHALL provide a purchase-history method that, for a requested
time window in days (default 90, ending today), returns one purchase
statistic per unique product purchased during the window, merging two
sources: in-store receipt items (kassabon) and delivered webshop order
items. Each statistic SHALL expose a product key, a product name, the total
quantity purchased in the window, the number of distinct days on which the
product was purchased, the total amount spent on the product in the window,
the calendar date on which the window starts, and a dense per-day purchase
count with exactly one entry per day of the window (zero on days with no
purchase).

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
- **THEN** its per-day count has an entry for every day of the window, with
  the purchased quantities on the two days and zero on all other days, and
  the window start date is reported so the entries can be aligned to dates

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
