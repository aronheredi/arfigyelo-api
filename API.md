# arfigyelo.gvh.hu — API map

Public, anonymous price-comparison API behind the Árfigyelő SPA.

- **Base URL:** `https://arfigyelo.gvh.hu/api`
- **Auth:** none (no cookies, tokens, or API keys)
- **Format:** JSON, UTF-8; prices are HUF as floats
- **Methods:** `GET` only (`HEAD` also allowed)
- **Sources:** HAR `arfigyelo.gvh.hu_Archive [26-11-19 14-13-45].har`, live probing on 2026-11-19, SPA bundle `/assets/index-5baaf084.js` (410 KB)

All seven endpoints below were found by decompiling the SPA bundle (`axios.create({baseURL:"/api"})`) and were verified live. There are no other `/api/*` routes: every non-matching path falls through to the SPA HTML or a Spring 404.

---

## Endpoint summary

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 1 | GET | `/api/categories` | Full category tree |
| 2 | GET | `/api/chain-stores` | Retail chains (9) |
| 3 | GET | `/api/shops` | Physical shops (1,831) |
| 4 | GET | `/api/products-by-category/{categoryId}` | Product list for a category (incl. descendants) |
| 5 | GET | `/api/search` | Text search |
| 6 | GET | `/api/product/{productId}` | Product detail, chain-level prices, shop availability |
| 7 | GET | `/api/product/{productId}/shop/{shopUuids}` | Per-shop prices for one product |

All are cacheable: `cache-control: public, max-age=299` (5 min), served through Azure CDN (`x-cache`, `x-azure-ref`).
Nothing sets `Access-Control-Allow-Origin`; cross-origin browser calls are blocked (an `OPTIONS` preflight with `Origin` is rejected with 403). Use it server-side.

---

## 1. `GET /api/categories`

Returns the whole category tree in one response (~24.6 KB).

```json
{"categories":[{
  "id": 1001,
  "name": "Tejtermék, sajt, tojás",
  "path": "tejtermek_sajt_tojas",
  "icon": null,
  "categoryNodes": [ /* recursive */ ]
}]}
```

2026-11-19 snapshot: **9 root nodes, 212 nodes total, max depth 2** (root → group → leaf). `icon` was `null` on every node.

Root nodes:

| id | path | name | children |
|---:|---|---|---:|
| 1001 | `tejtermek_sajt_tojas` | Tejtermék, sajt, tojás | 8 |
| 1015 | `hus_hal_felvagott` | Hús, hal, felvágott | 8 |
| 1028 | `zoldseg_gyumolcs` | Zöldség, gyümölcs | 3 |
| 1046 | `pekaru` | Pékáru | 2 |
| 1050 | `tartos_elelmiszer_ital` | Tartós élelmiszerek, italok | 8 |
| 1068 | `specialis_etrend` | Speciális étrend | 4 |
| 1123 | `baba` | Baba | 3 |
| 1126 | `haztartas` | Háztartás | 3 |
| 1138 | `szepseg_higienia` | Szépség és higiénia | 3 |

`path` is the slug used by the web routes (`/k/{path}`). `id` is what the product endpoints take. They are not the same hierarchy: **root IDs return 0 products**, while depth-1 IDs aggregate all descendants (e.g. `2001` "Tej" = 85 products = sum of its four leaf children; `2010` "Sajt" = 648).

---

## 2. `GET /api/chain-stores`

```json
{"chainStores":[{"uuid":"3ccc9f35-604c-4ccf-8376-64822ce4bc70","name":"Spar","imageUrl":"spar"}]}
```

`imageUrl` is a slug, not a URL (assets live at `/assets/{slug}-logo-small-*.svg`).

