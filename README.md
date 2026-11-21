# Lyftr Chat

Lyftr Chat is a multi-turn LLM chatbot with deterministic API-key failover and exact-match response caching. Each assistant reply shows its resolution source, model, elapsed time, and token usage. The stack uses React, TypeScript, Vite, FastAPI, LiteLLM, and SQLite.

## Live URLs

The source is available in the [public GitHub repository](https://github.com/Aditya-112/lyftr-assignment). Hosted frontend and backend URLs are pending. The verified local frontend is `http://localhost:3000` and the backend is `http://localhost:8000`.

### Zero-cost hosting options

| Option | SQLite persistence | Availability and cost |
| --- | --- | --- |
| Railway Free backend with a Cloudflare Pages frontend | The backend can mount its own SQLite file on the included 0.5 GB volume. | Railway stops service after the included allowance is exhausted. Access and Gemini egress still need verification. Pages can build and serve the React frontend on its free plan. [Railway Free plan](https://docs.railway.com/pricing/free-plan) · [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/) |
| Render Free Docker backend with a Render Static Site | The backend filesystem is ephemeral. Sleep, restarts, and deploys clear its SQLite history. | Use a free workspace with no payment method so overages suspend service instead of incurring charges. A paid disk is outside the budget. [Render Free restrictions](https://render.com/docs/free) |
| Oracle Cloud Always Free | An eligible VM and boot volume can retain SQLite. | Requires an eligible, accessible tenancy. New-account verification requires a card. [Oracle Free Tier FAQ](https://www.oracle.com/cloud/free/faq/) |
| Cloudflare Quick Tunnels to local Docker | The existing named volume retains SQLite while the local machine runs Docker. | The hostnames change when the tunnel processes restart. Suitable for a scheduled demo. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) |

### Deploy on Railway Free and Cloudflare Pages Free

1. In an authorized **Railway Free** workspace, create one backend service from the public GitHub repository. Use `backend` as the service root, build with its Dockerfile, and set the health check to `/health`. Generate a public HTTPS domain for port `8000`. Keep one replica and confirm that the workspace is on the Free plan, which stops services when its included resource allowance runs out. [Railway Free plan](https://docs.railway.com/pricing/free-plan)
2. Attach the included 0.5 GB volume at `/data`. Set `DATABASE_URL=sqlite:////data/app.db` and `RAILWAY_RUN_UID=0` so the service can write to Railway's root-owned volume. Put two valid Gemini keys in the backend's sealed `LLM_API_KEYS` variable. Set `LLM_MODEL=gemini/gemini-3.1-flash-lite`, `ENABLE_FAILURE_SIMULATION=true`, and `PORT=8000`. Set `ALLOWED_ORIGINS` to the exact HTTPS Pages origin once assigned. Use `http://localhost:3000` for initial backend verification. [Railway volume permissions](https://docs.railway.com/volumes#permissions)
3. Create a **Cloudflare Pages Free** project using Direct Upload. Build with Node.js 24 and the verified Railway HTTPS origin in `API`. Use the same project name and production branch for creation and deployment. [Cloudflare Pages Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)

   ```bash
   npm --prefix frontend ci --include=dev
   VITE_API_BASE_URL="$API" npm --prefix frontend run build
   wrangler pages project create lyftr-assignment --production-branch main --force
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

Set `API` to the deployed backend HTTPS URL for the demo or to `http://localhost:8000` for local verification. The commands use `curl` and `jq`. Run the block once per demo so the timestamp gives the first request a fresh cache identity.

```bash
export API='http://localhost:8000'
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

The first two calls should show `LIVE_INFERENCE` and `LLM_CACHE` with identical replies and per-turn token usage. The cache hit reports `key_id: null` and zero fallback attempts. The next two calls use the same prompt on purpose and should return real answers from `key_2` despite the warm cache. With two keys, both all-failed cases return HTTP 503 and `{"detail":"all providers unavailable"}`. History for the failed session returns HTTP 404.

Show multi-turn memory and isolate an independent session using the same follow-up wording.

```bash
post_chat "memory-$STAMP" "My favorite language is Python."
post_chat "memory-$STAMP" "What is my favorite language?"
post_chat "isolated-$STAMP" "What is my favorite language?"
curl -fsS "$API/sessions/memory-$STAMP/messages" | jq
```

To verify the named Docker volume, run `make down` then `make up` and fetch `/sessions/memory-$STAMP/messages` again from the same shell. Compare the stored messages and metadata.

### Automated live verification

The script expects real Gemini replies. Use `--extended` for all four simulation codes. Save a history snapshot to verify restart persistence on Docker or a hosted volume.

```bash
python3 scripts/verify_live.py http://localhost:8000 --extended --write-history /tmp/lyftr-history.json
docker compose restart backend frontend
curl --fail --retry 12 --retry-all-errors --retry-delay 2 http://localhost:8000/health
python3 scripts/verify_live.py http://localhost:8000 --check-history /tmp/lyftr-history.json
```

### Demo recording (2–3 minutes)

Record your screen with your own narration and share the finished video link. Prepare the command block and wake the Railway service before recording. Keep the local Docker restart check available as separate evidence of local persistence.

| Time | Show |
| --- | --- |
| 0:00–0:35 | Open the deployed frontend. Send “My favorite language is Python.” Ask “What is my favorite language?” Point to the model, resolution source, latency, and input/output token counts. |
| 0:35–1:15 | In a terminal with `API` set to the public backend, show `/health`. Run the live and cache calls from the smoke block and compare replies, elapsed times, and key IDs. |
| 1:15–1:55 | Run `key_1=429` against the warmed prompt. Show the real answer and `key_2`, then run `*=429` and show the HTTP 503 and 404 history result. |
| 1:55–2:30 | Show the successful history response. Explain how FastAPI reads SQLite context, routes through LiteLLM, and saves each turn atomically. Point to the `/data` volume in Compose. |

### Submission checklist

- [ ] Confirm the public GitHub repository and both verified HTTPS URLs open in a signed-out browser.
- [ ] Run the live verifier, restart Railway, and compare the saved history over HTTPS.
- [ ] Record the 2–3 minute walkthrough with your own narration and verify the video link is accessible.
- [ ] Submit the repository, frontend, backend, and recording links with the verified persistence status.

## Setup Used: your editor and AI tools

Development and verification were performed with the Codex desktop app on macOS. Codex assisted with implementation, test design, debugging, and documentation. The original Lyftr assessment PDF and LiteLLM documentation were used as references.

## Bonus features (if any): what you added beyond the requirements and why

The workspace includes an optional system prompt editor, Markdown replies, and an in-page conversation switcher so earlier sessions can be reopened through the history API while the page is open.

## Requirement audit

Verification recorded on 21 November 2026. Provider HTTP fixtures drive the application tests. They exercise the real LiteLLM adapter and cache.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Configuration and repository secret hygiene | PASS | `.env` has mode `0600` and is Git-ignored. The audit found no credential matches in 38 Git objects, 32 tracked files, 8 frontend build files, and 18 layers across the two Docker images. |
| Both Gemini keys verified independently | BLOCKED | Verification with two rotated credentials is pending. |
| FastAPI endpoint shapes and input validation | PASS | Backend tests cover the three endpoints, metadata, CORS preflight, 422 validation, 404 history, and JSON errors. |
| Inference, ordered fallbacks, and simulation | PASS | Provider fixtures cover primary success, 429, quota, 500/502/503, flag-off behavior, a warm-cache bypass, and exact 503 responses with no history writes. |
| Real Gemini inference and end-to-end failover | BLOCKED | Needs two usable replacement Gemini keys. |
| LiteLLM exact-match cache and per-request usage | PASS | Backend tests compare live and cached content and token counts, count provider calls, and vary messages, system prompts, and history. |
| SQLite history, conversation isolation, and atomic writes | PASS | Tests verify ordered history, context, separate sessions, and rollback. Docker returned an identical stored history response after container restart and a separate down/up cycle. |
| Docker Engine, image builds, and Compose | PASS | Docker Engine 29.9.3, `docker compose config --quiet`, `make up`, and `make down` were verified. Both localhost URLs responded. |
| React contract and responsive browser UI | PASS | TypeScript and the production build passed. The Docker-hosted browser showed the API connection, prompt selection, and a 390 px layout with no horizontal overflow. |
| Automated regression checks | PASS | 33 backend tests and 9 frontend tests passed. |
| Public GitHub publication | PASS | GitHub confirmed that `Aditya-112/lyftr-assignment` is public and received the source branch. |
| Railway Free memory limit | PASS | The local backend peaked at 238.8 MB under a 500 MB Docker cgroup cap during startup, a cache hit, and 12 concurrent fixture-backed requests. Railway build, runtime memory, and credit usage need public verification. |
| Cloudflare Pages Free project setup | PASS | The `lyftr-assignment` Direct Upload project exists and is ready for the frontend build configured with the Railway API origin. |
| Hosted frontend and backend, CORS, real API calls | BLOCKED | Requires rotated keys and authorization for a Railway Free workspace. |
| Hosted SQLite persistence | NOT VERIFIED | A Railway volume and restart verification are pending. |
| Zero-cost boundary | PASS | No paid hosting resources or billing changes were made. |
| Demo and submission preparation | PASS | Commands and a timed walkthrough are ready. Candidate narration, recording, and submission remain pending. |
