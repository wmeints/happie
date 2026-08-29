# albertheijn Delta: add-bonus-offers-tool

## ADDED Requirements

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
