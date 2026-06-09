# Environment

Current env surface for the Docker Compose runtime.

## Rule

- Compose commands in `deploy/README-SERVER.md` and `deploy/README-LOCAL.md` pass an explicit repo-root env file with `--env-file`
- Server runtime uses `.env`
- Local runtime uses `.env.local`
- Runtime envs are passed explicitly through `deploy/docker-compose.yml`
- Do not rely on mounting `.env` into containers
- If code starts reading a new env var, add it to:
  - `deploy/docker-compose.yml`
  - `.env.example`
  - this document

## Runtime Groups

### Compose, Containers, And Image Pins

- `AI_PROXY_CONTAINER_NAME`
  - public frontend container name seen by sibling `root-proxy`
  - default template value: `ai-proxy`
- `AI_PROXY_BACKEND_CONTAINER_NAME`
- `AI_PROXY_POSTGRES_CONTAINER_NAME`
- `AI_PROXY_REDIS_CONTAINER_NAME`
- `PYTHON_VERSION`
- `PIP_VERSION`
- `NODE_VERSION`
- `NPM_VERSION`
- `POSTGRES_VERSION`
- `NGINX_VERSION`
- `REDIS_VERSION`

### Database

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Compose derives:

- `DATABASE_URL`
- `REDIS_URL`

### App Runtime

- `APP_NAME`
- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `STARTUP_DEPENDENCY_MAX_ATTEMPTS`
- `STARTUP_DEPENDENCY_RETRY_SECONDS`

### Auth Cookies And Session Limits

- `AUTH_SESSION_COOKIE_NAME`
- `AUTH_CONFLICT_COOKIE_NAME`
- `AUTH_COOKIE_SECURE`
  - server: `true`
  - local: `false`
- `AUTH_COOKIE_SAMESITE`
- `AUTH_COOKIE_PATH`
- `AUTH_COOKIE_DOMAIN`
  - optional blank value
- `AUTH_DATA_ENCRYPTION_KEY`
  - required for encrypted auth/session data
- `AUTH_SESSION_TTL_MINUTES`
- `AUTH_GUEST_MAX_SESSIONS`
- `AUTH_MICROSOFT_MAX_SESSIONS`
- `AUTH_SESSION_LIMIT_STRATEGY`
- `AUTH_CONFLICT_TICKET_MINUTES`
- `HOUSEKEEPING_INTERVAL_MINUTES`
  - runs auth cleanup, attachment remote reconciliation, and attachment remote TTL cleanup

### Microsoft Auth

- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_AUTHORITY`
- `MICROSOFT_REDIRECT_PATH`
- `MICROSOFT_OAUTH_TRANSACTION_MINUTES`
- `MICROSOFT_SCOPES`

Microsoft login remains optional at the product level, but these env keys must be
present because Compose wires all backend runtime settings explicitly. Leave
client ID and secret blank only when Microsoft login is intentionally disabled.

### Chat Coordination

- `CHAT_DRAFT_TTL_SECONDS`
- `CHAT_INFLIGHT_LOCK_TTL_SECONDS`
- `CHAT_RATE_LIMIT_PER_MINUTE`
- `CHAT_RATE_LIMIT_PER_HOUR`

### Chat Attachments

- `CHAT_ATTACHMENT_MAX_FILES_PER_HISTORY`
- `CHAT_ATTACHMENT_MAX_FILES_PER_USER`
- `CHAT_ATTACHMENT_MAX_FILE_BYTES`
- `CHAT_ATTACHMENT_MAX_TOTAL_BYTES_PER_HISTORY`
- `CHAT_ATTACHMENT_MAX_TOTAL_TOKENS_PER_PROVIDER`
- `CHAT_ATTACHMENT_REMOTE_TTL_HOURS`
  - deletes provider-side remote attachment copies after this many hours without use

Not env-driven:

- supported attachment MIME types
- provider attachment mapping rules
- attachment prompt injection order

### Vertex

- `GOOGLE_APPLICATION_CREDENTIALS`
  - container path, usually `/run/secrets/gcp-service-account.json`
- `GOOGLE_CLOUD_PROJECT`
  - required to use Vertex
- `VERTEX_AI_API_VERSION`
- `VERTEX_AI_ATTACHMENT_GCS_BUCKET`
  - required for Gemini file attachments
  - value is the bucket name only, for example `your-ai-proxy-attachments-bucket`
- `VERTEX_AI_ATTACHMENT_GCS_PREFIX`
- `VERTEX_AI_RAG_CORPORA`
  - optional blank value
- `VERTEX_AI_RAG_SIMILARITY_TOP_K`
- `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`
  - optional blank value

Not env-driven:

- public Gemini model ids
- Vertex locations
- Vertex per-model response presets

### OpenAI

- `OPENAI_API_KEY`
  - required to use OpenAI
- `OPENAI_VECTOR_STORE_IDS`
  - optional blank value unless using retrieval
- `OPENAI_FILE_SEARCH_MAX_NUM_RESULTS`
- `OPENAI_FILE_SEARCH_SCORE_THRESHOLD`
  - optional blank value
- `OPENAI_CODE_INTERPRETER_MEMORY_LIMIT`

Not env-driven:

- public GPT model ids
- OpenAI per-model response presets

### Anthropic

- `ANTHROPIC_API_KEY`
  - required to use Anthropic
- `ANTHROPIC_VERSION`
- `ANTHROPIC_WEB_SEARCH_MAX_USES`
- `ANTHROPIC_WEB_SEARCH_ALLOWED_DOMAINS`
  - optional blank value
- `ANTHROPIC_WEB_SEARCH_BLOCKED_DOMAINS`
  - optional blank value

Not env-driven:

- public Claude model ids
- Anthropic per-model response presets
- output token caps

## Compose Overrides

### `deploy/docker-compose.local.yml`

- publishes `ai-proxy` on `8080:8080`

### `deploy/docker-compose.server.yml`

- attaches `ai-proxy` to external Docker network `edge-net`

## Removed Stale Wiring

- `GOOGLE_CLOUD_LOCATION`
  - removed from Compose because code does not read it
- `VERTEX_AI_MODEL`
  - removed from Compose because model selection is backend-owned in provider model catalogs
- `ANTHROPIC_MAX_TOKENS`
  - removed from env wiring because output caps now live in provider preset config

## Current Notes

- All runtime env values the backend reads should flow through Compose
- Compose uses required interpolation, so missing env keys fail before startup
- Optional blank env values must still be present as blank assignments
- Provider model catalogs are code-defined, not env-selected
- Provider output caps are preset-defined in provider config files
- `VERTEX_AI_RAG_CORPORA` and `OPENAI_VECTOR_STORE_IDS` are the retrieval-related envs
