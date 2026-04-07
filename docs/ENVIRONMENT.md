# Environment Variables

Server-deployment view of repo-root `.env`.

## Runtime Assumptions
- sibling `root-proxy` is the only public entrypoint
- `root-proxy` currently routes `ai.nextinsol.com` to `ai-proxy-frontend:8080`
- `frontend` joins external Docker network `edge-net`
- backend, PostgreSQL, and Redis stay internal to the app stack

## Main Variables

### Edge
- `AI_PROXY_CONTAINER_NAME`
  - frontend container name seen by `root-proxy`
  - keep aligned with the upstream container name in sibling `root-proxy`
  - current value: `ai-proxy-frontend`

### Database
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

### App
- `APP_NAME`
- `APP_ENV`
- `AUTH_COOKIE_SECURE`
  - keep `true` when traffic comes through HTTPS on `root-proxy`
- `AUTH_DATA_ENCRYPTION_KEY`
  - Fernet key used to encrypt stored OAuth transaction payloads
  - required only when Microsoft login is enabled

### Vertex
- `GOOGLE_APPLICATION_CREDENTIALS`
  - in-container path to the mounted service account JSON
- `GOOGLE_CLOUD_PROJECT`
  - required
- `GOOGLE_CLOUD_LOCATION`
- `VERTEX_AI_MODEL`
- `VERTEX_AI_API_VERSION`
- `VERTEX_AI_RAG_CORPORA`
  - optional
- `VERTEX_AI_RAG_SIMILARITY_TOP_K`
- `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`

### Chat Coordination
- `CHAT_INFLIGHT_LOCK_TTL_SECONDS`
- `CHAT_RATE_LIMIT_PER_MINUTE`
- `CHAT_RATE_LIMIT_PER_HOUR`

### Microsoft Auth
- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_AUTHORITY`
  - default: `https://login.microsoftonline.com/common`
- `MICROSOFT_REDIRECT_PATH`
  - default: `/api/v1/auth/callback/microsoft`
- `MICROSOFT_OAUTH_TRANSACTION_MINUTES`
  - default: `10`

### Startup
- `STARTUP_DEPENDENCY_MAX_ATTEMPTS`
- `STARTUP_DEPENDENCY_RETRY_SECONDS`

### Image Pins
- `PYTHON_VERSION`
- `PIP_VERSION`
- `NODE_VERSION`
- `NPM_VERSION`
- `POSTGRES_VERSION`
- `NGINX_VERSION`
- `REDIS_VERSION`

## Compose-Derived Variables
- `DATABASE_URL`
  - built in `deploy/docker-compose.yml`
- `REDIS_URL`
  - built in `deploy/docker-compose.yml`
- `APP_HOST=0.0.0.0`
- `APP_PORT=8000`

## Secrets
- `../secrets` is mounted into the backend at `/run/secrets`
- default service account path: `/run/secrets/gcp-service-account.json`

## Current Notes
- RAG stays inactive unless `VERTEX_AI_RAG_CORPORA` contains valid corpus resource names
- Microsoft auth becomes active only after `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `AUTH_DATA_ENCRYPTION_KEY` are set
- usage logging scaffolding exists in code but does not add env requirements yet
