import json
from pathlib import Path

import httpx

from arfigyelo_api.client import ArfigyeloClient, AsyncArfigyeloClient

FIXTURES = Path(__file__).parent / "fixtures"

TEMPLATE_PRODUCT = json.loads((FIXTURES / "products_by_category_5.json").read_text())["products"][0]


def page(items: list[dict], count: int) -> str:
    return json.dumps({"products": items, "count": count})


def make_paging_handler(page_sizes: list[int], total: int):
    """Serve `page_sizes` non-empty pages in request order, then empty pages."""
    calls: list[httpx.Request] = []
    served = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal served
        calls.append(request)
        index = served
        served += 1
        if index < len(page_sizes):
            items = [TEMPLATE_PRODUCT] * page_sizes[index]
            return httpx.Response(200, text=page(items, total))
        return httpx.Response(200, text=page([], 0))

    return handler, calls


class TestSyncIterators:
    def test_pagination_stops_on_empty_page_not_count(self):
        # 24+24+24+13 = 85 items; the empty 5th page reports count 0 (quirk #1)
        handler, calls = make_paging_handler([24, 24, 24, 13], total=85)
        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        products = list(client.iter_products_by_category(2001, limit=24))
        assert len(products) == 85
        assert len(calls) == 5
        assert int(calls[-1].url.params["offset"]) == 85

    def test_empty_first_page_yields_nothing(self):
        handler, calls = make_paging_handler([], total=0)
        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        assert list(client.iter_products_by_category(2001)) == []
        assert len(calls) == 1

    def test_single_partial_page(self):
        handler, calls = make_paging_handler([7], total=7)
        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        products = list(client.iter_products_by_category(2001))
        assert len(products) == 7
        assert len(calls) == 2  # data page + confirming empty page

    def test_iter_search(self):
        handler, calls = make_paging_handler([3], total=76)
        client = ArfigyeloClient(transport=httpx.MockTransport(handler))
        products = list(client.iter_search("tejfol", limit=48))
        assert len(products) == 3
        assert calls[0].url.path == "/api/search"
        assert calls[0].url.params["q"] == "tejfol"
        assert len(calls) == 2

    def test_iter_products_by_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/categories":
                return httpx.Response(200, text=(FIXTURES / "categories.json").read_text())
            assert request.url.path == "/api/products-by-category/107"
            offset = int(request.url.params["offset"])
            if offset == 0:
                return httpx.Response(200, text=page([TEMPLATE_PRODUCT] * 2, 2))
            return httpx.Response(200, text=page([], 0))

        calls: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        client = ArfigyeloClient(transport=httpx.MockTransport(recording))
        products = list(
            client.iter_products_by_path("tejtermek_sajt_tojas/sajt/ementali", limit=24)
        )
        assert len(products) == 2
        listing = [c for c in calls if c.url.path == "/api/products-by-category/107"]
        assert len(listing) == 2


class TestAsyncIterators:
    async def test_pagination_stops_on_empty_page(self):
        handler, calls = make_paging_handler([24, 24, 24, 13], total=85)
        client = AsyncArfigyeloClient(transport=httpx.MockTransport(handler))
        async with client:
            products = [p async for p in client.iter_products_by_category(2001, limit=24)]
        assert len(products) == 85
        assert len(calls) == 5

    async def test_empty_first_page_yields_nothing(self):
        handler, calls = make_paging_handler([], total=0)
        client = AsyncArfigyeloClient(transport=httpx.MockTransport(handler))
        async with client:
            products = [p async for p in client.iter_products_by_category(2001)]
        assert products == []
        assert len(calls) == 1

    async def test_iter_search(self):
        handler, calls = make_paging_handler([3], total=76)
        client = AsyncArfigyeloClient(transport=httpx.MockTransport(handler))
        async with client:
            products = [p async for p in client.iter_search("tejfol")]
        assert len(products) == 3
        assert len(calls) == 2
