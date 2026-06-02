# Architecture

Current runtime and code ownership for `ai-proxy-poc`.

## Runtime Shape
- Public traffic enters sibling `root-proxy`
- `root-proxy` terminates TLS and routes `ai.example.com` to `ai-proxy-frontend:8080`
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
10. `New Chat` only resets local UI state; it does not create a backend row.
11. The frontend does not persist the selected history or draft in browser storage; on refresh it returns to the local welcome state until the user loads a history again.
12. On the first real send or first file upload without an active history, `ChatPage` creates a backend draft through `POST /api/v1/chat/drafts`.
13. File upload goes through `POST /api/v1/chat/files` with either a real `chat_history_id` or a `draft_chat_id`.
14. If the first file upload succeeds, the backend promotes that draft id into the persisted `chat_history.id` immediately and deletes the Redis draft.
15. Chat send goes through `frontend/src/chat/api/streamChatApi.ts` to `POST /api/v1/chat/completions` with either a real `chat_history_id` or a `draft_chat_id`.
16. If send preflight succeeds, the backend promotes that draft id into the persisted `chat_history.id` immediately before the first turn starts.
17. The frontend consumes SSE `start`, `delta`, `status`, `done`, and `error`.

## Backend Flow
1. `proxy-api/app/main.py`
   - starts FastAPI
   - verifies Redis
   - runs Alembic migrations
   - runs startup housekeeping
   - starts background housekeeping
2. `proxy-api/app/api/v1/api.py`
   - registers auth, models, and chat routers
3. `proxy-api/app/api/v1/endpoints/`
   - stays thin
   - owns HTTP shape only
4. `proxy-api/app/services/chat/completions/route_selection.py`
   - resolves `model_id` and `tool_ids`
5. `proxy-api/app/services/chat/completions/preflight.py`
   - validates the selected route
   - resolves owned chat histories or owned first-send drafts
   - enforces provider readiness and chat rate limits
6. `proxy-api/app/services/chat/completions/request_builder.py`
   - rebuilds provider context from persisted history
   - assembles the provider request
   - conditionally resolves exact input-token counts near the soft threshold
   - runs context compaction when needed
7. `proxy-api/app/services/chat/completions/turn_persistence.py`
   - persists user message and assistant placeholder
8. `proxy-api/app/services/chat/completions/provider_execution.py`
   - executes the provider stream
   - persists final success or failure outcomes
9. `proxy-api/app/services/chat/completions/orchestrator.py`
   - starts backend-owned provider execution
   - emits live SSE events if the browser is still connected
10. `proxy-api/app/providers/catalog.py`
   - builds the public model catalog
   - validates model/tool selections
11. `proxy-api/app/providers/dispatcher.py`
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
- session TTL: `6 hours`
- guest max active sessions: `2`
- Microsoft max active sessions: `4`
- session-limit strategy default: `reject`
- conflict ticket TTL default: `5 minutes`

Session expiry semantics:
- active sessions are kept alive by `last_seen_at`
- idle timeout is `last_seen_at + 6 hours`
- session-limit eviction also marks the older session as `expired`
- expired sessions are cleaned up by the background housekeeping loop
- Redis chat drafts that never become a persisted history expire by TTL and do not require database cleanup

## Data Ownership
- PostgreSQL is the system of record for:
  - users
  - auth sessions
  - OAuth transactions
  - conflict tickets
  - chat histories
  - chat messages
  - backend-owned attachment blobs in `stored_files`
  - logical history attachments in `chat_history_files`
  - provider attachment metadata in `stored_file_provider_states`
  - per-turn attachment snapshots in `chat_message_attachments`
  - active chat context checkpoints
  - remembered-chat summary placeholders
- Redis is used for:
  - one in-flight chat lease per conversation id, including first-send drafts
  - ephemeral first-send chat drafts
  - minute/hour chat rate limits
- provider-side conversation state is not treated as the source of truth

## Chat Persistence Model
- `POST /api/v1/chat/completions` creates a backend-owned turn only after backend preflight checks pass, any required context compaction succeeds, and provider dispatch is about to begin
- on the first send in a brand-new local conversation, the frontend creates a Redis-backed draft before calling `POST /api/v1/chat/completions`
- `POST /api/v1/chat/completions` accepts either an owned `chat_history_id` or an owned `draft_chat_id`
- if a draft-backed send passes backend preflight, the backend creates `chat_histories.id = draft_chat_id` immediately before persisting the turn
- backend persists:
  - user message
  - assistant placeholder
  - resolved route metadata
  - final success or error outcome
  - assistant usage JSON with normalized usage, provider raw usage, and price snapshot
  - history-level `usage_summary` rollup cache
