# Architecture

Current runtime and code ownership for `ai-proxy-poc`.

## Runtime Shape
- Public traffic enters sibling `root-proxy`
- `root-proxy` terminates TLS and routes `ai.nextinsol.com` to `ai-proxy-frontend:8080`
- `frontend` serves the SPA and proxies `/api/*` and `/health` to `proxy-api:8000`
- `proxy-api` uses PostgreSQL, Redis, Vertex AI, OpenAI, and Anthropic
- runtime is Docker Compose first; backend should not depend on host-local services

## Top-Level Components
- `frontend/`
  - React + Vite SPA packaged behind NGINX
- `proxy-api/`
  - FastAPI backend
- `deploy/`
  - Compose topology and run-mode overrides
- `docs/`
  - maintenance docs
- `secrets/`
  - mounted secret files such as the GCP service account JSON

## Frontend Flow
1. `frontend/src/App.tsx` boots auth state through `frontend/src/auth/useAuthSession.ts`.
2. Anonymous users stay on `LoginPage`.
3. Guest login uses `POST /api/v1/auth/login/guest`.
4. Microsoft login redirects the whole page to `GET /api/v1/auth/login/microsoft`.
5. Authenticated users land on `ChatPage`.
6. `ChatPage` loads the backend model catalog from `GET /api/v1/models`.
7. The frontend does not own model defaults; the user explicitly selects from the backend catalog.
8. Chat history list/load/delete goes through `frontend/src/chat/api/chatHistoryApi.ts`.
9. Chat history rename and pin/unpin also go through `frontend/src/chat/api/chatHistoryApi.ts`.
10. Chat send goes through `frontend/src/chat/api/streamChatApi.ts` to `POST /api/v1/chat/completions`.
11. The frontend consumes SSE `start`, `delta`, `status`, `done`, and `error`.

## Backend Flow
1. `proxy-api/app/main.py`
   - starts FastAPI
   - verifies Redis
   - runs Alembic migrations
   - purges expired auth data
   - starts background auth cleanup
2. `proxy-api/app/api/v1/api.py`
   - registers auth, models, and chat routers
3. `proxy-api/app/api/v1/endpoints/`
   - stays thin
   - owns HTTP shape only
4. `proxy-api/app/services/chat/preparation.py`
   - resolves `model_id` and `tool_ids`
5. `proxy-api/app/services/chat/turns.py`
   - persists user message and assistant placeholder
6. `proxy-api/app/services/chat/stream.py`
   - starts backend-owned provider execution
   - emits live SSE events if the browser is still connected
   - persists final success or failure outcomes
7. `proxy-api/app/providers/catalog.py`
   - builds the public model catalog
   - validates model/tool selections
8. `proxy-api/app/providers/dispatcher.py`
   - checks provider readiness
   - dispatches execution to the selected provider package

## Auth and Session Model
- browser auth uses only `HttpOnly` cookies
- `session_id`
  - raw key lives only in the cookie
  - DB stores `session_key_hash`
- `session_conflict_id`
  - short-lived conflict ticket cookie
  - DB stores `ticket_hash`
- guest users are keyed by raw IP address in `guest_identities`
- Microsoft login is backend-owned OAuth
- session conflict resolution is backend-owned and supports evicting the oldest active session

Important defaults from code:
- guest max active sessions: `2`
- Microsoft max active sessions: `4`
- session-limit strategy default: `reject`
- conflict ticket TTL default: `5 minutes`

## Data Ownership
- PostgreSQL is the system of record for:
  - users
  - auth sessions
  - OAuth transactions
  - conflict tickets
  - chat histories
  - chat messages
  - remembered-chat summary placeholders
- Redis is used for:
  - one in-flight chat lease per session
  - minute/hour chat rate limits
- provider-side conversation state is not treated as the source of truth

## Chat Persistence Model
- `POST /api/v1/chat/completions` creates a backend-owned turn only after backend preflight checks pass and provider dispatch is about to begin
- backend persists:
  - user message
  - assistant placeholder
  - resolved route metadata
  - final success or error outcome
