# SuperFind AI (web)

The shopper web app: pick a store, search one product or a whole list, see stock, price and shelf,
build a shopping list and get the shortest walking route with a floor map. Vite + React + TypeScript
with plain CSS tokens. It talks **only** to the FastAPI app in `../api` (front end -> API -> provider ->
engine); it never reads store files.

## Run it locally (Windows PowerShell)

Two terminals, both from the repo root. Node 24+ and the repo's Python environment are assumed.

**Terminal 1: the API** (rule-based, no AI model; one worker because sessions live in memory):

```powershell
$env:PLANOGRAM_PROVIDER = 'none'
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

**Terminal 2: the web app:**

```powershell
cd web
npm ci            # first time only
npm run dev       # http://localhost:5173
```

In development the Vite server forwards `/api/*` to `http://127.0.0.1:8000` (see `vite.config.ts`),
so no CORS setting is needed. Open `http://localhost:5173` (Vite listens on `localhost`; on some
Windows machines `127.0.0.1:5173` does not answer).

## Settings

| Where | Variable | What it does |
|---|---|---|
| web (build time) | `VITE_API_BASE_URL` | API address for a deployed build, e.g. `https://api.example.com` (no trailing slash). **Required for `npm run build`**: the build stops if it is missing or not an http(s) address. Unset in `npm run dev`: `/api` (the dev proxy). See `.env.example`. |
| API | `PLANOGRAM_PROVIDER` | `none` runs without an AI model (use it for every local and test run). |
| API | `PLANOGRAM_CORS_ORIGINS` | Comma-separated web origins allowed to call the API, e.g. `https://superfind.example.com`. Exact origins only: no trailing slash, no wildcards. Unset = no cross-origin access. **Set it in production** when the web app and API are on different origins. |
| API | `PLANOGRAM_TRUST_PROXY` | `1` when the API sits behind a proxy that sets `X-Forwarded-For` (rate limits per real client). |
| API | `PLANOGRAM_TRUSTED_PROXY_HOPS` | Proxies in front of the API (default `1`); the client address is read that many entries from the right of `X-Forwarded-For`. |
| API | `PLANOGRAM_STORES_FILE` | Another store registry instead of `config/stores.json`. |

No keys or secrets belong in this folder; anything starting with `VITE_` ends up in the browser.

Production build: `$env:VITE_API_BASE_URL = 'https://api.example.com'; npm run build` writes `dist/`.
`npm run preview` serves it with the same security headers as Vercel (read from `vercel.json`).

**Deploying** (Render for the API, Vercel for this app, step by step): see [`../docs/DEPLOY.md`](../docs/DEPLOY.md).

**Slow or sleeping API:** every request gives up after 75 s (`REQUEST_TIMEOUT_MS`), a request still
pending after 4 s shows "Waking up the store server…" (`SLOW_REQUEST_MS`), and the store list is tried
once more before an error shows.

## Tests

```powershell
cd web
npm run typecheck     # tsc, strict
npm test              # vitest + Testing Library + jest-axe, against recorded API fixtures (no network)
npm run e2e           # Playwright smoke test in Chromium (starts or reuses the API and dev server)
```

The first `npm run e2e` needs the browser: `npx playwright install chromium`. It writes screenshots
to `screenshots/smoke/` (360 and 1280 px, light and dark). To run it against a production build
instead, set `SMOKE_BASE_URL` (and `SMOKE_SCREENSHOTS` for another folder); see "Production-like check"
in `docs/DEPLOY.md`.

### API contract fixtures

`src/api/fixtures/*.json` and `openapi.json` are recorded from the real API with the model off, so the
unit tests use real shapes. After changing the API or store data, regenerate them (repo root):

```powershell
$env:PLANOGRAM_PROVIDER='none'; python scripts/export_web_contract.py; npm --prefix web run gen:api
```

`tests/test_web_contract.py` (pytest) fails if the committed fixtures are out of date. Vitest's
persistent module cache is turned off in `vite.config.ts` because it kept the old fixture list after
new fixture files were added.

## Layout

| Folder | What is in it |
|---|---|
| `src/api` | Typed client (`client.ts`), generated types, recorded fixtures |
| `src/app`, `src/stores`, `src/theme` | Header, store selection (URL + storage), light/dark/system theme |
| `src/search`, `src/voice` | Search bar with suggestions, clarification questions, browser voice input |
| `src/categories`, `src/results` | Category chips and browsing, result and not-found cards |
| `src/list`, `src/route` | Shopping list per store, route steps and the SVG floor map |
| `src/components`, `src/styles` | Shared UI parts, design tokens (contrast-tested in both themes) |
| `e2e` | The Playwright smoke test |

Limits and timings (low stock, list size, quantities, debounce, toast time, request timeout) live in `src/config.ts`.
