"""Sync and async clients for the Árfigyelő API.

One request/validation/caching implementation, two facades over httpx
(docs/adr/0002-dual-sync-async-clients.md). Structural indexes (categories,
chains, shops) are always TTL-cached; price responses are cached only when
``cache_prices=True``.

Validation is local and raises :class:`ArfigyeloValidationError` before any
request for exactly the arguments the API would answer with a misleading 500
(docs/adr/0003-client-side-prevalidation.md). ``limit > 48`` is *not*
rejected: the server silently clips it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ._version import __version__
from .cache import TTLCache
from .errors import (
    ArfigyeloApiError,
    ArfigyeloConnectionError,
    ArfigyeloUnexpectedResponseError,
    ArfigyeloValidationError,
)
from .mapping import CategoryIndex, ChainIndex, ShopIndex
from .models import (
    Category,
    CategoryOrder,
    Chain,
    ProductDetail,
    ProductPage,
    ProductSummary,
    SearchOrder,
    Shop,
    ShopPriceEntry,
)

DEFAULT_BASE_URL = "https://arfigyelo.gvh.hu/api"
DEFAULT_TIMEOUT = 10.0
DEFAULT_TTL = 12 * 3600.0
LIMIT_CAP = 48  # server clips anything above; the client passes it through


# --- shared validation (local, pre-request) -------------------------------------


def _require_non_negative_int(field: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArfigyeloValidationError(field, f"must be a non-negative integer, got {value!r}")
    return value


def _require_order(field: str, order: Any, allowed: type[CategoryOrder] | type[SearchOrder]) -> str:
    value = order.value if isinstance(order, CategoryOrder | SearchOrder) else order
    if isinstance(value, str):
        try:
            order_value: str = allowed(value).value
            return order_value
        except ValueError:
            pass
    raise ArfigyeloValidationError(
        field, f"must be one of {[entry.value for entry in allowed]}, got {order!r}"
    )


def _require_query(q: Any) -> str:
    if isinstance(q, str):
        trimmed = q.strip()
        if len(trimmed) >= 3:
            return trimmed
    raise ArfigyeloValidationError(
        "q", f"must be a string of at least 3 characters after trimming, got {q!r}"
    )


def _require_shop_ids(field: str, shop_ids: Sequence[str] | None) -> str | None:
    if shop_ids is None:
        return None
    ids = list(shop_ids)
    if not ids or any(not isinstance(identifier, str) or not identifier for identifier in ids):
        raise ArfigyeloValidationError(
            field, "must be a non-empty sequence of non-empty shop uuids"
        )
    return ",".join(ids)


def _require_non_empty_str(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ArfigyeloValidationError(field, "must be a non-empty string")
    return value


# --- shared response handling ---------------------------------------------------


def _decode(response: httpx.Response) -> Any:
    """Parse a response body, raising for non-JSON bodies and the API error envelope."""
    try:
        data: Any = response.json()
    except ValueError as exc:
        raise ArfigyeloUnexpectedResponseError(response.status_code, response.text) from exc
    if (
        isinstance(data, dict)
        and isinstance(data.get("code"), str)
        and isinstance(data.get("message"), str)
    ):
        raise ArfigyeloApiError(data["code"], data["message"], response.status_code)
    return data


def _validate[ModelT: BaseModel](
    model: type[ModelT], data: Any, response: httpx.Response
) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ArfigyeloUnexpectedResponseError(response.status_code, response.text) from exc


def _cached[T](fetch: Callable[[], T], cache: TTLCache[Any], key: Any) -> T:
    cached_value: T | None = cache.get(key)
    if cached_value is None:
        result = fetch()
        cache.set(key, result)
        return result
    return cached_value


async def _async_cached[T](fetch: Callable[[], Awaitable[T]], cache: TTLCache[Any], key: Any) -> T:
    """Async counterpart of _cached; the stored value is the awaited result.

    Concurrent calls with the same empty-cache key race into redundant
    fetches, never corruption.
    """
    cached_value: T | None = cache.get(key)
    if cached_value is not None:
        return cached_value
    result = await fetch()
    cache.set(key, result)
    return result


# --- private wire envelopes (single-key response wrappers) ----------------------


class _CategoryList(BaseModel):
    model_config = ConfigDict(frozen=True)

    categories: list[Category]


class _ChainList(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain_stores: list[Chain] = Field(alias="chainStores")


class _ShopList(BaseModel):
    model_config = ConfigDict(frozen=True)

    shops: list[Shop]


class _ShopPriceList(BaseModel):
    model_config = ConfigDict(frozen=True)

    shops: list[ShopPriceEntry]


class _ClientOptions:
    """Constructor kwargs shared verbatim by both facades."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        retries: int,
        ttl: float | None,
        cache_prices: bool,
        user_agent: str,
        headers: Mapping[str, str] | None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.ttl = ttl
        self.cache_prices = cache_prices
        self.headers: dict[str, str] = {"Accept": "application/json", "User-Agent": user_agent}
        if headers is not None:
            self.headers.update(dict(headers))


