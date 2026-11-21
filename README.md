# Lyftr Chat

Lyftr Chat is a multi-turn LLM chatbot with deterministic API-key failover and exact-match response caching. Each assistant reply shows its resolution source, model, elapsed time, and token usage. The stack uses React, TypeScript, Vite, FastAPI, LiteLLM, and SQLite.

## Live URLs

- **Public frontend:** [Lyftr Chat on Cloudflare Pages](https://lyftr-assignment.pages.dev/)
- **Public API:** `https://lyftr-backend-production.up.railway.app` · [Health endpoint](https://lyftr-backend-production.up.railway.app/health)
- **Source:** [Public GitHub repository](https://github.com/Aditya-112/lyftr-assignment)

The API runs on Railway Free with one 0.5 GB volume mounted at `/data`. Railway SQLite history survived a controlled service restart. Railway Free sleeps when idle, so the first request may take longer. If the workspace consumes its $1 monthly allocation, services pause until the next cycle and the volume retains its files. The previous tunnel demo retains its separate local SQLite volume. [Railway Free plan](https://docs.railway.com/pricing/free-plan)

### Zero-cost hosting options

| Option | SQLite persistence | Availability and cost |
| --- | --- | --- |
| Railway Free backend with a Cloudflare Pages frontend | The production database is `sqlite:////data/app.db` and retained its history across a Railway restart. | This is the current deployment. The Free workspace shares its $1 monthly allocation across services. [Railway Free plan](https://docs.railway.com/pricing/free-plan) · [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/) |
| alwaysdata Free | A personal Free account includes 1 GB of persistent account storage and can run an ASGI server with Uvicorn. | The existing backend peaked at 239.7 MB in a local 256 MB, quarter-CPU fixture test. This leaves limited headroom. Account access, Gemini egress, and deployed runtime performance remain unverified. [alwaysdata offers](https://www.alwaysdata.com/en/offers/) · [Python hosting](https://help.alwaysdata.com/en/docs/web-hosting/languages/python/configuration/) |
| Render Free Docker backend with a Render Static Site | The backend filesystem is ephemeral. Sleep, restarts, and deploys clear its SQLite history. | Use a free workspace with no payment method so overages suspend service instead of incurring charges. A paid disk is outside the budget. [Render Free restrictions](https://render.com/docs/free) |
| Oracle Cloud Always Free | An eligible VM and boot volume can retain SQLite. | Requires an eligible, accessible tenancy. New-account verification requires a card. [Oracle Free Tier FAQ](https://www.oracle.com/cloud/free/faq/) |
| Cloudflare Quick Tunnels to local Docker | The named Docker volume retains SQLite independently of the tunnel. | The hostnames change when the tunnel processes restart. Suitable for a scheduled demo. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) |

### Deploy on Railway Free and Cloudflare Pages Free

The workspace owner switched to Free. Railway's API confirmed `FREE` before provisioning the `lyftr-backend` service in the existing project. The deployment used a clean archive of the tracked backend files and the existing Dockerfile, with `/health` as its startup check. The workspace reported a current bill of $0 during verification. [Railway workspace plans](https://railway.com/workspace/plans)

1. In an authorized **Railway Free** workspace, create one backend service from the public GitHub repository. Use `backend` as the service root, build with its Dockerfile, and set the health check to `/health`. Generate a public HTTPS domain for port `8000`. Keep one replica and confirm that the workspace is on the Free plan, which stops services when its included resource allowance runs out. [Railway Free plan](https://docs.railway.com/pricing/free-plan)
2. Attach the included 0.5 GB volume at `/data`. Set `DATABASE_URL=sqlite:////data/app.db` and `RAILWAY_RUN_UID=0` so the service can write to Railway's root-owned volume. Set `LLM_API_KEYS` as a backend-only secret. Set `LLM_MODEL=gemini/gemini-3.1-flash-lite`, `ENABLE_FAILURE_SIMULATION=true`, and `PORT=8000`. Set `ALLOWED_ORIGINS` to the exact Pages origin, `https://lyftr-assignment.pages.dev`. [Railway volume permissions](https://docs.railway.com/volumes#permissions)
3. Use the existing **Cloudflare Pages Free** Direct Upload project, `lyftr-assignment`. Build with Node.js 24 and the verified Railway HTTPS origin in `API`. [Cloudflare Pages Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)

   ```bash
   npm --prefix frontend ci --include=dev
   VITE_API_BASE_URL="$API" npm --prefix frontend run build
   wrangler pages deploy frontend/dist --project-name lyftr-assignment --branch main
   ```

4. Update Railway's allowed origin to the verified Pages hostname. Run the live verification script, send a chat turn from the deployed frontend, and check Railway's actual usage. Save a history snapshot, restart the backend, and compare the snapshot over HTTPS.

### Temporary public demo with local SQLite

With the local stack running and the official `cloudflared` CLI installed, start one command per terminal and keep both terminals open.

```bash
cloudflared tunnel --url http://localhost:8000
cloudflared tunnel --url http://localhost:3000
```

In a third terminal, set the two HTTPS URLs printed above and rebuild the frontend with the temporary backend URL. The local addresses remain allowed for browser testing.

```bash
export API_TUNNEL_URL='https://YOUR-API-HOST.trycloudflare.com'
export FRONTEND_TUNNEL_URL='https://YOUR-FRONTEND-HOST.trycloudflare.com'
ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000,$FRONTEND_TUNNEL_URL" \
  VITE_API_BASE_URL="$API_TUNNEL_URL" make up
python3 scripts/verify_live.py "$API_TUNNEL_URL"
```

Run `make up` without the tunnel overrides after the demo to restore the local frontend build. Keep the URLs labeled temporary anywhere you share them.

## Run locally: with Docker and without

Use two valid Gemini API keys, ideally from different Google AI Studio projects for independent quotas. Copy the template and put the keys in the private `.env` file. The public template contains placeholders.

```bash
cp -n .env.example .env
chmod 600 .env
```

| Environment variable | Meaning |
| --- | --- |
| `LLM_API_KEYS` | Two or more distinct keys for the configured provider, in priority order. Backend only. |
| `LLM_MODEL` | Provider-qualified LiteLLM model. Defaults to `gemini/gemini-3.1-flash-lite`. |
| `DATABASE_URL` | SQLite file URL. `sqlite:////data/app.db` is an absolute container path. |
| `ALLOWED_ORIGINS` | Comma-separated browser origins, including scheme and port if applicable. |
| `ENABLE_FAILURE_SIMULATION` | `true` honors the test header. The default is `false`. |
| `DEFAULT_SYSTEM_PROMPT` | Instructions used for a new session without an override. |
| `LLM_REQUEST_TIMEOUT` | Maximum seconds per key attempt. Defaults to 25. |
| `CACHE_TTL` | Lifetime of an in-memory completion in seconds. Defaults to 3,600. |
| `VITE_API_BASE_URL` | Browser-facing backend URL. Vite embeds this public setting at build time. |
| `PORT` | Backend listen port for `python -m app`. Defaults to 8000. |
| `LITELLM_LOCAL_MODEL_COST_MAP` | Uses LiteLLM's bundled model map at startup. Defaults to `True`. |
| `LITELLM_LOG` | LiteLLM log level. Defaults to `CRITICAL`. |

### Replace a Gemini key denied generation access

The configured `key_2` could list models and count tokens. Google returned `403 PERMISSION_DENIED` on generation with both `gemini-3.1-flash-lite` and `gemini-2.5-flash-lite`, stating that the Gemini API Free Tier is unavailable for that project. A direct uncached LiteLLM call reproduced the 403. `key_1` completed a request against the configured model. [Gemini API key management](https://ai.google.dev/gemini-api/docs/api-key)

Create one key in a project that already has generation access to `gemini-3.1-flash-lite`. In the private root `.env`, replace only the second comma-separated value of `LLM_API_KEYS`. Enter the key directly in the file and keep its permissions at `0600`. Recreate the local backend with `docker compose up -d --no-build --wait backend` so it reads the changed variable. Keep the existing SQLite volume. Then run the live verifier.

### With Docker

Use Docker Engine with Compose v2 or newer.

```bash
docker compose config --quiet
make up
```

Open the [frontend](http://localhost:3000) and check [backend health](http://localhost:8000/health). The backend mounts the Compose `chat_data` volume at `/data`. `make down` leaves that volume available for the next `make up`.

### Without Docker

Use Python 3.13 and Node.js 24. From the repository root, start the backend in one terminal. The command overrides the container database path for manual development.

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
DATABASE_URL=sqlite:///./data/app.db .venv/bin/python -m uvicorn app.main:create_app \
  --factory --env-file ../.env --host 127.0.0.1 --port 8000
```

In another terminal, run the frontend. Vite reads the root `.env` and exposes only the public `VITE_` setting to browser code.

```bash
cd frontend
npm ci
npm run dev
```

### Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

The backend tests replace the provider's HTTP response and exercise the real LiteLLM Gemini adapter, key selection and cache. They use temporary SQLite files and require no API keys. The frontend tests cover turn submission, history, metadata, drafts, validation, and error handling.

## Design decisions: key fallback, caching, SQLite session storage

- **Key fallback.** The gateway calls LiteLLM's async completion API with an explicit key per attempt. It starts at `key_1` and advances on rate limits, quota errors, provider 5xx responses, connection failures, timeouts, or credential failures. Each key gets at most one application attempt. The provider timeout applies separately to each key. The deterministic order keeps key IDs and attempt counts observable. If all keys fail, the gateway returns the assignment's JSON 503.
- **Caching.** The built-in LiteLLM local response cache keys requests by model and the full ordered message list. Matching conversations across session IDs can share a completion. The gateway reads LiteLLM's cache-hit flag and reuses the usage on that completion. Recognized simulation headers set the documented `no-cache` and `no-store` options on that request. Cache entries expire according to `CACHE_TTL`, can be evicted at capacity, and are cleared when the single process restarts. Startup loads the callback dependencies required by LiteLLM 1.108.13 so the first cache hit does not pay that import cost. [LiteLLM SDK cache controls](https://docs.litellm.ai/docs/caching/all_caches#switch-cache-on--off-per-litellm-call)
- **Token usage.** LiteLLM normalizes provider usage to `prompt_tokens` and `completion_tokens`. The input covers the system prompt, previous turns, and new message. The backend measures elapsed time for the current resolution, including failed attempts, using a monotonic clock. An unusable provider completion returns 503.
- **Persistence.** FastAPI initializes the SQLite schema on startup and uses WAL mode. A per-session async lock keeps overlapping turns in sequence. A short SQLite transaction commits the prompt setting and both messages together after inference succeeds. The active system prompt lives in a separate table. The supported topology is one backend process sharing one disk and in-memory cache. History is addressable by session ID for this assessment. The frontend generates an unpredictable ID for each new chat and each page load.

## Verification: how to see failover, cache hits and per-message token usage

The commands use `curl` and `jq`. For local verification, set `API=http://localhost:8000`. Run the block once per demo so the timestamp gives the first request a fresh cache identity.

```bash
export API='https://lyftr-backend-production.up.railway.app'
STAMP="$(date +%s)-$$"
PROMPT="In one sentence, explain how caching saves time. Demo reference $STAMP."

post_chat() {
  local session="$1" message="$2"
  shift 2
  jq -nc --arg session_id "$session" --arg message "$message" '{session_id: $session_id, message: $message}' |
    curl -sS -w '\nHTTP %{http_code}\n' "$API/chat" -H 'Content-Type: application/json' "$@" --data-binary @-
}

curl -fsS "$API/health" | jq
post_chat "live-$STAMP" "$PROMPT"
post_chat "cache-$STAMP" "$PROMPT"
post_chat "fallback429-$STAMP" "$PROMPT" -H 'X-Simulate-Failure: key_1=429'
post_chat "fallback500-$STAMP" "$PROMPT" -H 'X-Simulate-Failure: key_1=500'
post_chat "unavailable-$STAMP" "$PROMPT" -H 'X-Simulate-Failure: *=429'
post_chat "both-$STAMP" "$PROMPT" -H 'X-Simulate-Failure: key_1=429,key_2=500'
curl -i "$API/sessions/unavailable-$STAMP/messages"
curl -fsS "$API/sessions/live-$STAMP/messages" | jq
```

The first two calls showed `LIVE_INFERENCE` and `LLM_CACHE` with identical replies and per-turn token usage. The cache hit reports `key_id: null` and zero fallback attempts. The next two calls reuse the prompt to demonstrate bypass of the warm cache. A successful live fallback must return HTTP 200, nonempty assistant text, `key_id: "key_2"`, and `fallback_attempts: 1`. The demo currently returns HTTP 503 for those calls because Google denies generation on the secondary project. Both forced all-key failures return `{"detail":"all providers unavailable"}`. History for a failed new session returns HTTP 404.

Show multi-turn memory and isolate an independent session using the same follow-up wording.

```bash
post_chat "memory-$STAMP" "My favorite language is Python."
post_chat "memory-$STAMP" "What is my favorite language?"
post_chat "isolated-$STAMP" "What is my favorite language?"
curl -fsS "$API/sessions/memory-$STAMP/messages" | jq
```

To verify the named Docker volume, run `make down` then `make up` and fetch `/sessions/memory-$STAMP/messages` again from the same shell. Compare the stored messages and metadata.

To check hosted persistence, run these commands after the memory example. Link the Railway CLI to the Lyftr service's production environment first.

```bash
curl -fsS "$API/sessions/memory-$STAMP/messages" | jq -S . > /tmp/lyftr-railway-before.json
RESTARTED_AT=$(date -u +%FT%TZ)
railway restart --service lyftr-backend --yes
curl -fsS --retry 12 --retry-all-errors --retry-delay 2 "$API/health"
railway logs --service lyftr-backend --deployment --since "$RESTARTED_AT" --lines 30
```

After the logs show `Application startup complete`, compare the saved and current history.

```bash
curl -fsS "$API/sessions/memory-$STAMP/messages" | jq -S . > /tmp/lyftr-railway-after.json
diff -u /tmp/lyftr-railway-before.json /tmp/lyftr-railway-after.json
```

### Automated live verification

The strict verifier expects real replies from both Gemini keys. Its successful-failover assertion remains blocked while Google rejects the secondary credential. Use `--extended` for all four simulation codes. Save a history snapshot to verify restart persistence.

```bash
python3 scripts/verify_live.py http://localhost:8000 --extended --write-history /tmp/lyftr-history.json
docker compose restart backend frontend
curl --fail --retry 12 --retry-all-errors --retry-delay 2 http://localhost:8000/health
python3 scripts/verify_live.py http://localhost:8000 --check-history /tmp/lyftr-history.json
```

### Demo recording (2–3 minutes)

Record your screen with your own narration and share the finished video link. Open the Railway health endpoint before recording to wake the service if it is idle. Describe the secondary-key 503 accurately if Google still rejects that credential.

| Time | Show |
| --- | --- |
| 0:00–0:35 | Open the deployed frontend. Send “My favorite language is Python.” Ask “What is my favorite language?” Point to the model, resolution source, latency, and input/output token counts. |
| 0:35–1:15 | In a terminal with `API` set to the public backend, show `/health`. Run the live and cache calls from the smoke block and compare replies, elapsed times, and key IDs. |
| 1:15–1:55 | Run `key_1=429` and `key_1=500` against the warmed prompt. With an eligible secondary key, point out the real reply, `key_2`, and one fallback attempt. If access is still blocked, show the 503 and state the Google project restriction. Run `*=429` and show the exact HTTP 503 and 404 history result. |
| 1:55–2:30 | Show the successful history response. Explain how FastAPI reads SQLite context, routes through LiteLLM, and saves each turn atomically. Point to the Railway `/data` volume and show the identical history returned after the backend restart. |

### Submission checklist

- [x] Verify the public GitHub repository, frontend, and Railway HTTPS endpoint.
- [ ] Verify both keys independently and capture HTTP 200 for each primary-failure simulation. Restart the backend and compare the saved history over HTTPS.
- [x] Verify the Railway service runs on Free with `/data` mounted and its usage fits the Free allowance during verification.
- [ ] Record the 2–3 minute walkthrough with your own narration and verify the video link is accessible.
- [ ] Submit the repository, frontend, backend, and recording links with the verified persistence status.

## Setup Used: your editor and AI tools

Development and verification were performed with the Codex desktop app on macOS. Codex assisted with implementation, test design, debugging, and documentation. The original Lyftr assessment PDF and LiteLLM documentation were used as references.

## Bonus features (if any): what you added beyond the requirements and why

The workspace includes an optional system prompt editor, Markdown replies, and an in-page conversation switcher so earlier sessions can be reopened through the history API while the page is open.

## Requirement audit

Verification recorded on 21 November 2026. The automated suites use provider HTTP fixtures. Public and local smoke checks used real Gemini inference for the working primary key.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Configuration and repository secret hygiene | PASS | `.env` has mode `0600` and is Git-ignored. The audit found no credential matches in Git objects, tracked files, frontend builds, 18 image layers, or inspected runtime logs. |
| Both Gemini keys verified independently | FAIL | `key_1` returned an uncached LiteLLM completion with 8 input and 2 output tokens. For `key_2`, model discovery and token counting succeeded, but both tested models returned `403 PERMISSION_DENIED` for generation because the project lacks Free Tier access. |
| FastAPI endpoint shapes and input validation | PASS | Backend tests cover the three endpoints, metadata, CORS preflight, 422 validation, 404 history, and JSON errors. |
| Inference, ordered fallbacks, and simulation | PASS | Provider fixtures cover primary success, 429, quota, 500/502/503, flag-off behavior, a warm-cache bypass, and exact 503 responses with no history writes. |
| Real Gemini primary inference | PASS | Real `key_1` inference works locally and over HTTPS. |
| Successful live secondary failover | BLOCKED | Simulated primary 429 and 500 bypassed the warm cache. The secondary denial resulted in exact 503s and unchanged history. The fixture suite verifies successful fallback. |
| LiteLLM exact-match cache and per-request usage | PASS | On Railway, the same prompt in two sessions returned identical replies and token counts. The live request took 1,218 ms and the cache hit took 1 ms, with 28 input and 45 output tokens in both. |
| SQLite history, conversation isolation, and atomic writes | PASS | Real requests verified recall, separate sessions, chronological order, and higher input-token counts for stored context. The hosted history, including metadata, matched over HTTPS after Railway mounted `/data` and started a fresh server process. |
| Docker Engine, image builds, and Compose | PASS | Docker Engine 29.9.3, `docker compose config --quiet`, `make up`, and `make down` were verified. Both localhost URLs responded. |
| React contract and responsive browser UI | PASS | TypeScript and both builds passed. The public browser displayed real Gemini replies and cache metadata, cleared the input, and showed a styled 390 px layout with no horizontal overflow. |
| Automated regression checks | PASS | 33 backend tests and 9 frontend tests passed. |
| Public GitHub publication | PASS | GitHub confirmed that `Aditya-112/lyftr-assignment` is public and received the source branch. |
| Railway build, deployed memory, and allowance | PASS | Railway built the Docker image and served the test requests on Free. Railway sampled a peak of about 242 MB during verification, within its 0.5 GB RAM limit. The workspace showed a $0 current bill. |
| Cloudflare Pages Free deployment | PASS | The production Pages hostname loaded in the browser, connected to Railway, cleared the composer after sending, and rendered a live Gemini reply with model and token metadata. |
| Public API and SQLite persistence | PASS | Public HTTPS checks covered health, chat, cache, Pages-only browser CORS, exact 503 with unchanged history, and malformed JSON 422. The same HTTPS history response survived a controlled Railway service restart. |
| Zero-cost boundary | PASS | The current deployment uses Railway Free and Cloudflare Pages Free. No paid hosting resources were created. |
| Demo and submission preparation | PASS | Commands and a timed walkthrough are ready. Candidate narration, recording, and submission remain pending. |
