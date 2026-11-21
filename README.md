# arfigyelo-api

Python client for the [Árfigyelő](https://arfigyelo.gvh.hu) price-comparison API —
the Hungarian Competition Authority's official retail price monitor.

Fully-typed [pydantic](https://docs.pydantic.dev/) models, sync and async
clients, a mapping layer (category paths, chains, shops), and safe pagination
iterators. All money values are exact `Decimal` forints (HUF).

Requires Python 3.14+.

## Install

```bash
pip install arfigyelo-api
```

## Usage

### Sync

```python
from decimal import Decimal

from arfigyelo_api import ArfigyeloClient

with ArfigyeloClient() as client:
    # mapping layer: resolve by category path, never by numeric id
    products = list(client.iter_products_by_path("tejtermek_sajt_tojas/sajt/ementali"))
    cheapest = products[0]  # default order: unitAmount_asc
    print(cheapest.name, cheapest.min_unit_price)  # exact Decimal HUF

    detail = client.get_product(cheapest.id)
    spar = client.get_chain(name="Spar")
    shops = client.find_shops(city="Budapest", chain_uuid=spar.uuid)

    # per-shop prices (shop uuids, not chain uuids)
    prices = client.get_product_shop_prices(detail.id, [s.uuid for s in shops[:3]])
```

### Async

```python
from arfigyelo_api import AsyncArfigyeloClient

async with AsyncArfigyeloClient() as client:
    page = await client.search("tejföl", limit=48)
    async for product in client.iter_search("sajt"):
        ...  # paginates safely until exhausted
```

### Caching

Structural indexes (categories, chains, shops) are cached in memory with a
12-hour TTL (prices change daily). Price responses are never cached unless you
opt in:

```python
# poll-friendly: identical price calls hit the network at most once per ttl
client = ArfigyeloClient(cache_prices=True, ttl=12 * 3600)
```

Pass `ttl=0.0` to refetch on every call, `ttl=None` to cache for the lifetime
of the client instance.

### Errors

All exceptions derive from `ArfigyeloError`:

- `ArfigyeloApiError` — the API's `{"code": ..., "message": ...}` envelope
  (`.code`, `.message`, `.status_code`)
- `ArfigyeloValidationError` — invalid call arguments, raised *before* any
  request (the API would answer these with a misleading 500)
- `ArfigyeloConnectionError` — transport failures
- `ArfigyeloUnexpectedResponseError` — non-JSON bodies (e.g. the WAF page) or
  responses that fail schema validation

## API surface

| Client method | Endpoint |
|---|---|
| `get_categories()` / `get_chains()` / `get_shops()` | structural lists |
| `get_products_by_category(id, *, limit, offset, order, shop_ids)` | category listing |
| `get_products_by_path(path, ...)` | category listing via path |
| `search(q, *, limit, offset, order, shop_ids)` | text search |
| `get_product(product_id)` | product detail |
| `get_product_shop_prices(product_id, shop_uuids)` | per-shop prices |
| `iter_products_by_category` / `iter_products_by_path` / `iter_search` | safe pagination (stop on empty page, not on `count`) |
| `get_category_by_path`, `get_chain`, `get_shop`, `find_shops`, `category_index`, `chain_index`, `shop_index` | mapping layer |

The same methods exist on `AsyncArfigyeloClient` as coroutines/async
generators. See [API.md](https://github.com/aronheredi/arfigyelo-api/blob/main/API.md)
for the full endpoint map, and
[docs/adr/](https://github.com/aronheredi/arfigyelo-api/tree/main/docs/adr)
for the design decisions.

## Scope

The daily full-dump spreadsheet at
`https://cdnarfigyeloprodweu.azureedge.net/excel/arfigyelo_napi_termekadatok.xlsx`
is **not** part of this package — it is a CDN file, not an API endpoint; fetch
and parse it yourself if you need bulk data.

## Development

```bash
uv sync                 # install runtime + dev dependencies
uv run pytest           # test suite (uses recorded fixtures, no network)
uv run ruff check .     # lint
uv run mypy             # strict type check
uv build                # sdist + wheel in dist/
```

## License

MIT — see [LICENSE](https://github.com/aronheredi/arfigyelo-api/blob/master/LICENSE).
