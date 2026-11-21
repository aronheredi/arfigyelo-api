"""arfigyelo-api: Python client for the Árfigyelő price-comparison API."""

from ._version import __version__
from .cache import TTLCache
from .client import DEFAULT_BASE_URL, ArfigyeloClient, AsyncArfigyeloClient
from .errors import (
    ArfigyeloApiError,
    ArfigyeloConnectionError,
    ArfigyeloError,
    ArfigyeloUnexpectedResponseError,
    ArfigyeloValidationError,
)
from .mapping import CategoryIndex, ChainIndex, ShopIndex
from .models import (
    Category,
    CategoryOrder,
    Chain,
    ChainPrices,
    DetailChain,
    DetailPrice,
    ListPrice,
    ProductDetail,
    ProductPage,
    ProductSummary,
    SearchOrder,
    Shop,
    ShopLocation,
    ShopPriceEntry,
    ShopPrices,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "AsyncArfigyeloClient",
    "ArfigyeloApiError",
    "ArfigyeloClient",
    "ArfigyeloConnectionError",
    "ArfigyeloError",
    "ArfigyeloUnexpectedResponseError",
    "ArfigyeloValidationError",
    "Category",
    "CategoryIndex",
    "CategoryOrder",
    "Chain",
    "ChainIndex",
    "ChainPrices",
    "DetailChain",
    "DetailPrice",
    "ListPrice",
    "ProductDetail",
    "ProductPage",
    "ProductSummary",
    "SearchOrder",
    "Shop",
    "ShopIndex",
    "ShopLocation",
    "ShopPriceEntry",
    "ShopPrices",
    "TTLCache",
    "__version__",
]
