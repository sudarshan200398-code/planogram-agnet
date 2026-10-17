# Store Product Finder API

FastAPI app over the existing engine. Every store endpoint is under `/stores/{store_id}`; stores come
from `config/stores.json` (`central` = Central Store, `riverside` = Riverside Market).
Interactive docs: `http://127.0.0.1:8000/docs` once it is running.

## Run (Windows PowerShell, from the repo root)

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[api,dev]"                       # fastapi, uvicorn, httpx (pinned)

$env:PLANOGRAM_PROVIDER = 'none'                   # AI model off; 'gemini' + GEMINI_API_KEY turns it on
$env:PLANOGRAM_CORS_ORIGINS = 'http://localhost:5173'   # comma-separated; unset = no cross-origin access
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

- `--workers 1`: clarification sessions live in memory in the worker that answered `/search`. With
  more workers a `/clarify` can reach a worker that never saw the question and gets
  `409 SESSION_NOT_FOUND`. Scale with more instances behind sticky sessions, or move sessions to a
  shared store (for example Redis) first.
- `--no-access-log`: uvicorn's access log prints full URLs including `?q=` search text. The app logs
  its own line per request instead: request id, method, route template, status, duration.

## Test

```powershell
$env:PLANOGRAM_PROVIDER = 'none'
python -m pytest -q                                # everything, including tests\test_api*.py
python -m pytest -q tests\test_api.py tests\test_api_isolation.py
```

## Environment variables

| Variable | Meaning |
|---|---|
| `PLANOGRAM_PROVIDER` | `none` (default for tests), `gemini`, or `fake` |
| `GEMINI_API_KEY` | Only when the provider is `gemini`; never logged |
| `PLANOGRAM_CORS_ORIGINS` | Allowed browser origins, comma-separated |
| `PLANOGRAM_TRUST_PROXY` | `1` = rate-limit by the `X-Forwarded-For` address the trusted proxy added, counted from the right (only behind your own proxy); a missing or non-IP entry falls back to the connection address |
| `PLANOGRAM_TRUSTED_PROXY_HOPS` | how many proxies in front of the API append to `X-Forwarded-For` (default `1`); only used with `PLANOGRAM_TRUST_PROXY=1` |
| `PLANOGRAM_STORES_FILE` | Another store registry instead of `config/stores.json` |

Limits live in `config/settings.json`: `max_query_chars` (500), `max_items` (20), basket quantity
1 to 99, `api_rate_limit_per_minute` (120 per client per worker), `api_page_size_max` (100).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Service up; which stores are loaded |
| GET | `/stores` | id, name, floors, product count, whether prices exist |
| GET | `/stores/{id}/categories` | Category names with product counts |
| GET | `/stores/{id}/products?category=&page=&page_size=` | Browse, sorted by name then sku |
| GET | `/stores/{id}/suggest?q=` | As-you-type product suggestions |
| POST | `/stores/{id}/search` | `{text, start?, step_free?}`: the full request pipeline |
| POST | `/stores/{id}/clarify` | `{session_id, item_index, sku}`: answer the pending question |
| GET | `/stores/{id}/products/{sku}` | One product with stock, places and price |
| POST | `/stores/{id}/basket/route` | `{items: [{sku, qty}], start?, step_free?}` |
| GET | `/stores/{id}/map` | Floors, bounds, nodes, edges, connectors, zones |
| GET | `/stores/{id}/products/{sku}/image` | PNG from the store's `images/` folder, or an SVG placeholder |

Errors: `{"error": {"code", "message", "request_id"}}` with codes such as `STORE_NOT_FOUND`,
`PRODUCT_NOT_FOUND`, `CATEGORY_NOT_FOUND`, `SESSION_NOT_FOUND`, `INVALID_CHOICE`, `VALIDATION_ERROR`,
`TEXT_TOO_LONG`, `TOO_MANY_ITEMS`, `QUANTITY_OUT_OF_RANGE`, `DUPLICATE_SKU`, `RATE_LIMITED`.
`price` is in rupees and `null` when the store has no `prices.csv` entry. `image_url` paths are
relative to the API's base URL.