- backend-local rejects such as validation failures, session locks, rate limits, and provider-readiness failures are not persisted as chat turns
- those backend-local rejects are instead audit-logged in `chat_request_rejections`
- if provider execution fails, the assistant message is kept renderable but marked `excluded_from_context=true`
- persisted provider-attempted failures keep provider-specific `result_code`, `result_message`, `finish_reason`, and safe `error_detail`
- future provider context is rebuilt from:
  - a checkpoint summary when one exists
  - persisted non-error messages after the checkpoint coverage boundary
  - the latest request user message

## Attachment Persistence Model
- attachments belong to a `chat_history`, not to an individual prompt textarea submit
- the frontend never stores attachment state outside the current in-memory render
- local file attach creates no durable client state; only backend responses define what exists
- `stored_files`
  - stores backend-owned file bytes in PostgreSQL
  - deduplicates identical file content per user by `sha256`
- `chat_history_files`
  - stores one logical attachment row per history
  - blocks same-history duplicate content by `UNIQUE(chat_history_id, stored_file_id)`
  - allows the same stored file to be referenced by different histories
  - stores whether each attachment is active for future prompt sends
- `stored_file_provider_states`
  - caches provider-specific token counts
  - caches provider-managed remote file refs after attach-time upload
  - OpenAI and Anthropic store provider file ids
  - Vertex stores private GCS `gs://...` object URIs
- `chat_message_attachments`
  - snapshots which attachments were present when a persisted turn reached provider dispatch
- file-first flow:
  - frontend creates a draft
  - backend validates the upload, counts tokens for supported providers, stores the blob, creates the persisted history using the draft id, and deletes the draft
- text-first flow:
  - frontend creates a draft only when the first send starts
  - backend promotes the draft to a persisted history immediately before the first persisted turn is created
- provider-managed files are not the source of truth
  - OpenAI and Anthropic `file_id` values are disposable execution refs
  - deleting a provider file does not delete the logical attachment if the PostgreSQL row still exists
- provider uploads happen at attach time and are recreated at send time if housekeeping removed or reconciled away the remote copy
- only active history attachments are injected into future provider requests
- provider-side remote attachment copies are reconciled by housekeeping; missing provider refs become `not_uploaded` while DB-owned blobs remain the source of truth
- provider-side remote attachment copies are deleted after `CHAT_ATTACHMENT_REMOTE_TTL_HOURS` without use while DB-owned blobs remain the source of truth
- attachment token limits are separate from text compaction
  - text compaction remains text-only
  - attachments are rejected if their provider-specific total exceeds the configured attachment token limit
- current supported attachment types:
  - `application/pdf`
  - `image/png`
  - `image/jpeg`
- current provider support:
  - OpenAI: supported
  - Anthropic: supported
  - Vertex: supported through private GCS `fileData` refs

## Frontend Refresh Semantics
- the frontend does not persist the active conversation in `localStorage` or `sessionStorage`
- refresh always returns to the local welcome state
- if an SSE response is interrupted by refresh, the browser stops rendering live output immediately
- the frontend does not attempt hidden restore or replay
- later history rendering comes only from explicit backend reads after the message or attachment has been persisted

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

## Context Compaction
- context compaction is backend-owned
- soft compaction threshold: `50000` estimated input tokens
- exact input-token count is attempted from `40000` estimated input tokens upward
- compression currently uses an internal Vertex AI pipeline with `gemini-3-flash-preview`
- chat history rendering still uses raw `chat_messages`
- checkpoint summaries are inference-only and live in a dedicated table

## Provider Layer

Shared provider layer:
- `proxy-api/app/providers/types.py`
- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/dispatcher.py`

## Generic Model Defaults
- backend-owned generic helper work stays pinned to these lighter tiers unless a call site explicitly overrides it:
  - Vertex: `gemini-3-flash-preview`
  - OpenAI: `gpt-5.4-mini`
  - Anthropic: `claude-haiku-4-5`
- current uses:
  - internal context compression uses the Vertex generic model
  - attachment token counting uses the OpenAI and Anthropic generic models

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
- `usage.py`
  - provider usage normalization
  - provider-side price estimation
- `count_tokens.py`
  - provider-native exact input token counting
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
  - `proxy-api/app/services/chat/completions/orchestrator.py`
  - `proxy-api/app/services/chat/completions/preflight.py`
  - `proxy-api/app/services/chat/completions/request_builder.py`
  - `proxy-api/app/services/chat/completions/provider_execution.py`
  - `proxy-api/app/services/chat/completions/turn_persistence.py`
  - `proxy-api/app/services/chat/histories/usage_summary.py`

## Active vs Inactive Areas
- active:
  - guest login
  - backend-owned Microsoft OAuth
  - session conflict handling
  - persisted chat histories
  - streaming chat with backend-owned execution
  - backend-owned model catalog
  - provider-native hosted tools