| Chain | UUID | Shops |
|---|---|---:|
| Spar | `3ccc9f35-604c-4ccf-8376-64822ce4bc70` | 375 |
| Rossmann | `41e81400-3e3d-47b4-84f7-7dce01cc9b43` | 282 |
| dm | `555f7e7c-8229-4f4f-ba60-450925a5b308` | 259 |
| Penny | `53b66cb6-a24f-420d-9861-d38757467d07` | 248 |
| Lidl | `f95031d8-84a5-4edf-b4fa-18b2cbae2ea1` | 222 |
| Tesco | `792ea257-0af9-4588-ada7-81bd96c96400` | 197 |
| Aldi | `55b678e0-4e02-49d7-86da-ba6fba862a7e` | 188 |
| Müller | `e313905a-b57e-4016-b4d2-1d1f45e53157` | 34 |
| Auchan | `e9cc63fd-52e0-4c1e-ba8d-d135d7285c63` | 26 |

## 3. `GET /api/shops`

Returns all 1,831 shops (~416 KB).

```json
{"shops":[{
  "uuid": "spar-110",
  "postalCode": "1011",
  "city": "Budapest I.",
  "address": "Batthyány tér 5-6",
  "chainStoreUuid": "3ccc9f35-604c-4ccf-8376-64822ce4bc70",
  "location": {"latitude": 47.506062, "longitude": 19.038035},
  "openingTime": ""
}]}
```

`openingTime` is a human-readable string, usually empty; when present it uses `#` as a line separator, e.g. `Nyitvatartás: 06:30-21:30#Nyitvatartás - Vasárnap: 07:00-19:00`. `location` was present on all shops.

Shop UUIDs (`spar-110`, `auchan-002`, …) are the only valid values for the `shopIds` filter and the per-shop endpoint. Chain UUIDs are **not** accepted there.

---

## 4. `GET /api/products-by-category/{categoryId}`

Returns products for a category and all of its descendants.

### Query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `categoryId` | path, integer | — | from `/api/categories` |
| `limit` | integer | **12** | server caps at **48** |
| `offset` | integer | 0 | |
| `order` | string | `unitAmount_asc` | see below |
| `shopIds` | string | — | comma-separated shop UUIDs; filters products **and** returned prices |

`order` values:

| Value | Sort |
|---|---|
| `unitAmount_asc` *(default)* | ascending `minUnitPrice` |
| `unitAmount_desc` | descending `minUnitPrice` |
| `amount_asc` | ascending cheapest pack price (`productMinAmount`) |
| `amount_desc` | descending cheapest pack price |

`relevance` is **not** accepted here (500).

### Example

```bash
curl 'https://arfigyelo.gvh.hu/api/products-by-category/5?limit=24&offset=0&order=unitAmount_asc'
```

```json
{
  "products": [{
    "id": "penny-2076",
    "name": "Sissy tejföl 20% 450g",
    "imageUrl": "https://cdnarfigyeloprodweu.azureedge.net/images/product-image-penny-2076.jpg",
    "unit": "kg",
    "unitTitle": "db",
    "bulk": false,
    "returnType": null,
    "returnFee": 0,
    "packaging": "0.45",
    "categoryPath": "tejtermek_sajt_tojas/tejfol/tejfol_20",
    "minUnitPrice": 886.67,
    "pricesOfChainStores": [{
      "id": "53b66cb6-a24f-420d-9861-d38757467d07",
      "name": "Penny",
      "priceSameEverywhere": true,
      "productMinAmount": 399.0,
      "prices": [
        {"type": "NORMAL",     "amount": 449.0, "unitAmount": 997.78, "sameAmountEverywhere": true},
        {"type": "DISCOUNTED", "amount": 399.0, "unitAmount": 886.67, "sameAmountEverywhere": true}
      ]
    }]
  }],
  "count": 40
}
```

### Pagination semantics (important)

- `count` is the total matching products **for a non-empty page**.
- **When the page is empty, `count` is `0`, not the total.** Stop paginating on `products: []`, not on `offset >= count`.
- `limit > 48` is silently clipped to 48 (verified: 48 → 48 items, 49/100/1000 → 48 items).
- The 48-item cap drops nothing: paging category `2001` (`count: 85`) with `limit=24` at `offset=0/24/48/72` returns 24+24+24+13 = 85, so it is a page-size cap, not silently discarded rows.
- Non-numeric/negative `limit` or `offset` → `500 INTERNAL_SERVER_ERROR`.
- Unknown/non-existent category → `200 {"products":[],"count":0}`.
- Non-numeric category path → 500 (or Spring 404 for a slash-containing path).

