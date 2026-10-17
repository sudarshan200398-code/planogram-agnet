# Deploying SuperFind (live link)

Two pieces, both deployed from the `main` branch:

| Piece | Where | Config in the repo |
|---|---|---|
| API (FastAPI, `api/`) | Render, free web service, **one worker** | `render.yaml`, `requirements-api.txt` |
| Web app (Vite + React, `web/`) | Vercel, static build | `web/vercel.json`, `web/.env.example` |

The live API runs with `PLANOGRAM_PROVIDER=none` (rule-based, no AI model), so **no secrets or API keys are
needed anywhere**.

Do the steps in this order. Each one needs the URL from the step before it.

---

## (a) Merge to main

1. On GitHub, open a pull request from `v3-web` into `main`.
2. Check the diff, then merge it.

Render and Vercel both deploy from `main`.

## (b) Render: deploy the API

1. Sign in at <https://dashboard.render.com>.
2. Click **New +** (top right), then **Blueprint**.
3. Connect GitHub if asked, then pick this repository.
4. Render reads `render.yaml` and shows one service, **superfind-api**, on the **Free** plan.
5. Render asks for a value for **PLANOGRAM_CORS_ORIGINS**, which `render.yaml` marks as "set manually".
   - You don't know the Vercel URL yet, so leave it empty for now.
   - If Render insists on a value, enter `https://example.invalid` and replace it in step (d).
6. Click **Apply** (or **Create**) and wait for the deploy to finish.
   - The first build installs `requirements-api.txt`. That took about 1.5 minutes on a Windows laptop; Render's time will differ.
   - The service shows **Live** when it is done.
7. Copy the service URL from the top of the service page, e.g. `https://superfind-api.onrender.com`.
8. Open `<that URL>/health` in a browser. You should see `{"status":"ok","stores":[...]}`.

What the Blueprint sets up:
- **Python:** `PYTHON_VERSION` 3.12.10, with `PYTHONPATH=src`.
- **Build:** `pip install -r requirements-api.txt`.
- **Start:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`.
- **Health check:** `/health`.
- **Environment:** `PLANOGRAM_PROVIDER=none`, `PLANOGRAM_TRUST_PROXY=1`, `PLANOGRAM_TRUSTED_PROXY_HOPS=1`, and `PLANOGRAM_CORS_ORIGINS`, which you set yourself.

**Rate limiting behind Render's proxy.** The API limits each shopper by address. With
`PLANOGRAM_TRUST_PROXY=1` it reads the address from `X-Forwarded-For`, counting `PLANOGRAM_TRUSTED_PROXY_HOPS`
entries from the right (1 = the entry the nearest proxy added); entries further left come from the
client and are ignored. A missing or unusable header falls back to the connection address.
If rate limiting looks wrong on the live site (everyone throttled together, or never throttled), this is the setting to check; Render's proxy layout is not something I could verify locally.

## (c) Vercel: deploy the web app

1. Sign in at <https://vercel.com>.
2. Click **Add New...**, then **Project**, and import this GitHub repository.
3. Next to **Root Directory**, click **Edit** and choose `web`.
4. Leave the framework preset at **Vite**. `web/vercel.json` already sets these, so don't change them:
   - install: `npm ci`
   - build: `npm run build`
   - output: `dist`
5. Open **Environment Variables** and add:
   - Name: `VITE_API_BASE_URL`
   - Value: the Render URL from step (b), e.g. `https://superfind-api.onrender.com`. Use `https` and **no trailing slash**.
6. Click **Deploy**.
   - If the build stops with `VITE_API_BASE_URL is not set`, the variable is missing or misspelled.
   - The build checks this on purpose, so the app can never call the wrong host.
7. Copy the production URL, e.g. `https://superfind.vercel.app`.
   - Use the main domain shown on the project page, not a per-deployment URL with a random part.

`VITE_API_BASE_URL` is baked in at build time. If you change it later, redeploy: open **Deployments**, then **⋯**, then **Redeploy**.

## (d) Render: allow the web app's origin, then redeploy

