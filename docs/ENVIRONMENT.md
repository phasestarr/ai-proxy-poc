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

Server deployment trust boundary:
- sibling `root-proxy` is expected to be the only public HTTP entrypoint
- `root-proxy` must overwrite `X-Real-IP` and all `X-Forwarded-*` headers before traffic reaches this stack
- backend guest identity and Microsoft redirect URI construction rely on that sanitized edge header set
- local deployment can run without `root-proxy`, but local guest IPs may be Docker bridge addresses

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
- `STARTUP_DEPENDENCY_MAX_ATTEMPTS`
- `STARTUP_DEPENDENCY_RETRY_SECONDS`

### Auth Cookies And Session Limits

- `AUTH_SESSION_COOKIE_NAME`
- `AUTH_CONFLICT_COOKIE_NAME`
- `AUTH_COOKIE_SECURE`
  - server: `true`
  - local: `false`
  - session cookies always use `SameSite=strict`
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
  - runs auth cleanup, stale send cleanup, attachment remote reconciliation, attachment remote TTL cleanup, and attachment blob delete retry
  - keep this greater than `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS / 60` unless `delete_stale_empty_histories` is changed to skip active operations

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
  - internal blank-page upload staging drafts are eligible for deletion after this TTL if an interrupted operation leaves them behind
- `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`
  - bounds local validation, request preparation, context compaction, attachment upload/delete/toggle, and history delete operations
  - operation owners must still hold their DB token immediately before committing
- `CHAT_PROVIDER_EVENT_IDLE_TIMEOUT_SECONDS`
  - after provider dispatch, another provider event must arrive before this idle timeout
  - mapped provider chunks check the operation token, but DB heartbeat writes are throttled to the first event, provider-state transitions, and a derived heartbeat interval capped at 30 seconds
  - there is no background DB heartbeat loop while the service is idle
  - housekeeping marks streaming turns with no first event as `provider_first_response_timeout`
  - housekeeping marks streaming turns that started but stopped emitting events as `provider_response_timeout`
- `CHAT_PROVIDER_MAX_RUNTIME_SECONDS`
  - hard cap for one provider stream regardless of event activity
- `CHAT_RATE_LIMIT_PER_MINUTE`
- `CHAT_RATE_LIMIT_PER_HOUR`

### Usage Caps

- `USAGE_DEFAULT_CAP_USD`
  - default per-user effective usage cap when no `user_usage_caps` override exists
  - template default: `100`
  - cap enforcement is intentionally post-paid: it checks existing ledger spend before dispatch and records actual estimated spend after success

### Deployment Readiness

- `DEPLOYMENT_SMOKE_REQUIRED`
  - when `true`, `/health` runs deployment smoke until it passes
  - `frontend` waits for backend health, so public UI does not start until smoke succeeds
  - use `true` for server deployments and `false` for local runs that should not call provider APIs during startup
  - Compose only reads the file passed by `--env-file`; `docker-compose.local.yml` does not automatically load `.env.local`
  - current smoke requires all exposed providers: Vertex AI, OpenAI, and Anthropic
  - smoke exercises direct text generation and direct provider attachment upload-delete paths
  - product file uploads also prepare all three providers at attach time by design

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
  - optional blank value unless using `file_search`
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
- `VERTEX_AI_RAG_CORPORA` and `OPENAI_VECTOR_STORE_IDS` configure Vertex retrieval and OpenAI file search respectively