With `shopIds`, the response is filtered to prices available in those shops; `count` and `minUnitPrice` reflect the filter. Unknown shop IDs simply produce an empty result.

---

## 5. `GET /api/search`

### Query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — | required; trimmed; **min 3 characters**; accent-insensitive |
| `limit` | integer | **48** | capped at 48 |
| `offset` | integer | 0 | |
| `order` | string | `relevance` | `relevance`, `unitAmount_asc`, `unitAmount_desc`, `amount_asc`, `amount_desc` |
| `shopIds` | string | — | comma-separated shop UUIDs |

Search matches accents both ways: `q=tejfol` and `q=tejföl` both return the same 76 results. Digits and spaces are valid (`q=123`, `q=a b`). A single trailing space is ignored.

### Example

```bash
curl 'https://arfigyelo.gvh.hu/api/search?q=tejfol&limit=48&offset=0&order=relevance'
```

Response shape is identical to endpoint 4 (`{"products":[...],"count":...}`).

### Validation

| Case | Result |
|---|---|
| `q` missing | `500 INTERNAL_SERVER_ERROR` (backend bug) |
| `q` empty / blank / < 3 chars | `400 {"code":"SEARCH-INPUT-ERROR","message":"Invalid search parameter"}` |
| `order=bogus` | `500 INTERNAL_SERVER_ERROR` |
| SQL-injection-like input | 403 HTML (WAF "Hamarosan indul" page), not JSON |

Same pagination caveat as endpoint 4: `count` becomes `0` on an empty page.

---

## 6. `GET /api/product/{productId}`

`productId` is the `id` from list/search results (`5999550782526`, `lidl-0001534`, `penny-2076`, …).

```json
{
  "id": "5999550782526",
  "name": "S-Budget friss csirkemellfilé",
  "imageUrl": "https://cdnarfigyeloprodweu.azureedge.net/images/product-image-5999550782526.jpg",
  "unit": "kg",
  "unitTitle": "kg",
  "bulk": true,
  "returnType": null,
  "returnFee": 0,
  "packaging": "1",
  "categoryId": "18",
  "categoryPath": "hus_hal_felvagott/szarnyas/csirkemell",
  "chainStores": [{
    "uuid": "3ccc9f35-604c-4ccf-8376-64822ce4bc70",
    "name": "Spar",
    "imageUrl": "spar",
    "prices": [
      {"type": "NORMAL", "amount": 1924.0, "unitAmount": 1924.0}
    ],
    "pricesMax": [],
    "priceSameEverywhere": true,
    "availableInShops": ["spar-104", "spar-105", "spar-106", "..."]
  }]
}
```

Differences vs. the list model:

- `categoryId` is added (string).
- `pricesOfChainStores` → `chainStores`, each entry keyed by `uuid` (not `id`).
- Chain entries carry `pricesMax` and `availableInShops`.
- No `minUnitPrice` / `productMinAmount` at the top level.

`pricesMax` is populated only when the chain sells the product at different prices in different shops; it then holds the maximum variant(s). Example: Spar `prices` NORMAL 92.0, `pricesMax` NORMAL 99.0, `priceSameEverywhere: false`.

Unknown product:

```http
HTTP 404
{"code":"NOT_FOUND_PRODUCT","message":"No product found based on the product UUID! [uuid: nope]"}
```

---

## 7. `GET /api/product/{productId}/shop/{shopUuids}`

`shopUuids` = comma-separated shop UUIDs (from endpoint 3 or `availableInShops`).

```bash
curl 'https://arfigyelo.gvh.hu/api/product/5999545594554/shop/spar-536,spar-622,spar-631'
```

