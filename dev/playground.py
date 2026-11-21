"""Interactive FastAPI playground for manually exercising the Árfigyelő API.

Every endpoint is a thin wrapper over :class:`arfigyelo_api.ArfigyeloClient`;
the request is passed through unchanged and client exceptions are mapped to
JSON error responses instead of stack traces.

Run from the repo root::

    uv sync                 # installs the dev group (fastapi, uvicorn)
    uv run uvicorn dev.playground:app --reload
    # then open http://127.0.0.1:8000/docs

Or directly::

    uv run python dev/playground.py

Environment overrides:

    ARFIGYELO_BASE_URL       default https://arfigyelo.gvh.hu/api
    ARFIGYELO_TIMEOUT        seconds, default 10
    ARFIGYELO_TTL            structural cache TTL seconds, default 43200 (0 disables)
    ARFIGYELO_CACHE_PRICES   "1"/"true" caches price responses too
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from arfigyelo_api import (
    DEFAULT_BASE_URL,
    ArfigyeloApiError,
    ArfigyeloClient,
    ArfigyeloConnectionError,
    ArfigyeloError,
    ArfigyeloUnexpectedResponseError,
    ArfigyeloValidationError,
    Category,
    CategoryOrder,
    Chain,
    ProductDetail,
    ProductPage,
    SearchOrder,
    Shop,
    ShopPriceEntry,
    __version__,
)

_TRUE = {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.base_url = os.environ.get("ARFIGYELO_BASE_URL", DEFAULT_BASE_URL)
    app.state.client = ArfigyeloClient(
        base_url=app.state.base_url,
        timeout=float(os.environ.get("ARFIGYELO_TIMEOUT", "10")),
        ttl=float(os.environ.get("ARFIGYELO_TTL", "43200")),
        cache_prices=os.environ.get("ARFIGYELO_CACHE_PRICES", "").lower() in _TRUE,
    )
    try:
        yield
    finally:
        app.state.client.close()


app = FastAPI(
    title="Árfigyelő API playground",
    description="Thin manual-testing client. Open /docs and use 'Try it out'.",
    version=__version__,
    lifespan=lifespan,
)


def _client(request: Request) -> ArfigyeloClient:
    return request.app.state.client


@app.exception_handler(ArfigyeloValidationError)
async def _validation_error(_: Request, exc: ArfigyeloValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation", "field": exc.field, "message": exc.reason},
    )


@app.exception_handler(ArfigyeloApiError)
async def _api_error(_: Request, exc: ArfigyeloApiError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "upstream_api",
            "code": exc.code,
            "message": exc.message,
            "upstream_status": exc.status_code,
        },
    )


@app.exception_handler(ArfigyeloUnexpectedResponseError)
async def _unexpected_error(_: Request, exc: ArfigyeloUnexpectedResponseError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "unexpected_response",
            "upstream_status": exc.status_code,
            "body": exc.body,
        },
    )


@app.exception_handler(ArfigyeloConnectionError)
async def _connection_error(_: Request, exc: ArfigyeloConnectionError) -> JSONResponse:
    return JSONResponse(status_code=504, content={"error": "connection", "message": str(exc)})


@app.exception_handler(ArfigyeloError)
async def _generic_error(_: Request, exc: ArfigyeloError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "client", "message": str(exc)})


@app.get("/", tags=["meta"])
def root(request: Request) -> dict[str, str]:
    """Playground entry point."""
    return {
        "upstream": request.app.state.base_url,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


# --- structural endpoints ------------------------------------------------------


@app.get("/categories", response_model=list[Category], tags=["structural"])
def categories(request: Request) -> list[Category]:
    """GET /categories — full category tree (client-cached)."""
    return _client(request).get_categories()


@app.get("/categories/by-path", response_model=Category, tags=["mapping"])
def category_by_path(
    request: Request,
    path: Annotated[str, Query(description="slug path, e.g. tejtermek_sajt_tojas/sajt/ementali")],
) -> Category:
    """Resolve a category by its slug path (not a numeric id)."""
    return _client(request).get_category_by_path(path)


@app.get("/chains", response_model=list[Chain], tags=["structural"])
def chains(request: Request) -> list[Chain]:
    """GET /chain-stores — all retail chains (client-cached)."""
    return _client(request).get_chains()


@app.get("/chains/lookup", response_model=Chain, tags=["mapping"])
def chain_lookup(
    request: Request,
    uuid: Annotated[str | None, Query(description="chain uuid")] = None,
    name: Annotated[str | None, Query(description="case-insensitive chain name")] = None,
) -> Chain:
    """Resolve a chain by uuid or name (uuid wins when both are set)."""
    return _client(request).get_chain(uuid=uuid, name=name)


@app.get("/shops", response_model=list[Shop], tags=["structural"])
def shops(request: Request) -> list[Shop]:
    """GET /shops — every physical shop (client-cached; large response)."""
    return _client(request).get_shops()


@app.get("/shops/find", response_model=list[Shop], tags=["mapping"])
def find_shops(
    request: Request,
    city: Annotated[
        str | None, Query(description="case-insensitive prefix match, e.g. 'Budap'")
    ] = None,
    postal_code: Annotated[str | None, Query(description="exact postal code")] = None,
    chain_uuid: Annotated[str | None, Query(description="chain uuid, not shop uuid")] = None,
) -> list[Shop]:
    """Filter the cached shop index (filters are AND-combined)."""
    return _client(request).find_shops(city=city, postal_code=postal_code, chain_uuid=chain_uuid)


@app.get("/shops/{uuid}", response_model=Shop, tags=["mapping"])
def shop(request: Request, uuid: str) -> Shop:
    """Resolve a shop by uuid (e.g. ``spar-110``)."""
    return _client(request).get_shop(uuid)


# --- product endpoints ---------------------------------------------------------

OrderQuery = Annotated[
    CategoryOrder | None,
    Query(description="listing order; defaults to unitAmount_asc"),
]
ShopIdsQuery = Annotated[
    list[str] | None,
    Query(description="repeat for multiple shop uuids (NOT chain uuids)"),
]


@app.get("/products/by-category/{category_id}", response_model=ProductPage, tags=["products"])
def products_by_category(
    request: Request,
    category_id: int,
    limit: Annotated[int, Query(ge=0)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: OrderQuery = None,
    shop_ids: ShopIdsQuery = None,
) -> ProductPage:
    """GET /products-by-category/{id} — one page of a category listing."""
    return _client(request).get_products_by_category(
        category_id,
        limit=limit,
        offset=offset,
        order=order or CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids=shop_ids,
    )


@app.get("/products/by-path", response_model=ProductPage, tags=["products"])
def products_by_path(
    request: Request,
    path: Annotated[str, Query(description="slug path, e.g. tejtermek_sajt_tojas/sajt/ementali")],
    limit: Annotated[int, Query(ge=0)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: OrderQuery = None,
    shop_ids: ShopIdsQuery = None,
) -> ProductPage:
    """Category listing resolved through the mapping layer."""
    return _client(request).get_products_by_path(
        path,
        limit=limit,
        offset=offset,
        order=order or CategoryOrder.UNIT_AMOUNT_ASC,
        shop_ids=shop_ids,
    )


@app.get("/search", response_model=ProductPage, tags=["products"])
def search(
    request: Request,
    q: Annotated[str, Query(min_length=3, description="accent-insensitive text")],
    limit: Annotated[int, Query(ge=0)] = 48,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[
        SearchOrder | None, Query(description="search-only order; 'relevance' is valid here")
    ] = None,
    shop_ids: ShopIdsQuery = None,
) -> ProductPage:
    """GET /search — text search."""
    return _client(request).search(
        q,
        limit=limit,
        offset=offset,
        order=order or SearchOrder.RELEVANCE,
        shop_ids=shop_ids,
    )


@app.get("/product/{product_id}", response_model=ProductDetail, tags=["products"])
def product(request: Request, product_id: str) -> ProductDetail:
    """GET /product/{id} — detail endpoint (different shape from listings)."""
    return _client(request).get_product(product_id)


@app.get(
    "/product/{product_id}/shop-prices",
    response_model=list[ShopPriceEntry],
    tags=["products"],
)
def product_shop_prices(
    request: Request,
    product_id: str,
    shop_ids: Annotated[
        list[str],
        Query(min_length=1, description="repeat for multiple shop uuids"),
    ],
) -> list[ShopPriceEntry]:
    """GET /product/{id}/shop/{uuids} — per-shop prices (NORMAL + DISCOUNTED only)."""
    return _client(request).get_product_shop_prices(product_id, shop_ids)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
