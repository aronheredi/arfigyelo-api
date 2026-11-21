from decimal import Decimal

import pytest
from pydantic import ValidationError

from arfigyelo_api.errors import (
    ArfigyeloApiError,
    ArfigyeloConnectionError,
    ArfigyeloError,
    ArfigyeloUnexpectedResponseError,
    ArfigyeloValidationError,
)
from arfigyelo_api.models import (
    Category,
    Chain,
    ChainPrices,
    DetailPrice,
    ListPrice,
    ProductDetail,
    ProductPage,
    ProductSummary,
    Shop,
    ShopPriceEntry,
    ShopPrices,
)


def parse_categories(load_fixture):
    return [Category.model_validate(c) for c in load_fixture("categories.json")["categories"]]


def test_parse_categories(load_fixture):
    cats = parse_categories(load_fixture)
    assert len(cats) == 9
    root = cats[0]
    assert (root.id, root.name, root.path, root.icon) == (
        1001,
        "Tejtermék, sajt, tojás",
        "tejtermek_sajt_tojas",
        None,
    )
    # max depth 2: root -> group -> leaf
    assert len(root.category_nodes) == 8
    sajt = root.category_nodes[3]
    assert (sajt.id, sajt.path) == (2010, "tejtermek_sajt_tojas/sajt")
    ementali = sajt.category_nodes[3]
    assert (ementali.id, ementali.name, ementali.path) == (
        107,
        "Ementáli",
        "tejtermek_sajt_tojas/sajt/ementali",
    )
    assert ementali.category_nodes == []


def test_parse_chain_stores(load_fixture):
    chains = [Chain.model_validate(c) for c in load_fixture("chain_stores.json")["chainStores"]]
    assert len(chains) == 9
    spar = chains[0]
    assert spar.uuid == "3ccc9f35-604c-4ccf-8376-64822ce4bc70"
    assert spar.name == "Spar"
    assert spar.image_url == "spar"  # a slug, not a URL


def test_parse_shops(load_fixture):
    shops = [Shop.model_validate(s) for s in load_fixture("shops.json")["shops"]]
    assert len(shops) == 6
    first = shops[0]
    assert (first.uuid, first.postal_code, first.city, first.address) == (
        "spar-110",
        "1011",
        "Budapest I.",
        "Batthyány tér 5-6",
    )
    assert first.chain_store_uuid == "3ccc9f35-604c-4ccf-8376-64822ce4bc70"
    assert first.location.latitude == pytest.approx(47.506062)
    assert first.location.longitude == pytest.approx(19.038035)
    assert first.opening_time == ""
    # '#' is the line separator inside openingTime
    assert "#" in shops[1].opening_time


def test_parse_product_page(load_fixture):
    page = ProductPage.model_validate(load_fixture("products_by_category_5.json"))
    assert page.count == 40
    assert len(page.products) == 24
    product = page.products[0]
    assert product.id == "penny-2076"
    assert product.name == "Sissy tejföl 20% 450g"
    assert product.unit == "kg"
    assert product.unit_title == "db"
    assert product.bulk is False
    assert product.return_type is None
    assert product.return_fee == Decimal("0")
    assert product.packaging == "0.45"
    assert product.category_path == "tejtermek_sajt_tojas/tejfol/tejfol_20"
    # exact money, not float
    assert product.min_unit_price == Decimal("886.67")
    chain = product.prices_of_chain_stores[0]
    assert isinstance(chain, ChainPrices)
    assert chain.id == "53b66cb6-a24f-420d-9861-d38757467d07"
    assert chain.name == "Penny"
    assert chain.price_same_everywhere is True
    assert chain.product_min_amount == Decimal("399.0")
    assert chain.prices[0].type.value == "NORMAL"
    assert chain.prices[0].amount == Decimal("449.0")
    assert chain.prices[0].unit_amount == Decimal("997.78")
    assert chain.prices[0].same_amount_everywhere is True
    assert chain.prices[1].type.value == "DISCOUNTED"


def test_decimal_exactness():
    price = ListPrice.model_validate(
        {"type": "NORMAL", "amount": 886.67, "unitAmount": 997.78, "sameAmountEverywhere": True}
    )
    assert price.amount == Decimal("886.67")
    assert price.unit_amount == Decimal("997.78")