```json
{"shops":[
  {"uuid":"5999545594554","shopUuid":"spar-536","prices":[{"type":"NORMAL","amount":99.0,"unitAmount":66.0}]},
  {"uuid":"5999545594554","shopUuid":"spar-622","prices":[{"type":"NORMAL","amount":92.0,"unitAmount":61.33}]}
]}
```

- The top-level `uuid` is the **product ID** (API quirk; naming suggests product, not shop).
- Only shops that actually have a price are returned; unknown/unavailable shop IDs are skipped.
- If no requested shop has a price (or the product is unknown):
  ```http
  HTTP 404
  {"code":"PRODUCT-SHOP-PRICES-NOT-FOUND","message":"Not found prices by product and shops uuid! [productUuid : '...', shopUuids : [...]]"}
  ```
- Prices include `NORMAL` and `DISCOUNTED`, but **not `LOYALTY`** — loyalty prices only appear in the product-detail endpoint.
- Result order is not the requested order.

---

## Data models

### Product list item (endpoints 4, 5)

| Field | Type | Notes |
|---|---|---|
| `id` | string | numeric EAN-style or retailer-prefixed (`lidl-0001534`, `penny-2076`) |
| `name` | string | Hungarian product name |
| `imageUrl` | string | absolute CDN URL on `cdnarfigyeloprodweu.azureedge.net` |
| `unit` | `kg` \| `l` \| `db` \| `g` | base unit for unit price |
| `unitTitle` | string | sale-unit label, observed `db` and `csomag` |
| `bulk` | boolean | bulk/loose goods flag |
| `returnType` | `null` \| `"one-way-return-fee"` | deposit type |
| `returnFee` | number | HUF; `0` or `50` observed |
| `packaging` | string | numeric string, size in `unit` (e.g. `"0.45"`, `"1.5"`) |
| `categoryPath` | string | slug path |
| `minUnitPrice` | number | HUF per `unit`, cheapest non-loyalty price |
| `pricesOfChainStores` | array | see below |

`unitAmount = amount / packaging`. For unit `db` with `packaging: "5"` (multipack), `unitAmount` is the per-piece price. `minUnitPrice` is the minimum `unitAmount` across all `NORMAL` and `DISCOUNTED` prices — `LOYALTY` prices are excluded. `productMinAmount` is similarly the minimum `amount`, excluding `LOYALTY`.

### `pricesOfChainStores[]`

| Field | Type | Notes |
|---|---|---|
| `id` | string | chain-store UUID |
| `name` | string | chain name |
| `priceSameEverywhere` | boolean | same price in all shops of that chain |
| `productMinAmount` | number | cheapest shelf price at that chain (excl. loyalty) |
| `prices` | array | `{type, amount, unitAmount, sameAmountEverywhere}` |

### Price object

| Field | Type | Notes |
|---|---|---|
| `type` | `NORMAL` \| `DISCOUNTED` \| `LOYALTY` | |
| `amount` | number | shelf price in HUF |
| `unitAmount` | number | HUF per `unit` |
| `sameAmountEverywhere` | boolean | list responses only |

### Product detail (endpoint 6)

| Field | Type |
|---|---|
| `id`, `name`, `imageUrl` | string |
| `unit`, `unitTitle` | string |
| `bulk` | boolean |
| `returnType` | string \| null |
| `returnFee` | number |
| `packaging` | string |
| `categoryId` | string |
| `categoryPath` | string |
| `chainStores[]` | `{uuid, name, imageUrl, prices[], pricesMax[], priceSameEverywhere, availableInShops[]}` |

Detail `prices` entries omit `sameAmountEverywhere`; the chain object carries `priceSameEverywhere` instead.

### Category

`{id:number, name:string, path:string, icon:null, categoryNodes:Category[]}`

### Chain store

`{uuid:string, name:string, imageUrl:string /* slug */}`

### Shop

`{uuid, postalCode, city, address, chainStoreUuid, location:{latitude,longitude}, openingTime}`

