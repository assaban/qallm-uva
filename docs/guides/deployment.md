# Deploying QALLM: separating frontend from API

This document is the source of truth for deploying QALLM. It complements the README (which gives a quickstart for running QALLM locally and with Docker) by covering production topology: how to separate the React frontend from the FastAPI backend, configure CORS and TLS, and the operational considerations that follow. For what QALLM *does* once running, see [`workflow-design.md`](workflow-design.md).

## The current default: integrated deployment

By default, QALLM ships as a single Docker container that serves both:

- The FastAPI backend at `/api/*`
- The built React frontend at `/` (static files served from `web/frontend/dist/`)

This is the simplest deployment: one container, one port, no cross-origin concerns. It is what you get from `docker compose up`.

The frontend is built once during the Docker build step (`vite build`), then served by FastAPI's `StaticFiles` mount. The frontend's API calls use relative URLs (`/api/...`) which resolve to the same origin, so no CORS configuration is needed for production.

This is recommended for:

- Local development of the full pipeline.
- Demo deployments where you want one URL to share.
- Thesis demonstrations.
- Reviewers running QALLM on their own machines.

## When to separate frontend from API

You might want to split them if:

- You want to host the frontend on a static-asset CDN (Vercel, Netlify, Cloudflare Pages) for global low-latency delivery.
- You need to scale the API independently (more workers, more memory, different machine).
- You want to update the frontend without redeploying the API (or vice versa).
- You have separate domains for the marketing/landing page and the application.

For an MSc thesis, none of these are likely to apply. The integrated deployment is fine. If you do need to split, the rest of this document is the recipe.

## Architecture of a split deployment

```
┌──────────────────────────┐         ┌────────────────────────────┐
│   Frontend (static)      │         │   API (Docker container)   │
│   Vercel / Netlify /     │ ──────► │   FastAPI on port 8000     │
│   Cloudflare Pages / S3  │  CORS   │   /api/* endpoints only    │
└──────────────────────────┘         └────────────────────────────┘
        https://qallm.example.org             https://api.qallm.example.org
```

The frontend is built once (`npm run build` in `web/frontend/`) and deployed as static assets to any static host. The API runs as a Docker container behind a reverse proxy. The two communicate over HTTPS, with CORS configured on the API to accept the frontend's origin.

## Step-by-step instructions

### 1. Build the frontend with the API URL baked in

The frontend needs to know where the API lives. The cleanest way is a build-time environment variable.

In `web/frontend/.env.production`:

```
VITE_API_BASE_URL=https://api.qallm.example.org
```

In `web/frontend/src/api.ts`, ensure the base URL is read from the environment:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  // ... rest of the implementation
}
```

If your `api.ts` already builds paths as relative `/api/...`, change the base resolution to use `API_BASE` so production builds point at the remote API.

Build:

```
cd web/frontend
npm install
npm run build
```

The output is in `web/frontend/dist/`. Upload this directory to your static host:

- **Vercel**: `cd web/frontend && vercel deploy --prod` (one-time setup needed).
- **Netlify**: drag-and-drop `dist/` into the Netlify dashboard, or use `netlify deploy --dir=dist --prod`.
- **S3 + CloudFront**: `aws s3 sync dist/ s3://your-bucket/ --delete`.
- **Cloudflare Pages**: connect the GitHub repo, set build command to `cd web/frontend && npm install && npm run build`, set publish directory to `web/frontend/dist`.

### 2. Configure the API to NOT serve the frontend

When the frontend lives elsewhere, the API should not also try to serve it. This is already handled by presence: the API mounts the frontend only when a built dist directory is found. The mount logic in `src/qallm/api/main.py` resolves the dist path from the `QALLM_FRONTEND_DIST` environment variable (used by the Docker image) and otherwise falls back to the source-tree location for editable installs:

```python
_env_dist = os.getenv("QALLM_FRONTEND_DIST")
if _env_dist:
    _FRONTEND_DIST = Path(_env_dist)
else:
    _FRONTEND_DIST = Path(__file__).resolve().parents[2].parent / "web" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
else:
    logger.info("Frontend dist not found at %s; running API only", _FRONTEND_DIST)
```

So to run the API standalone, build an API-only image (do not run the frontend build stage) or point `QALLM_FRONTEND_DIST` at a path that does not exist. There is no separate on/off boolean; the presence of a dist directory is the switch.

```
# API-only: no dist present, so nothing is mounted at /
docker run -p 8000:8000 qallm-api
```

### 3. Configure CORS on the API

The API needs to accept cross-origin requests from your frontend's domain. CORS middleware is *not* wired in by default (the integrated deployment is same-origin and does not need it), so add it for a split deployment.

In `src/qallm/api/main.py`:

