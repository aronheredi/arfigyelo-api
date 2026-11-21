from pathlib import Path

import httpx
import pytest

from arfigyelo_api.client import DEFAULT_BASE_URL, ArfigyeloClient, AsyncArfigyeloClient
from arfigyelo_api.errors import (
    ArfigyeloApiError,
    ArfigyeloConnectionError,
    ArfigyeloUnexpectedResponseError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def json_response(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, text=fixture_text(name), headers={"content-type": "application/json"}
    )


SPAR_UUID = "3ccc9f35-604c-4ccf-8376-64822ce4bc70"


def make_handler(calls: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        path = request.url.path
        if path == "/api/categories":
            return json_response("categories.json")
        if path == "/api/chain-stores":
            return json_response("chain_stores.json")
        if path == "/api/shops":
            return json_response("shops.json")
        if path == "/api/products-by-category/5":
            return json_response("products_by_category_5.json")
        if path == "/api/products-by-category/107":
            return json_response("products_by_category_47.json")
        if path == "/api/search":
            return json_response("search_tejfol.json")
        if path == "/api/product/5999550782526":
            return json_response("product_5999550782526.json")
        if path == "/api/product/nope":
            return json_response("error_not_found_product.json", status=404)
        if path == "/api/product/5999545594554/shop/spar-536,spar-622":
            return json_response("product_shop_prices.json")
        return json_response("spring_404.json", status=404)

    return handler


def make_client(**kwargs) -> ArfigyeloClient:
    return ArfigyeloClient(transport=httpx.MockTransport(make_handler()), **kwargs)


def make_async_client(**kwargs) -> AsyncArfigyeloClient:
    return AsyncArfigyeloClient(transport=httpx.MockTransport(make_handler()), **kwargs)


class TestStructuralEndpoints:
    def test_get_categories(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        cats = client.get_categories()
        assert len(cats) == 9
        assert calls[0].url.path == "/api/categories"
        # structural index: cached across calls
        client.get_categories()
        assert len(calls) == 1

    def test_get_chains(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        chains = client.get_chains()
        assert len(chains) == 9
        assert chains[0].name == "Spar"
        client.get_chains()
        assert len(calls) == 1

    def test_get_shops(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        shops = client.get_shops()
        assert len(shops) == 6
        assert shops[0].uuid == "spar-110"
        client.get_shops()
        assert len(calls) == 1

    def test_ttl_zero_refetches_structural(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)), ttl=0.0)
        client.get_categories()
        client.get_categories()
        assert len(calls) == 2


class TestProductEndpoints:
    def test_get_products_by_category(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        page = client.get_products_by_category(5)
        assert page.count == 40
        assert len(page.products) == 24
        request = calls[0]
        assert request.url.path == "/api/products-by-category/5"
        assert request.method == "GET"
        # documented defaults: limit 12, offset 0, order unitAmount_asc
        assert request.url.params["limit"] == "12"
        assert request.url.params["offset"] == "0"
        assert request.url.params["order"] == "unitAmount_asc"

    def test_get_products_by_category_explicit_params(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        client.get_products_by_category(
            5, limit=24, offset=24, order="unitAmount_desc", shop_ids=["spar-536", "spar-622"]
        )
        params = calls[0].url.params
        assert params["limit"] == "24"
        assert params["offset"] == "24"
        assert params["order"] == "unitAmount_desc"
        assert params["shopIds"] == "spar-536,spar-622"

    def test_search(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        page = client.search("tejföl")
        assert page.count == 76
        request = calls[0]
        assert request.url.path == "/api/search"
        # documented defaults: limit 48, order relevance
        assert request.url.params["q"] == "tejföl"
        assert request.url.params["limit"] == "48"
        assert request.url.params["order"] == "relevance"

    def test_get_product(self):
        client = make_client()
        detail = client.get_product("5999550782526")
        assert detail.id == "5999550782526"
        assert detail.category_id == "18"
        assert detail.chain_stores[0].name == "Spar"

    def test_get_product_shop_prices(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        entries = client.get_product_shop_prices("5999545594554", ["spar-536", "spar-622"])
        assert len(entries) == 2
        assert entries[0].product_id == "5999545594554"
        assert entries[1].shop_uuid == "spar-622"
        assert calls[0].url.path == "/api/product/5999545594554/shop/spar-536,spar-622"


class TestMappingLayer:
    def test_get_category_by_path(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        cat = client.get_category_by_path("tejtermek_sajt_tojas/sajt/ementali")
        assert cat.id == 107
        cat2 = client.get_category_by_path(["tejtermek_sajt_tojas", "tej"])
        assert cat2.id == 2001
        # one categories request, reused
        assert len([c for c in calls if c.url.path == "/api/categories"]) == 1

    def test_get_products_by_path_resolves_id(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        page = client.get_products_by_path("tejtermek_sajt_tojas/sajt/ementali")
        assert page.count == 28  # products_by_category_47 fixture
        listing = [c for c in calls if c.url.path == "/api/products-by-category/107"]
        assert len(listing) == 1

    def test_get_chain_by_name_and_uuid(self):
        client = make_client()
        assert client.get_chain(name="lidl").name == "Lidl"
        assert client.get_chain(uuid=SPAR_UUID).name == "Spar"

    def test_get_shop(self):
        client = make_client()
        assert client.get_shop("spar-536").city == "Budapest XI."

    def test_find_shops(self):
        client = make_client()
        found = client.find_shops(city="Budapest")
        assert len(found) == 4
        assert [s.uuid for s in client.find_shops(postal_code="1117")] == ["spar-536"]
        assert [s.uuid for s in client.find_shops(city="Budapest", chain_uuid=SPAR_UUID)] == [
            "spar-110",
            "spar-536",
        ]

    def test_indexes_share_the_structural_cache(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        client.category_index()
        client.chain_index()
        client.shop_index()
        client.get_categories()
        assert len(calls) == 3  # categories, chain-stores, shops — once each


class TestPriceCaching:
    def test_prices_not_cached_by_default(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        client.get_product("5999550782526")
        client.get_product("5999550782526")
        assert len(calls) == 2

    def test_cache_prices_caches_identical_calls(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(
            transport=httpx.MockTransport(make_handler(calls)), cache_prices=True
        )
        first = client.get_product("5999550782526")
        second = client.get_product("5999550782526")
        assert first is second  # the cached model object itself
        assert len(calls) == 1

    def test_cache_prices_different_params_miss(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(
            transport=httpx.MockTransport(make_handler(calls)), cache_prices=True
        )
        client.get_products_by_category(5, offset=0)
        client.get_products_by_category(5, offset=24)
        assert len(calls) == 2

    def test_cache_prices_respects_ttl(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(
            transport=httpx.MockTransport(make_handler(calls)), cache_prices=True, ttl=0.0
        )
        client.get_product("5999550782526")
        client.get_product("5999550782526")
        assert len(calls) == 2


class TestErrors:
    def test_api_error_envelope(self):
        client = make_client()
        with pytest.raises(ArfigyeloApiError) as excinfo:
            client.get_product("nope")
        err = excinfo.value
        assert err.code == "NOT_FOUND_PRODUCT"
        assert err.status_code == 404
        assert "No product found" in err.message

    def test_search_input_error_envelope(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return json_response("error_search_input.json", status=400)

        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ArfigyeloApiError) as excinfo:
            client.search("tejfol")
        assert excinfo.value.code == "SEARCH-INPUT-ERROR"
        assert excinfo.value.status_code == 400

    def test_spring_404_is_unexpected_response(self):
        client = make_client()
        with pytest.raises(ArfigyeloUnexpectedResponseError) as excinfo:
            client.get_product("totally-unknown-path")
        assert excinfo.value.status_code == 404

    def test_waf_403_html_is_unexpected_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403, text=fixture_text("waf_403.html"), headers={"content-type": "text/html"}
            )

        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ArfigyeloUnexpectedResponseError) as excinfo:
            client.search("tejfol")
        assert excinfo.value.status_code == 403
        assert "Hamarosan indul" in excinfo.value.body

    def test_transport_error_becomes_connection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ArfigyeloConnectionError):
            client.get_categories()

    def test_bad_json_is_unexpected_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json at all")

        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ArfigyeloUnexpectedResponseError):
            client.get_categories()


class TestClientConfiguration:
    def test_default_headers(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        client.get_categories()
        assert calls[0].headers["user-agent"].startswith("arfigyelo-api/")
        assert calls[0].headers["accept"] == "application/json"

    def test_custom_user_agent_and_headers(self):
        calls: list[httpx.Request] = []
        client = ArfigyeloClient(
            transport=httpx.MockTransport(make_handler(calls)),
            user_agent="my-app/1.0",
            headers={"X-Custom": "yes"},
        )
        client.get_categories()
        assert calls[0].headers["user-agent"] == "my-app/1.0"
        assert calls[0].headers["x-custom"] == "yes"

    def test_default_base_url_constant(self):
        assert DEFAULT_BASE_URL == "https://arfigyelo.gvh.hu/api"

    def test_context_manager_closes(self):
        with make_client() as client:
            client.get_categories()
        assert client._http.is_closed

    def test_retries_accepted_without_transport(self):
        client = ArfigyeloClient(retries=3)
        client.close()


class TestAsyncClient:
    async def test_get_categories(self):
        calls: list[httpx.Request] = []
        client = AsyncArfigyeloClient(transport=httpx.MockTransport(make_handler(calls)))
        async with client:
            cats = await client.get_categories()
        assert len(cats) == 9
        assert len(calls) == 1

    async def test_get_products_by_category(self):
        client = make_async_client()
        async with client:
            page = await client.get_products_by_category(5)
        assert page.count == 40

    async def test_get_product_and_shop_prices(self):
        client = make_async_client()
        async with client:
            detail = await client.get_product("5999550782526")
            entries = await client.get_product_shop_prices(
                "5999545594554", ["spar-536", "spar-622"]
            )
        assert detail.id == "5999550782526"
        assert entries[0].product_id == "5999545594554"

    async def test_mapping_layer(self):
        client = make_async_client()
        async with client:
            cat = await client.get_category_by_path("tejtermek_sajt_tojas/sajt/ementali")
            found = await client.find_shops(city="Budapest")
            chain = await client.get_chain(name="lidl")
        assert cat.id == 107
        assert len(found) == 4
        assert chain.name == "Lidl"

    async def test_api_error(self):
        client = make_async_client()
        async with client:
            with pytest.raises(ArfigyeloApiError) as excinfo:
                await client.get_product("nope")
        assert excinfo.value.code == "NOT_FOUND_PRODUCT"

    async def test_cache_prices(self):
        calls: list[httpx.Request] = []
        client = AsyncArfigyeloClient(
            transport=httpx.MockTransport(make_handler(calls)), cache_prices=True
        )
        async with client:
            await client.get_product("5999550782526")
            await client.get_product("5999550782526")
        assert len(calls) == 1

    async def test_connection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = AsyncArfigyeloClient(transport=httpx.MockTransport(handler))
        async with client:
            with pytest.raises(ArfigyeloConnectionError):
                await client.get_categories()