class ArfigyeloClient:
    """Synchronous client for the Árfigyelő API."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 0,
        ttl: float | None = DEFAULT_TTL,
        cache_prices: bool = False,
        user_agent: str = f"arfigyelo-api/{__version__}",
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        options = _ClientOptions(
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            ttl=ttl,
            cache_prices=cache_prices,
            user_agent=user_agent,
            headers=headers,
        )
        self._cache_prices = options.cache_prices
        self._index_cache: TTLCache[Any] = TTLCache[Any](options.ttl)
        self._price_cache: TTLCache[Any] = TTLCache[Any](options.ttl)
        if transport is None:
            transport = httpx.HTTPTransport(retries=options.retries)
        self._http = httpx.Client(
            base_url=options.base_url,
            timeout=options.timeout,
            transport=transport,
            headers=options.headers,
        )

    # --- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ArfigyeloClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # --- transport plumbing ----------------------------------------------------

    def _get(self, path: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        try:
            return self._http.get(path, params=params)
        except httpx.TransportError as exc:
            raise ArfigyeloConnectionError(str(exc)) from exc

    def _model[ModelT: BaseModel](
        self, model: type[ModelT], path: str, params: Mapping[str, str] | None = None
    ) -> ModelT:
        response = self._get(path, params)
        data = _decode(response)
        return _validate(model, data, response)

    @staticmethod
    def _price_key(path: str, params: Mapping[str, str]) -> tuple[Any, ...]:
        return (path, tuple(sorted(params.items())))

    # --- structural endpoints (always cached) ----------------------------------

    def get_categories(self) -> list[Category]:
        """GET /categories — the full category tree (cached with ttl)."""

        def fetch() -> list[Category]:
            return self._model(_CategoryList, "categories").categories

        return _cached(fetch, self._index_cache, "categories")

    def get_chains(self) -> list[Chain]:
        """GET /chain-stores — all retail chains (cached with ttl)."""

        def fetch() -> list[Chain]:
            return self._model(_ChainList, "chain-stores").chain_stores

        return _cached(fetch, self._index_cache, "chain-stores")

    def get_shops(self) -> list[Shop]:
        """GET /shops — all physical shops (cached with ttl)."""

        def fetch() -> list[Shop]:
            return self._model(_ShopList, "shops").shops

        return _cached(fetch, self._index_cache, "shops")

    # --- product endpoints (cached only under cache_prices=True) ---------------

    def get_products_by_category(
        self,
        category_id: int,
        *,
        limit: int = 12,
        offset: int = 0,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """GET /products-by-category/{id} — one page of a category listing."""
        limit_v = _require_non_negative_int("limit", limit)
        offset_v = _require_non_negative_int("offset", offset)
        order_v = _require_order("order", order, CategoryOrder)
        shop_ids_v = _require_shop_ids("shop_ids", shop_ids)
        path = f"products-by-category/{category_id}"
        params: dict[str, str] = {"limit": str(limit_v), "offset": str(offset_v), "order": order_v}
        if shop_ids_v is not None:
            params["shopIds"] = shop_ids_v

        def fetch() -> ProductPage:
            return self._model(ProductPage, path, params)

        if self._cache_prices:
            return _cached(fetch, self._price_cache, self._price_key(path, params))
        return fetch()

    def get_products_by_path(
        self,
        path: str | Sequence[str],
        *,
        limit: int = 12,
        offset: int = 0,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """Category listing resolved by category path (mapping layer)."""
        category_id = self.get_category_by_path(path).id
        return self.get_products_by_category(
            category_id, limit=limit, offset=offset, order=order, shop_ids=shop_ids
        )

    def search(
        self,
        q: str,
        *,
        limit: int = 48,
        offset: int = 0,
        order: SearchOrder | str = SearchOrder.RELEVANCE,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """GET /search — text search (accent-insensitive server-side)."""
        query = _require_query(q)
        limit_v = _require_non_negative_int("limit", limit)
        offset_v = _require_non_negative_int("offset", offset)
        order_v = _require_order("order", order, SearchOrder)
        shop_ids_v = _require_shop_ids("shop_ids", shop_ids)
        params: dict[str, str] = {
            "q": query,
            "limit": str(limit_v),
            "offset": str(offset_v),
            "order": order_v,
        }
        if shop_ids_v is not None:
            params["shopIds"] = shop_ids_v

        def fetch() -> ProductPage:
            return self._model(ProductPage, "search", params)

        if self._cache_prices:
            return _cached(fetch, self._price_cache, self._price_key("search", params))
        return fetch()

    def get_product(self, product_id: str) -> ProductDetail:
        """GET /product/{id} — product detail with chain-level prices."""
        product_id = _require_non_empty_str("product_id", product_id)
        path = f"product/{product_id}"

        def fetch() -> ProductDetail:
            return self._model(ProductDetail, path)

        if self._cache_prices:
            return _cached(fetch, self._price_cache, self._price_key(path, {}))
        return fetch()

    def get_product_shop_prices(
        self, product_id: str, shop_uuids: Sequence[str]
    ) -> list[ShopPriceEntry]:
        """GET /product/{id}/shop/{shopUuids} — per-shop prices for one product.

        Only shops that have a price are returned; loyalty prices never appear
        here (NORMAL and DISCOUNTED only).
        """
        product_id = _require_non_empty_str("product_id", product_id)
        joined = _require_shop_ids("shop_uuids", shop_uuids)
        assert joined is not None  # _require_shop_ids raises on empty/None input
        path = f"product/{product_id}/shop/{joined}"

        def fetch() -> list[ShopPriceEntry]:
            return self._model(_ShopPriceList, path).shops

        if self._cache_prices:
            return _cached(fetch, self._price_cache, self._price_key(path, {}))
        return fetch()

    # --- pagination iterators (stop on empty page, never on count) -------------

    def iter_products_by_category(
        self,
        category_id: int,
        *,
        limit: int = LIMIT_CAP,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> Iterator[ProductSummary]:
        """Yield every product of a category, paging internally.

        Terminates on an empty ``products`` page; ``count`` is unreliable on
        empty pages (API quirk #1).
        """
        offset = 0
        while True:
            page = self.get_products_by_category(
                category_id, limit=limit, offset=offset, order=order, shop_ids=shop_ids
            )
            yield from page.products
            if not page.products:
                return
            offset += len(page.products)

    def iter_products_by_path(
        self,
        path: str | Sequence[str],
        *,
        limit: int = LIMIT_CAP,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> Iterator[ProductSummary]:
        """Category listing iterator resolved by category path."""
        category_id = self.get_category_by_path(path).id
        yield from self.iter_products_by_category(
            category_id, limit=limit, order=order, shop_ids=shop_ids
        )

    def iter_search(
        self,
        q: str,
        *,
        limit: int = LIMIT_CAP,
        order: SearchOrder | str = SearchOrder.RELEVANCE,
        shop_ids: Sequence[str] | None = None,
    ) -> Iterator[ProductSummary]:
        """Yield every search result, paging internally."""
        offset = 0
        while True:
            page = self.search(q, limit=limit, offset=offset, order=order, shop_ids=shop_ids)
            yield from page.products
            if not page.products:
                return
            offset += len(page.products)

    # --- mapping layer ---------------------------------------------------------

    def category_index(self) -> CategoryIndex:
        """Category path/id index over the (cached) category tree."""
        return CategoryIndex(self.get_categories())

    def chain_index(self) -> ChainIndex:
        """Chain index over the (cached) chain list."""
        return ChainIndex(self.get_chains())

    def shop_index(self) -> ShopIndex:
        """Shop index over the (cached) shop list."""
        return ShopIndex(self.get_shops())

    def get_category_by_path(self, path: str | Sequence[str]) -> Category:
        """Resolve a category by slug path: ``"tejtermek_sajt_tojas/sajt/ementali"``."""
        return self.category_index().by_path(path)

    def get_chain(self, *, uuid: str | None = None, name: str | None = None) -> Chain:
        """Resolve a chain by uuid or (case-insensitive) name; uuid wins when both."""
        return self.chain_index().get(uuid=uuid, name=name)

    def get_shop(self, uuid: str) -> Shop:
        """Resolve a shop by its uuid (e.g. ``spar-110``)."""
        return self.shop_index().get(uuid)

    def find_shops(
        self,
        *,
        city: str | None = None,
        postal_code: str | None = None,
        chain_uuid: str | None = None,
    ) -> list[Shop]:
        """AND-combined shop filters; ``city`` is a case-insensitive prefix match."""
        return self.shop_index().find(city=city, postal_code=postal_code, chain_uuid=chain_uuid)


class AsyncArfigyeloClient:
    """Asynchronous client for the Árfigyelő API (mirrors ArfigyeloClient)."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 0,
        ttl: float | None = DEFAULT_TTL,
        cache_prices: bool = False,
        user_agent: str = f"arfigyelo-api/{__version__}",
        headers: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        options = _ClientOptions(
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            ttl=ttl,
            cache_prices=cache_prices,
            user_agent=user_agent,
            headers=headers,
        )
        self._cache_prices = options.cache_prices
        self._index_cache: TTLCache[Any] = TTLCache[Any](options.ttl)
        self._price_cache: TTLCache[Any] = TTLCache[Any](options.ttl)
        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=options.retries)
        self._http = httpx.AsyncClient(
            base_url=options.base_url,
            timeout=options.timeout,
            transport=transport,
            headers=options.headers,
        )

    # --- lifecycle -----------------------------------------------------------

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncArfigyeloClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    # --- transport plumbing ----------------------------------------------------

    async def _get(self, path: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        try:
            return await self._http.get(path, params=params)
        except httpx.TransportError as exc:
            raise ArfigyeloConnectionError(str(exc)) from exc

    async def _model[ModelT: BaseModel](
        self, model: type[ModelT], path: str, params: Mapping[str, str] | None = None
    ) -> ModelT:
        response = await self._get(path, params)
        data = _decode(response)
        return _validate(model, data, response)

    @staticmethod
    def _price_key(path: str, params: Mapping[str, str]) -> tuple[Any, ...]:
        return (path, tuple(sorted(params.items())))

    # --- structural endpoints (always cached) ----------------------------------

    async def get_categories(self) -> list[Category]:
        """GET /categories — the full category tree (cached with ttl)."""

        async def fetch() -> list[Category]:
            return (await self._model(_CategoryList, "categories")).categories

        return await _async_cached(fetch, self._index_cache, "categories")

    async def get_chains(self) -> list[Chain]:
        """GET /chain-stores — all retail chains (cached with ttl)."""

        async def fetch() -> list[Chain]:
            return (await self._model(_ChainList, "chain-stores")).chain_stores

        return await _async_cached(fetch, self._index_cache, "chain-stores")

    async def get_shops(self) -> list[Shop]:
        """GET /shops — all physical shops (cached with ttl)."""

        async def fetch() -> list[Shop]:
            return (await self._model(_ShopList, "shops")).shops

        return await _async_cached(fetch, self._index_cache, "shops")

    # --- product endpoints (cached only under cache_prices=True) ---------------

    async def get_products_by_category(
        self,
        category_id: int,
        *,
        limit: int = 12,
        offset: int = 0,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """GET /products-by-category/{id} — one page of a category listing."""
        limit_v = _require_non_negative_int("limit", limit)
        offset_v = _require_non_negative_int("offset", offset)
        order_v = _require_order("order", order, CategoryOrder)
        shop_ids_v = _require_shop_ids("shop_ids", shop_ids)
        path = f"products-by-category/{category_id}"
        params: dict[str, str] = {"limit": str(limit_v), "offset": str(offset_v), "order": order_v}
        if shop_ids_v is not None:
            params["shopIds"] = shop_ids_v

        async def fetch() -> ProductPage:
            return await self._model(ProductPage, path, params)

        if self._cache_prices:
            return await _async_cached(fetch, self._price_cache, self._price_key(path, params))
        return await fetch()

    async def get_products_by_path(
        self,
        path: str | Sequence[str],
        *,
        limit: int = 12,
        offset: int = 0,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """Category listing resolved by category path (mapping layer)."""
        category = await self.get_category_by_path(path)
        return await self.get_products_by_category(
            category.id, limit=limit, offset=offset, order=order, shop_ids=shop_ids
        )

    async def search(
        self,
        q: str,
        *,
        limit: int = 48,
        offset: int = 0,
        order: SearchOrder | str = SearchOrder.RELEVANCE,
        shop_ids: Sequence[str] | None = None,
    ) -> ProductPage:
        """GET /search — text search (accent-insensitive server-side)."""
        query = _require_query(q)
        limit_v = _require_non_negative_int("limit", limit)
        offset_v = _require_non_negative_int("offset", offset)
        order_v = _require_order("order", order, SearchOrder)
        shop_ids_v = _require_shop_ids("shop_ids", shop_ids)
        params: dict[str, str] = {
            "q": query,
            "limit": str(limit_v),
            "offset": str(offset_v),
            "order": order_v,
        }
        if shop_ids_v is not None:
            params["shopIds"] = shop_ids_v

        async def fetch() -> ProductPage:
            return await self._model(ProductPage, "search", params)

        if self._cache_prices:
            return await _async_cached(fetch, self._price_cache, self._price_key("search", params))
        return await fetch()

    async def get_product(self, product_id: str) -> ProductDetail:
        """GET /product/{id} — product detail with chain-level prices."""
        product_id = _require_non_empty_str("product_id", product_id)
        path = f"product/{product_id}"

        async def fetch() -> ProductDetail:
            return await self._model(ProductDetail, path)

        if self._cache_prices:
            return await _async_cached(fetch, self._price_cache, self._price_key(path, {}))
        return await fetch()

    async def get_product_shop_prices(
        self, product_id: str, shop_uuids: Sequence[str]
    ) -> list[ShopPriceEntry]:
        """GET /product/{id}/shop/{shopUuids} — per-shop prices for one product.

        Only shops that have a price are returned; loyalty prices never appear
        here (NORMAL and DISCOUNTED only).
        """
        product_id = _require_non_empty_str("product_id", product_id)
        joined = _require_shop_ids("shop_uuids", shop_uuids)
        assert joined is not None  # _require_shop_ids raises on empty/None input
        path = f"product/{product_id}/shop/{joined}"

        async def fetch() -> list[ShopPriceEntry]:
            return (await self._model(_ShopPriceList, path)).shops

        if self._cache_prices:
            return await _async_cached(fetch, self._price_cache, self._price_key(path, {}))
        return await fetch()

    # --- pagination iterators (stop on empty page, never on count) -------------

    async def iter_products_by_category(
        self,
        category_id: int,
        *,
        limit: int = LIMIT_CAP,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> AsyncIterator[ProductSummary]:
        """Yield every product of a category, paging internally (async).

        Terminates on an empty ``products`` page; ``count`` is unreliable on
        empty pages (API quirk #1).
        """
        offset = 0
        while True:
            page = await self.get_products_by_category(
                category_id, limit=limit, offset=offset, order=order, shop_ids=shop_ids
            )
            for product in page.products:
                yield product
            if not page.products:
                return
            offset += len(page.products)

    async def iter_products_by_path(
        self,
        path: str | Sequence[str],
        *,
        limit: int = LIMIT_CAP,
        order: CategoryOrder | str = CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids: Sequence[str] | None = None,
    ) -> AsyncIterator[ProductSummary]:
        """Category listing iterator resolved by category path (async)."""
        category = await self.get_category_by_path(path)
        async for product in self.iter_products_by_category(
            category.id, limit=limit, order=order, shop_ids=shop_ids
        ):
            yield product

    async def iter_search(
        self,
        q: str,
        *,
        limit: int = LIMIT_CAP,
        order: SearchOrder | str = SearchOrder.RELEVANCE,
        shop_ids: Sequence[str] | None = None,
    ) -> AsyncIterator[ProductSummary]:
        """Yield every search result, paging internally (async)."""
        offset = 0
        while True:
            page = await self.search(q, limit=limit, offset=offset, order=order, shop_ids=shop_ids)
            for product in page.products:
                yield product
            if not page.products:
                return
            offset += len(page.products)

    # --- mapping layer ---------------------------------------------------------

    async def category_index(self) -> CategoryIndex:
        """Category path/id index over the (cached) category tree."""
        return CategoryIndex(await self.get_categories())

    async def chain_index(self) -> ChainIndex:
        """Chain index over the (cached) chain list."""
        return ChainIndex(await self.get_chains())

    async def shop_index(self) -> ShopIndex:
        """Shop index over the (cached) shop list."""
        return ShopIndex(await self.get_shops())

    async def get_category_by_path(self, path: str | Sequence[str]) -> Category:
        """Resolve a category by slug path: ``"tejtermek_sajt_tojas/sajt/ementali"``."""
        index = await self.category_index()
        return index.by_path(path)

    async def get_chain(self, *, uuid: str | None = None, name: str | None = None) -> Chain:
        """Resolve a chain by uuid or (case-insensitive) name; uuid wins when both."""
        index = await self.chain_index()
        return index.get(uuid=uuid, name=name)

    async def get_shop(self, uuid: str) -> Shop:
        """Resolve a shop by its uuid (e.g. ``spar-110``)."""
        index = await self.shop_index()
        return index.get(uuid)

    async def find_shops(
        self,
        *,
        city: str | None = None,
        postal_code: str | None = None,
        chain_uuid: str | None = None,
    ) -> list[Shop]:
        """AND-combined shop filters; ``city`` is a case-insensitive prefix match."""
        index = await self.shop_index()
        return index.find(city=city, postal_code=postal_code, chain_uuid=chain_uuid)