---

## SPA route → API mapping

| Web route | API calls |
|---|---|
| `/` | `/api/categories`, `/api/chain-stores`, category endpoint for "most searched" |
| `/k/:categoryPath+` | `/api/categories` (resolve slug → id), then `/api/products-by-category/{id}` |
| `/k/:categoryPath+/t/:productId` | `/api/product/{id}`; optionally `/api/product/{id}/shop/{shopIds}` |
| `/kereses/:searchText` | `/api/search?q=...&limit=...&offset=...&order=...` |
| `/uzletek` | `/api/shops`, `/api/chain-stores` |
| `/bevasarlolista` | client-side only (localStorage) |

Order and paging are passed as URL query params (`?order=unitAmount_asc`) and forwarded to the API.

---

## Errors

Custom JSON envelope:

```json
{"code":"...","message":"..."}
```

| Code | HTTP | Cause |
|---|---:|---|
| `NOT_FOUND_PRODUCT` | 404 | unknown `productId` in endpoint 6 |
| `PRODUCT-SHOP-PRICES-NOT-FOUND` | 404 | no requested shop has the product (endpoint 7) |
| `SEARCH-INPUT-ERROR` | 400 | missing/short/blank `q` |
| `BAD_REQUEST` | 400 | non-GET method: `{"code":"BAD_REQUEST","message":"Request method 'POST' is not supported"}` |
| `INTERNAL_SERVER_ERROR` | 500 | invalid `order`, bad/negative `limit`/`offset`, missing `q` |

Unmatched paths get Spring's default shape instead:

```json
{"timestamp":"2026-11-19T13:20:52.189+00:00","status":404,"error":"Not Found","path":"/api/products"}
```

`OPTIONS` on a valid endpoint returns `200` with `Allow: GET,HEAD,OPTIONS`, but a CORS preflight (`Origin` + `Access-Control-Request-Method`) is rejected with 403.

---

## Adjacent non-API data

Found in the same SPA bundle (not JSON API):

| URL | Content |
|---|---|
| `https://cdnarfigyeloprodweu.azureedge.net/excel/arfigyelo_napi_termekadatok.xlsx` | Daily full dump, ~2.1 MB; sheet titled `Napi feltöltések - 2026-11-17`; 25,626 rows incl. header |
| `https://cdnarfigyeloprodweu.azureedge.net/excel/arfigyelo_20250313_napi_termekadatok.xlsx` | Frozen 2025-03-13 snapshot, ~220 KB |
| `https://cdnarfigyeloprodweu.azureedge.net/images/product-image-{id}.jpg` | Product images |
| `https://arfigyelo.gvh.hu/docs/archive/{filename}.pdf` | Archived legal documents |

XLSX columns: `Termék azonosító`, `Termék név`, `Kategória azonosító`, `Kategória név`, `Üzletlánc név`, `Egység`, `Kiszerelés`, `Minimum ár`, `Maximum ár`, `Minimum egységár`, `Maximum egységár`, `Hány üzletláncban elérhető`, `Hány boltban elérhető`, `Üzletlánc összes boltja` — one row per product × chain, with Hungarian decimal commas.

---

## Known quirks

1. **`count: 0` on empty pages.** Don't use `count` to detect the end of pagination; test `products.length`.
2. **Limit cap 48.** Anything larger is clipped; the app itself requests 12/24.
3. **Different defaults:** category = 12, search = 48.
4. **Root categories are empty.** Only depth-1 and leaf IDs return products; depth-1 aggregates descendants.
5. **`shopIds` takes shop UUIDs, not chain UUIDs.** Chain UUIDs silently yield zero results.
6. **Per-shop `uuid` is the product ID.**
7. **Per-shop prices omit `LOYALTY`.**
8. **`relevance` works only on `/api/search`.** Passing it to the category endpoint returns 500.
9. **No CORS.** Server-side access only, unless you proxy.
10. **Missing `q` returns 500** rather than 400.