1. On Render, open **superfind-api**, then **Environment**.
2. Set **PLANOGRAM_CORS_ORIGINS** to the Vercel URL, e.g. `https://superfind.vercel.app`.
3. Click **Save Changes**. Choose **Save and deploy** if offered; otherwise click **Manual Deploy**, then **Deploy latest commit**.

The exact format matters. Each case below was checked against the real API code:

| Value | Result |
|---|---|
| `https://superfind.vercel.app` | allowed |
| `https://superfind.vercel.app,https://superfind-git-main-you.vercel.app` | both allowed (comma-separated; spaces around commas are fine) |
| `https://superfind.vercel.app/` (trailing slash) | **nothing allowed** |
| `https://*.vercel.app` (wildcard) | **nothing allowed**, because wildcards aren't supported |

- **Write exact origins:** scheme plus host, with no path and no trailing slash.
- **Vercel preview deployments** each get their own URL and are blocked unless you add them too. Only the production URL needs to work for the demo.

## (e) Open the live app: smoke checklist

Open the Vercel URL on your phone and on a laptop, then check:

- [ ] **Store list loads.** If the API was asleep you'll see "Waking up the store server, this can take up to a minute." Wait for it.
- [ ] **Store switch.** Switch to Riverside Market and back. The address bar shows `?store=...`.
- [ ] **Search.**
  - Search **milk**, pick one, and check that the card shows price, stock and shelf.
  - Check that there is no route under the search results; the route lives in the list.
- [ ] **List.** Tap **Add to list**, then add something from Level 2, e.g. *PlayTime Wax Crayons 12 pack*.
- [ ] **Route and map.** Open the **List** and tap **Find my route**. You should see numbered steps, metres, "1 floor change", and a map for each floor.
- [ ] **Product images** show (they load from the Render URL).
- [ ] **Voice.**
  - Tap the microphone and allow the browser's permission prompt. Say "bread" and check the words appear in the box.
  - This needs Chrome or Edge (Web Speech API). The button is hidden where the browser doesn't support it.
- [ ] **Theme.** The theme button cycles System, then Light, then Dark.
- [ ] **No errors.** Nothing says "Can't reach the store". If it does, see Troubleshooting.

## (f) Wake the API before a demo

The free Render service goes to sleep when nobody uses it, and the first request after that is slow.

1. **About 2 minutes before the demo,** open `https://<your-render-url>/health`.
   - Wait until it shows `{"status":"ok",...}`.
   - The first time, this can take up to about a minute.
2. **Open the Vercel URL** and do one search in each store.
   - The API loads a store's data on its first search for that store.
   - Locally that took about 0.6 s, so it is quick once the service is awake.
3. **Keep using it,** or reopen `/health`, so it doesn't go back to sleep. Render's idle timeout is listed under the free-tier limits below.

The app copes with a sleeping server:
- After 4 s it shows the waking-up message.
- Each request waits up to 75 s.
- The store list retries once.
- If the server still doesn't answer, the shopper sees a friendly message with **Try again**, never a raw error.

## (g) Roll back

**Web app (Vercel):**
1. Open the project, then **Deployments**.
2. Find the last good production deployment and click **⋯**, then **Promote to Production**. Some plans call this **Instant Rollback**.
3. This takes effect immediately, with no rebuild.

**API (Render):**
1. Open **superfind-api**, then **Events** (or **Deploys**).
2. Find the last good deploy and click **Rollback**.
3. Render redeploys that build. Sessions in memory are cleared; shoppers who were mid-question are asked again.

**Afterwards:** both services auto-deploy from `main`, so the next merge to `main` deploys again. Fix or revert the bad change on `main` too.

## (h) What NOT to do

- **No keys or secrets in env files, `vercel.json`, `render.yaml` or the dashboards.**
  - Anything named `VITE_*` ends up in the public JavaScript bundle.
  - `.env` and `.env.*` files are ignored by git, except `web/.env.example`, which holds only a placeholder.
- **Don't add workers or instances to the API.**
  - Keep `--workers 1` and one instance.
  - Clarification sessions and the rate limiter live in the process's memory.
  - A second worker would lose sessions ("That question has expired") and split the rate limit.
