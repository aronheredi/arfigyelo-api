import httpx
import pytest

from arfigyelo_api.client import ArfigyeloClient, AsyncArfigyeloClient
from arfigyelo_api.errors import ArfigyeloValidationError
from arfigyelo_api.models import CategoryOrder, SearchOrder


def forbidden_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request should be made, got {request.url.path}")


@pytest.fixture
def client() -> ArfigyeloClient:
    return ArfigyeloClient(transport=httpx.MockTransport(forbidden_handler))


class TestCategoryEndpointValidation:
    def test_negative_limit(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_products_by_category(2001, limit=-1)
        assert excinfo.value.field == "limit"

    def test_negative_offset(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_products_by_category(2001, offset=-1)
        assert excinfo.value.field == "offset"

    @pytest.mark.parametrize("limit", [1.5, True, "12", None])
    def test_non_integer_limit(self, client, limit):
        with pytest.raises(ArfigyeloValidationError):
            client.get_products_by_category(2001, limit=limit)

    @pytest.mark.parametrize("offset", [1.5, True, "0", None])
    def test_non_integer_offset(self, client, offset):
        with pytest.raises(ArfigyeloValidationError):
            client.get_products_by_category(2001, offset=offset)

    def test_bool_is_not_an_integer(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.get_products_by_category(2001, limit=True, offset=True)

    def test_relevance_rejected_on_category(self, client):
        # quirk #8: relevance works only on /api/search; the category endpoint 500s
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_products_by_category(2001, order="relevance")
        assert excinfo.value.field == "order"

    def test_bogus_order_rejected(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.get_products_by_category(2001, order="bogus")

    def test_empty_shop_ids(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_products_by_category(2001, shop_ids=[])
        assert excinfo.value.field == "shop_ids"

    def test_blank_shop_id(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.get_products_by_category(2001, shop_ids=["spar-536", ""])

    def test_valid_enum_instance_accepted(self):
        client = ArfigyeloClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text='{"products": [], "count": 0}')
            )
        )
        page = client.get_products_by_category(2001, order=CategoryOrder.AMOUNT_DESC)
        assert page.products == []

    def test_limit_above_cap_passes_through(self):
        # server clips limit > 48 silently; the client must NOT reject it
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, text='{"products": [], "count": 0}')

        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        client.get_products_by_category(2001, limit=100)
        assert calls[0].url.params["limit"] == "100"


class TestSearchValidation:
    def test_short_query(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.search("ab")
        assert excinfo.value.field == "q"

    def test_blank_query(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.search("   ")

    def test_query_trimmed_too_short(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.search("  ab  ")

    def test_bogus_order(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.search("tejfol", order="bogus")

    def test_negative_limit(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.search("tejfol", limit=-1)

    def test_relevance_accepted_on_search(self):
        client = ArfigyeloClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text='{"products": [], "count": 0}')
            )
        )
        page = client.search("tejfol", order=SearchOrder.RELEVANCE)
        assert page.count == 0

    def test_category_order_accepted_on_search(self):
        client = ArfigyeloClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text='{"products": [], "count": 0}')
            )
        )
        client.search("tejfol", order="unitAmount_asc")


class TestShopPricesValidation:
    def test_empty_shop_uuids(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_product_shop_prices("some-product", [])
        assert excinfo.value.field == "shop_uuids"

    def test_blank_shop_uuid(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.get_product_shop_prices("some-product", ["spar-536", ""])

    def test_blank_product_id(self, client):
        with pytest.raises(ArfigyeloValidationError):
            client.get_product("")


class TestAsyncValidation:
    async def test_validation_raises_before_request(self):
        client = AsyncArfigyeloClient(transport=httpx.MockTransport(forbidden_handler))
        async with client:
            with pytest.raises(ArfigyeloValidationError):
                await client.get_products_by_category(2001, limit=-1)
            with pytest.raises(ArfigyeloValidationError):
                await client.search("ab")
            with pytest.raises(ArfigyeloValidationError):
                await client.get_product_shop_prices("p", [])


class TestValidationErrorShape:
    def test_message_contains_field(self, client):
        with pytest.raises(ArfigyeloValidationError) as excinfo:
            client.get_products_by_category(2001, limit=-1)
        assert "limit" in str(excinfo.value)

    def test_is_value_error(self, client):
        with pytest.raises(ValueError):
            client.search("ab")