def test_parse_product_detail(load_fixture):
    detail = ProductDetail.model_validate(load_fixture("product_5999550782526.json"))
    assert detail.id == "5999550782526"
    assert detail.name == "S-Budget friss csirkemellfilé"
    assert detail.category_id == "18"
    assert detail.category_path == "hus_hal_felvagott/szarnyas/csirkemell"
    assert detail.bulk is True
    assert detail.unit == "kg"
    assert detail.unit_title == "kg"
    assert detail.packaging == "1"
    chain = detail.chain_stores[0]
    assert chain.uuid == "3ccc9f35-604c-4ccf-8376-64822ce4bc70"
    assert chain.name == "Spar"
    assert chain.image_url == "spar"
    assert chain.price_same_everywhere is True
    assert chain.prices[0].type.value == "NORMAL"
    assert chain.prices[0].amount == Decimal("1924.0")
    assert chain.prices_max == []
    assert len(chain.available_in_shops) == 254
    assert chain.available_in_shops[0] == "spar-104"


def test_parse_shop_prices(load_fixture):
    prices = ShopPrices.model_validate(load_fixture("product_shop_prices.json"))
    assert len(prices.shops) == 2
    entry = prices.shops[0]
    assert isinstance(entry, ShopPriceEntry)
    # the wire 'uuid' is the product id, renamed canonically
    assert entry.product_id == "5999545594554"
    assert entry.shop_uuid == "spar-536"
    assert entry.prices[0].amount == Decimal("99.0")
    assert entry.prices[0].unit_amount == Decimal("66.0")
    assert prices.shops[1].shop_uuid == "spar-622"


def test_loyalty_price_type():
    price = ListPrice.model_validate(
        {"type": "LOYALTY", "amount": 10, "unitAmount": 10, "sameAmountEverywhere": True}
    )
    assert price.type.value == "LOYALTY"


def test_roundtrip_by_alias(load_fixture):
    page = ProductPage.model_validate(load_fixture("products_by_category_5.json"))
    again = ProductPage.model_validate_json(page.model_dump_json(by_alias=True))
    assert again == page


def test_shop_price_entry_roundtrip_keeps_wire_alias(load_fixture):
    prices = ShopPrices.model_validate(load_fixture("product_shop_prices.json"))
    dumped = prices.model_dump_json(by_alias=True)
    assert '"uuid":"5999545594554"' in dumped


def test_extra_fields_ignored(load_fixture):
    raw = load_fixture("products_by_category_5.json")
    raw["products"][0]["futureField"] = "surprise"
    page = ProductPage.model_validate(raw)
    assert page.products[0].id == "penny-2076"


def test_models_are_frozen(load_fixture):
    page = ProductPage.model_validate(load_fixture("products_by_category_5.json"))
    with pytest.raises(ValidationError):
        page.count = 1


def test_same_amount_split_between_list_and_detail_prices():
    assert "same_amount_everywhere" in ListPrice.model_fields
    assert "same_amount_everywhere" not in DetailPrice.model_fields


def test_product_summary_is_not_product_detail():
    assert "min_unit_price" in ProductSummary.model_fields
    assert "min_unit_price" not in ProductDetail.model_fields
    assert "category_id" in ProductDetail.model_fields
    assert "category_id" not in ProductSummary.model_fields


def test_error_hierarchy():
    assert issubclass(ArfigyeloApiError, ArfigyeloError)
    assert issubclass(ArfigyeloConnectionError, ArfigyeloError)
    assert issubclass(ArfigyeloUnexpectedResponseError, ArfigyeloError)
    assert issubclass(ArfigyeloValidationError, ArfigyeloError)
    assert issubclass(ArfigyeloValidationError, ValueError)


def test_api_error_str():
    err = ArfigyeloApiError(
        code="NOT_FOUND_PRODUCT",
        message="No product found based on the product UUID! [uuid: nope]",
        status_code=404,
    )
    assert str(err) == "NOT_FOUND_PRODUCT: No product found based on the product UUID! [uuid: nope]"


def test_unexpected_response_error_attributes():
    err = ArfigyeloUnexpectedResponseError(status_code=403, body="<html>blocked</html>")
    assert err.status_code == 403
    assert "blocked" in err.body


def test_validation_error_attributes():
    err = ArfigyeloValidationError(field="limit", reason="must be a non-negative integer")
    assert err.field == "limit"
    assert "limit" in str(err)