- **Don't change `PLANOGRAM_PROVIDER`** from `none` on the live API. Any other value would need an AI model key.
- **Don't add a trailing slash or `*`** to `PLANOGRAM_CORS_ORIGINS` (see the table in step d).
- **Don't set `VITE_API_BASE_URL` with a path or trailing slash**, e.g. `https://x.onrender.com/api`. The API serves from its root.
- **Don't edit `requirements.txt`.** It is for the Streamlit app; the API uses `requirements-api.txt`.

## Free-tier limits

These are as I know them. Prices and limits change, so items marked **(check the current pricing)** must be confirmed on the providers' pages before you rely on them.

**Render free web service:**
- **Sleep:** spins down after about 15 minutes with no traffic. The next request wakes it, which can take up to about a minute. **(check the current pricing)**
- **Hours:** about 750 free instance hours per month per workspace, enough for one always-on service. **(check the current pricing)**
- **Instance:** small, about 512 MB RAM and a fraction of a CPU. **(check the current pricing)**
  - Locally, with both stores loaded, the API used about 109 MB working set (318 MB private) on Windows.
  - Linux memory use will differ.
- **No persistent disk,** and restarts and deploys clear memory. That's fine here, because store data is in the repo and only sessions are in memory.
- **Bandwidth and build minutes** have monthly allowances. **(check the current pricing)**
- **Health checks and Blueprint support** on the free plan. **(check the current pricing)**

**Vercel Hobby:**
- **Personal, non-commercial use only.** **(check the current pricing)**
- **Bandwidth, build minutes and deployments per day** have monthly or daily limits; this app is about 85 kB of JavaScript gzipped. **(check the current pricing)**
- **Instant Rollback** may only go back to the previous production deployment on Hobby. **(check the current pricing)**

## Troubleshooting

| What you see | Likely cause | Fix |
|---|---|---|
| Vercel build fails: `VITE_API_BASE_URL is not set` | Variable missing, or not set for the Production environment | Add it (step c), then redeploy |
| App shows "Can't reach the store" | CORS: `PLANOGRAM_CORS_ORIGINS` doesn't match the exact Vercel URL; or the API is down | Fix the value (step d), redeploy the API, then open `/health` |
| "Waking up the store server…" for a long time | Render is starting the service | Wait up to a minute; check the Render logs if it keeps failing |
| Images missing, everything else works | `VITE_API_BASE_URL` points at the wrong host | Fix it on Vercel and redeploy |
| Everyone gets "Lots of searches right now" together, or nobody ever does | `PLANOGRAM_TRUSTED_PROXY_HOPS` doesn't match Render's proxy layout | Try `2` (or back to `1`) on Render, redeploy, and test from two networks (e.g. Wi-Fi and phone data) |
| "That question has expired" often | More than one worker or instance, or frequent restarts | Keep one worker and one instance |

The browser can't tell a CORS block apart from an unreachable server, so both show "Can't reach the store". The browser console names CORS when that is the cause.

## Production-like check on your own machine

This is the same build and the same start command, on local ports. Run it from the repo root in PowerShell.

**Terminal 1: the API,** with Render's start command on port 8001:

```powershell
$env:PYTHONPATH = 'src'; $env:PLANOGRAM_PROVIDER = 'none'; $env:PLANOGRAM_TRUST_PROXY = '1'
$env:PLANOGRAM_CORS_ORIGINS = 'http://localhost:4173'; $env:PORT = '8001'
python -m uvicorn api.main:app --host 0.0.0.0 --port $env:PORT --workers 1 --no-access-log
```

**Terminal 2: the web app.** Build it and serve it with the same headers as Vercel; `vite preview` reads them from `vercel.json`:

```powershell
cd web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8001'; npm run build
npx vite preview --port 4173 --strictPort
```

**Terminal 3: the smoke test** against the preview:

```powershell
cd web
$env:SMOKE_BASE_URL = 'http://localhost:4173'; $env:SMOKE_SCREENSHOTS = "$PWD\test-results\prod-smoke"; npm run e2e
```
