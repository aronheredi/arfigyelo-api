# Árfigyelő

A Python client package for the public Árfigyelő (arfigyelo.gvh.hu) price-comparison API of Hungarian retail chains. This file is the glossary for the domain.

## Language

### Retail landscape

**Chain**:
A national retail chain (e.g. Spar, Lidl, Penny) that sets prices; identified by a chain UUID.
_Avoid_: Chain store, chainStore (wire name), retailer

**Shop**:
A single physical store of a Chain, with address and coordinates; identified by a shop UUID (e.g. `spar-110`). Chain UUIDs are never valid shop identifiers.
_Avoid_: Store, chain store, üzlet
**Category Path**:
The full slug path of a Category from the tree root (e.g. `tejtermek_sajt_tojas/sajt/ementali`); identical to the web route after `/k/`. Identifies a Category uniquely.
_Avoid_: Category slug (for the full path)

**Category**:
A node in the product classification tree. Only depth-1 and leaf categories contain products; depth-1 categories aggregate their leaf descendants. Root categories return no products.
_Avoid_: Category node (wire name)

### Products and prices

**ProductSummary**:
A product as returned by listing endpoints (category listing, search): has `minUnitPrice` and per-Chain price aggregates.
_Avoid_: Product list item, list model

**ProductDetail**:
A product as returned by the detail endpoint: has `categoryId`, per-Chain `pricesMax` and shop availability. A distinct model, not a superset of ProductSummary.
_Avoid_: Product (unqualified, when the endpoint shape matters)

**ShopPrice**:
One row of a per-shop price query: the price of one product in one Shop. The wire response mislabels the product id as `uuid`.
_Avoid_: Shop uuid (for the product id field)

**Price**:
A single price point of a product at a Chain or Shop. One of three types: `NORMAL`, `DISCOUNTED`, or `LOYALTY`. Amounts are exact forint (HUF) values with up to two decimals.

**Unit Price**:
The price per base `unit` (`kg`, `l`, `db`, `g`) computed as shelf price divided by packaging size. `minUnitPrice` excludes `LOYALTY` prices.
_Avoid_: unitAmount (wire name)
