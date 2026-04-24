# Environment

Current env surface for the Docker Compose runtime.

## Rule
- Compose commands in `deploy/README-SERVER.md` and `deploy/README-LOCAL.md` pass an explicit repo-root env file with `--env-file`
- server runtime uses `.env`
- local runtime uses `.env.local`
- runtime envs are passed explicitly through `deploy/docker-compose.yml`
- do not rely on mounting `.env` into containers
- if code starts reading a new env var, add it to:
  - `deploy/docker-compose.yml`
  - `.env.example`
  - this document

## Runtime Groups

### Compose and Image Pins
- `AI_PROXY_CONTAINER_NAME`
  - frontend container name seen by sibling `root-proxy`
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

### Auth Cookies and Session Limits
- `AUTH_SESSION_COOKIE_NAME`
  - default: `session_id`
- `AUTH_CONFLICT_COOKIE_NAME`
  - default: `session_conflict_id`
- `AUTH_COOKIE_SECURE`
  - local override sets this to `false`
- `AUTH_COOKIE_SAMESITE`
  - default: `strict`
- `AUTH_COOKIE_PATH`
  - default: `/`
- `AUTH_COOKIE_DOMAIN`
  - optional
- `AUTH_DATA_ENCRYPTION_KEY`
  - required for Microsoft auth flow
- `AUTH_GUEST_IDLE_MINUTES`
  - default: `360`
- `AUTH_GUEST_ABSOLUTE_HOURS`
  - default: `24`
- `AUTH_GUEST_MAX_SESSIONS`
  - default: `2`
- `AUTH_MICROSOFT_IDLE_MINUTES`
  - default: `1440`
- `AUTH_MICROSOFT_ABSOLUTE_DAYS`
  - default: `1`
- `AUTH_MICROSOFT_MAX_SESSIONS`
  - default: `4`
- `AUTH_SESSION_LIMIT_STRATEGY`
  - default: `reject`
- `AUTH_CONFLICT_TICKET_MINUTES`
  - default: `5`
- `AUTH_CLEANUP_INTERVAL_MINUTES`
  - default: `60`

### Microsoft Auth
- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_AUTHORITY`
  - default: `https://login.microsoftonline.com/common`
- `MICROSOFT_REDIRECT_PATH`
  - default: `/api/v1/auth/callback/microsoft`
- `MICROSOFT_OAUTH_TRANSACTION_MINUTES`
  - default: `10`
- `MICROSOFT_SCOPES`
  - JSON list string
  - default: `["email"]`

### Chat Coordination
- `CHAT_INFLIGHT_LOCK_TTL_SECONDS`
  - default: `180`
- `CHAT_RATE_LIMIT_PER_MINUTE`
  - default: `10`
- `CHAT_RATE_LIMIT_PER_HOUR`
  - default: `30`

### Vertex
- `GOOGLE_APPLICATION_CREDENTIALS`
  - default container path: `/run/secrets/gcp-service-account.json`
- `GOOGLE_CLOUD_PROJECT`
  - required to use Vertex
- `VERTEX_AI_API_VERSION`
  - default: `v1`
- `VERTEX_AI_RAG_CORPORA`
  - optional
- `VERTEX_AI_RAG_SIMILARITY_TOP_K`
  - default: `5`
- `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`
  - optional

Not env-driven:
- public Gemini model ids
- Vertex locations
- Vertex per-model response presets

### OpenAI
- `OPENAI_API_KEY`
  - required to use OpenAI
- `OPENAI_VECTOR_STORE_IDS`
  - required only for `retrieval`
- `OPENAI_FILE_SEARCH_MAX_NUM_RESULTS`
  - default: `5`
- `OPENAI_FILE_SEARCH_SCORE_THRESHOLD`
  - optional `0..1`
- `OPENAI_CODE_INTERPRETER_MEMORY_LIMIT`
  - default: `4g`
  - allowed: `1g`, `4g`, `16g`, `64g`

Not env-driven:
- public GPT model ids
- OpenAI per-model response presets

### Anthropic
- `ANTHROPIC_API_KEY`
  - required to use Anthropic
- `ANTHROPIC_VERSION`
  - default: `2023-06-01`
  - API contract header, not model version
- `ANTHROPIC_WEB_SEARCH_MAX_USES`
  - default: `5`
- `ANTHROPIC_WEB_SEARCH_ALLOWED_DOMAINS`
  - optional
- `ANTHROPIC_WEB_SEARCH_BLOCKED_DOMAINS`
  - optional

Not env-driven:
- public Claude model ids
- Anthropic per-model response presets
- output token caps

## Compose Overrides

### `deploy/docker-compose.local.yml`
- overrides `AUTH_COOKIE_SECURE=false`
- publishes frontend on `8080:8080`

### `deploy/docker-compose.server.yml`
- attaches frontend to external Docker network `edge-net`

## Removed Stale Wiring
- `GOOGLE_CLOUD_LOCATION`
  - removed from Compose because code does not read it
- `VERTEX_AI_MODEL`
  - removed from Compose because model selection is backend-owned in provider model catalogs
- `ANTHROPIC_MAX_TOKENS`
  - removed from env wiring because output caps now live in provider preset config

## Current Notes
- all runtime env values the backend reads should flow through Compose
- provider model catalogs are code-defined, not env-selected
- provider output caps are preset-defined in provider config files
- `VERTEX_AI_RAG_CORPORA` and `OPENAI_VECTOR_STORE_IDS` are the only tool-selection envs that materially enable retrieval features
- Microsoft auth remains optional until its required env vars are configured