```python
allowed_origins = os.getenv(
    "QALLM_CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

When deploying:

```
docker run \
  -e QALLM_CORS_ORIGINS=https://qallm.example.org \
  -p 8000:8000 \
  qallm-api
```

(API-only because this image was built without the frontend dist; see step 2.)

### 4. Set up TLS

Both the frontend and the API must be served over HTTPS in production. Browsers reject mixed-content requests (HTTPS page calling HTTP API). Options:

- Put both behind a reverse proxy (Caddy, Traefik, nginx with Let's Encrypt).
- Use the static host's built-in TLS (Vercel, Netlify, Cloudflare Pages all give it for free).
- For the API, use a managed platform (Fly.io, Render, Railway) that handles TLS automatically.

### 5. Verify end to end

After deployment:

```
# API health check
curl https://api.qallm.example.org/api/health
# Should return {"status": "online"}

# CORS preflight
curl -X OPTIONS https://api.qallm.example.org/api/health \
     -H "Origin: https://qallm.example.org" \
     -H "Access-Control-Request-Method: GET" \
     -v
# Should include "Access-Control-Allow-Origin: https://qallm.example.org" in response
```

Then load the frontend in a browser and verify the network tab shows API calls going to the remote host with status 200.

## Operational considerations

### Sessions live in memory on the API

QALLM's API stores session state (orchestrator, uploaded files, intermediate results) in an in-memory dictionary. This means:

- **Restarting the API kills all active sessions.** The user has to upload again.
- **Multiple API workers do not share sessions.** A session created on worker 1 cannot be resumed by worker 2.

For a thesis-scope deployment this is fine. For production, you would need:

- A persistent session store (Redis, PostgreSQL).
- Sticky sessions in the load balancer, or shared session storage.

The Dockerfile currently uses `--workers 1` for this reason. Do not increase worker count without first solving session storage.

### File uploads land in /tmp on the API container

Uploaded files go to `/tmp/qallm_upload_*` on the API host. These survive within the container but vanish on restart. For long-running sessions, mount a persistent volume:

```yaml
services:
  api:
    image: qallm-api
    volumes:
      - qallm_uploads:/tmp/qallm_uploads
      - qallm_outputs:/app/outputs
    environment:
      - TMPDIR=/tmp/qallm_uploads
```

### Cost: API calls happen from the API host

When QALLM calls OpenAI/Anthropic, the requests originate from the API container, not from the frontend. This means:

- API keys are stored as environment variables on the API host, never sent to the frontend.
- API costs are billed to the OpenAI/Anthropic account whose key is configured on the API host.
- Rate limits apply to the API host, not per-user.

For a multi-user deployment, you would need either per-user API keys (handled in the request body, not env vars) or a billing mechanism. Neither is implemented in QALLM v1.

## Reverting to integrated deployment

If you have already split the deployment and want to go back:

```
docker run -p 8000:8000 qallm-api
# An image built with the frontend dist serves the UI at / automatically.
```

Visit `http://localhost:8000` and the integrated UI loads. No CORS issues because everything is same-origin.

## Recommendation for the thesis

**Stay with the integrated deployment.** It is the simplest, lowest-friction option for:

- Running pilot experiments on a thesis-grade VM.
- Demonstrating QALLM during the defence.
- Sharing the project with reviewers who can clone the repo and run `docker compose up`.

The split-deployment instructions in this document exist for completeness and as a deployment guide if anyone (you or a future user) wants to take QALLM beyond the thesis. They are not needed for the thesis itself.

## Continuous integration and staging deploys

### CI (quality gate)

`.github/workflows/ci.yml` runs on every push and pull request to `dev` and `main`. It installs the package, lints `src/qallm` with ruff, and runs the full test suite on Python 3.10 and 3.12. It does **not** deploy anything and has no access to any server: it is purely a merge gate, so a red run means do not merge. Deployment is deliberately kept separate from CI so that no external system (GitHub Actions, tokens) can reach the research VM.

### Staging deploy (manual, on the VM)

The staging server tracks a branch (default `dev`) and is updated by hand with `scripts/deploy.sh`, run on the VM after a merge:

```
cd ~/qallm-uva
./scripts/deploy.sh                  # deploy the tracked branch (dev)
QALLM_BRANCH=main ./scripts/deploy.sh   # deploy a different branch or tag
```

The script fast-forwards the tracked branch, rebuilds the image, restarts the container, prunes the old image, and polls `/api/health` so a broken deploy fails loudly. It refuses to run if the working tree has uncommitted changes or if `.env` is missing, both of which would otherwise cause silent or confusing failures on a shared box.

This is the recommended model for a dev/staging VM: the test gate is automated, the deploy is a single auditable command, and nothing outside the VM holds credentials to it. If QALLM later becomes a longer-lived service under a single owner, full push-to-deploy can be revisited then, weighing the convenience against giving a CI runner SSH access to the infrastructure.