- backend-local rejects such as validation failures, session locks, rate limits, and provider-readiness failures are not persisted
- if provider execution fails, the assistant message is kept renderable but marked `excluded_from_context=true`
- persisted provider-attempted failures keep provider-specific `result_code`, `result_message`, `finish_reason`, and safe `error_detail`
- future provider context is rebuilt from persisted non-error messages

## Chat History Metadata
- `chat_histories.title` stores the backend-owned history title text
- first-prompt auto-titles are normalized and capped to `80` characters without backend-added ellipsis
- manually renamed titles are capped to the DB column limit and rendered with frontend truncation when needed
- `chat_histories.pin_order`
  - `NULL` means unpinned
  - lower values sort earlier in the pinned section
  - new pins append to the end of the pinned section
- history list order is:
  - pinned histories by `pin_order ASC`
  - then unpinned histories by `COALESCE(last_message_at, created_at) DESC`
- metadata edits may change `updated_at`, but list ordering uses pin state and message activity timestamps

## Provider Layer

Shared provider layer:
- `proxy-api/app/providers/types.py`
- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/dispatcher.py`

Provider package shape:
- `models.py`
  - public model ids
  - provider runtime model ids
  - supported tool ids
- `config.py`
  - provider request preset mapping
  - model to preset mapping
- `tools.py`
  - tool metadata
  - provider-native hosted tool payloads
- `client.py`
  - SDK client creation and readiness checks
- `mapper.py`
  - internal messages to provider-native payload shape
  - provider chunks to shared stream chunks
- `outcomes.py`
  - provider-specific success messages
  - provider-specific terminal outcome messages
  - provider-specific live status messages
- `stream.py`
  - actual SDK streaming call
  - provider-specific error mapping

## Current Provider Shape

Vertex:
- public models:
  - `gemini-3.1-pro-preview`
  - `gemini-3-flash-preview`
  - `gemini-3.1-flash-lite-preview`
- preset config:
  - `none`
  - `low`
  - `normal`
  - `high`
- current preset knobs:
  - `thinking_config.thinking_level`
  - `thinking_config.include_thoughts`
  - `maxOutputTokens`

OpenAI:
- public models:
  - `gpt-5.4`
  - `gpt-5.4-mini`
  - `gpt-5.4-nano`
- preset config:
  - `none`
  - `low`
  - `normal`
  - `high`
  - `xhigh`
- current preset knobs:
  - `max_output_tokens`
  - `reasoning`
  - `text.verbosity`
  - `tool_choice`
  - `parallel_tool_calls`

Anthropic:
- public models:
  - `claude-opus-4-7`
  - `claude-sonnet-4-6`
  - `claude-haiku-4-5`
- preset config:
  - `none`
  - `low`
  - `normal`
  - `high`
  - `xhigh`
  - `max`
- current preset knobs:
  - `max_tokens`
  - `thinking`
  - `output_config.effort`

## Model and Tool Source Of Truth
- backend is the source of truth for public model and tool exposure
- `GET /api/v1/models` is the frontend source of truth
- the frontend must not hardcode model defaults, tool support, or provider-specific capabilities
- model order in the UI follows backend catalog order

## Change Points
- add/remove/reorder models:
  - `proxy-api/app/providers/<provider>/models.py`
  - `proxy-api/app/providers/<provider>/config.py`
- change tool exposure or display names:
  - `proxy-api/app/providers/<provider>/tools.py`
  - `proxy-api/app/providers/<provider>/models.py`
- change shared provider routing:
  - `proxy-api/app/providers/catalog.py`
  - `proxy-api/app/providers/dispatcher.py`
- change chat execution lifecycle:
  - `proxy-api/app/services/chat/stream.py`
  - `proxy-api/app/services/chat/turns.py`
  - `proxy-api/app/services/chat/provider_context.py`

## Active vs Inactive Areas
- active:
  - guest login
  - backend-owned Microsoft OAuth
  - session conflict handling
  - persisted chat histories
  - streaming chat with backend-owned execution
  - backend-owned model catalog
  - provider-native hosted tools
- scaffold-only:
  - usage logging models/services
