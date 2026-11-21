"""Pydantic models for the Árfigyelő API wire format.

Conventions:
- snake_case attributes, camelCase serialization aliases (the wire format).
- every money field is ``Decimal``; pydantic parses JSON numbers into Decimal
  from their lexical representation, so values stay exact (no float
  round-trip). See docs/adr/0001-money-as-decimal.md.
- models are frozen: responses are immutable data.
- list responses and the detail endpoint return *different* product shapes;
  they are separate models, not one all-optional model.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class PriceType(StrEnum):
    NORMAL = "NORMAL"
    DISCOUNTED = "DISCOUNTED"
    LOYALTY = "LOYALTY"


class CategoryOrder(StrEnum):
    """``order`` values accepted by the category listing endpoint."""

    UNIT_AMOUNT_ASC = "unitAmount_asc"
    UNIT_AMOUNT_DESC = "unitAmount_desc"
    AMOUNT_ASC = "amount_asc"
    AMOUNT_DESC = "amount_desc"


class SearchOrder(StrEnum):
    """``order`` values accepted by the search endpoint.

    ``relevance`` is valid *only* on search; the category endpoint answers it
    with 500 (API quirk #8).
    """

    RELEVANCE = "relevance"
    UNIT_AMOUNT_ASC = "unitAmount_asc"
    UNIT_AMOUNT_DESC = "unitAmount_desc"
    AMOUNT_ASC = "amount_asc"
    AMOUNT_DESC = "amount_desc"


class ListPrice(_ApiModel):
    """A single price point in a listing response (endpoints 4 and 5)."""

    type: PriceType
    amount: Decimal
    unit_amount: Decimal
    same_amount_everywhere: bool


class ChainPrices(_ApiModel):
    """Per-chain price aggregate in a listing response."""

    id: str  # chain-store UUID
    name: str
    price_same_everywhere: bool
    product_min_amount: Decimal
    prices: list[ListPrice]


class ProductSummary(_ApiModel):
    """A product as returned by listing endpoints (category listing, search)."""

    id: str
    name: str
    image_url: str
    unit: str  # observed: kg, l, db, g
    unit_title: str  # observed: db, csomag
    bulk: bool
    return_type: str | None  # observed: "one-way-return-fee"
    return_fee: Decimal
    packaging: str  # numeric string, size in `unit`
    category_path: str
    min_unit_price: Decimal
    prices_of_chain_stores: list[ChainPrices]


class ProductPage(_ApiModel):
    """One page of a listing response.

    ``count`` is the total only on non-empty pages; an empty page reports
    ``count: 0`` (API quirk #1). Paginate until ``products`` is empty, never
    until ``offset >= count``.
    """

    products: list[ProductSummary]
    count: int


class Category(_ApiModel):
    """A node of the category tree (recursive)."""

    id: int
    name: str
    path: str  # full slug path from the root; matches the web route /k/{path}
    icon: str | None
    category_nodes: list[Category]


class Chain(_ApiModel):
    """A retail chain (Spar, Lidl, ...). ``image_url`` is a slug, not a URL."""

    uuid: str
    name: str
    image_url: str


class ShopLocation(_ApiModel):
    latitude: float
    longitude: float


class Shop(_ApiModel):
    """A physical store of a chain. Shop UUIDs (e.g. ``spar-110``) are the only
    valid values for shop filters and the per-shop endpoint; chain UUIDs are
    silently rejected there."""

    uuid: str
    postal_code: str
    city: str
    address: str
    chain_store_uuid: str
    location: ShopLocation
    opening_time: str  # human-readable; '#' separates lines


class DetailPrice(_ApiModel):
    """A single price point in a detail (or per-shop) response; these endpoints
    omit ``sameAmountEverywhere`` and carry it on the chain object instead."""

    type: PriceType
    amount: Decimal
    unit_amount: Decimal


class DetailChain(_ApiModel):
    """Per-chain entry in a product detail response.

    ``prices_max`` is populated only when the chain sells the product at
    different prices in different shops; it then holds the maximum variant(s).
    """

    uuid: str
    name: str
    image_url: str
    prices: list[DetailPrice]
    prices_max: list[DetailPrice]
    price_same_everywhere: bool
    available_in_shops: list[str]


class ProductDetail(_ApiModel):
    """A product as returned by the detail endpoint (endpoint 6)."""

    id: str
    name: str
    image_url: str
    unit: str
    unit_title: str
    bulk: bool
    return_type: str | None
    return_fee: Decimal
    packaging: str
    category_id: str
    category_path: str
    chain_stores: list[DetailChain]


class ShopPriceEntry(_ApiModel):
    """One row of a per-shop price query (endpoint 7).

    The wire response mislabels the product id as ``uuid``; the canonical
    name here is ``product_id``.
    """

    product_id: str = Field(serialization_alias="uuid", validation_alias="uuid")
    shop_uuid: str
    prices: list[DetailPrice]


class ShopPrices(_ApiModel):
    """Response envelope of endpoint 7. Prices include NORMAL and DISCOUNTED
    but never LOYALTY (loyalty prices appear only in product details)."""

    shops: list[ShopPriceEntry]
