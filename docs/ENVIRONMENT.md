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
  - Fernet key used to encrypt stored OAuth transaction and session-conflict ticket payloads
  - required only when Microsoft login is enabled
- `AUTH_GUEST_MAX_SESSIONS`
  - default: `2`
- `AUTH_MICROSOFT_MAX_SESSIONS`
  - default: `4`
- `AUTH_SESSION_LIMIT_STRATEGY`
  - default: `reject`
  - conflict resolution explicitly uses `evict_oldest`
- `AUTH_CONFLICT_COOKIE_NAME`
  - default: `session_conflict_id`
- `AUTH_CONFLICT_TICKET_MINUTES`
  - default: `5`

Note:
- `deploy/docker-compose.yml` currently passes only the auth env vars needed by the default runtime path.
- Session-limit values above are app-supported settings, but Compose uses code defaults unless the compose `proxy-api.environment` block is extended.

### Vertex
- `GOOGLE_APPLICATION_CREDENTIALS`
  - in-container path to the mounted service account JSON
- `GOOGLE_CLOUD_PROJECT`
  - required
- `VERTEX_AI_API_VERSION`
- `VERTEX_AI_RAG_CORPORA`
  - optional
- `VERTEX_AI_RAG_SIMILARITY_TOP_K`
- `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`

### OpenAI
- `OPENAI_API_KEY`
  - required when using OpenAI models
- `OPENAI_VECTOR_STORE_IDS`
  - comma-separated, newline-separated, or JSON-list vector store ids for OpenAI `retrieval`
- `OPENAI_FILE_SEARCH_MAX_NUM_RESULTS`
  - default: `5`
  - passed to the OpenAI `file_search` tool
- `OPENAI_FILE_SEARCH_SCORE_THRESHOLD`
  - optional number from `0` to `1`
  - passed as OpenAI `file_search.ranking_options.score_threshold`
- `OPENAI_CODE_INTERPRETER_MEMORY_LIMIT`
  - default: `4g`
  - allowed values: `1g`, `4g`, `16g`, `64g`

### Anthropic
- `ANTHROPIC_API_KEY`
  - required when using Anthropic models
- `ANTHROPIC_VERSION`
  - default: `2023-06-01`
  - Anthropic API contract version header, not a model version
- `ANTHROPIC_MAX_TOKENS`
  - default: `4096`
- `ANTHROPIC_WEB_SEARCH_MAX_USES`
  - default: `5`
- `ANTHROPIC_WEB_SEARCH_ALLOWED_DOMAINS`
  - optional comma-separated, newline-separated, or JSON-list domain allowlist
- `ANTHROPIC_WEB_SEARCH_BLOCKED_DOMAINS`
  - optional comma-separated, newline-separated, or JSON-list domain blocklist
  - do not set both allowed and blocked domain lists for one request

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
- public Gemini model ids are code-defined, not env-selected
- Vertex model locations are code-defined per model, not env-selected
- public OpenAI model ids are code-defined, not env-selected
- public Anthropic model ids are code-defined, not env-selected
- Google Search is exposed as a native Vertex tool and does not add env requirements
- RAG stays inactive unless `VERTEX_AI_RAG_CORPORA` contains valid corpus resource names
- Vertex URL context is exposed as a native Gemini tool and does not add env requirements
- OpenAI retrieval uses `OPENAI_VECTOR_STORE_IDS`
- OpenAI web search and code execution do not add env requirements beyond `OPENAI_API_KEY`
- Anthropic web search and code execution do not add env requirements beyond `ANTHROPIC_API_KEY`
- Microsoft auth becomes active only after `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `AUTH_DATA_ENCRYPTION_KEY` are set
- guest identity is keyed by raw request IP in `guest_identities`; local Docker commonly reports the bridge IP such as `172.18.0.1`
- chat history is PostgreSQL-backed and does not add env requirements
- usage logging scaffolding exists in code but does not add env requirements yet
