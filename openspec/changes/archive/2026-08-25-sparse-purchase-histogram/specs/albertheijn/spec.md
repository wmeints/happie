# albertheijn Delta: sparse-purchase-histogram

## MODIFIED Requirements

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
