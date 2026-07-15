# Architecture

Current runtime and code ownership for AI Proxy.

## Runtime Shape
- Public traffic enters sibling `root-proxy`
- `root-proxy` terminates TLS and routes `ai.example.com` to `ai-proxy:8080`
- `frontend` serves the SPA and proxies `/api/*` and `/health` to `backend:8000`
- `backend` service uses PostgreSQL, Redis, Vertex AI, OpenAI, and Anthropic
- runtime is Docker Compose first; backend should not depend on host-local services
- optional deployment smoke gating keeps `backend` unhealthy until smoke passes, so `frontend` does not start

## Public Edge Trust Boundary
- server deployment assumes sibling `root-proxy` is the only public HTTP entrypoint
- `root-proxy/nginx/conf.d/snippets/proxy-common.conf` overwrites client-supplied forwarding headers:
  - `X-Real-IP` from `$remote_addr`
  - `X-Forwarded-For` from `$remote_addr`
  - `X-Forwarded-Host` from `$host`
  - `X-Forwarded-Port` from `$server_port`
  - `X-Forwarded-Proto` from `$scheme`
- `frontend/nginx/default.conf` forwards those sanitized headers to the backend
- backend IP-based guest identity and Microsoft redirect URI construction rely on that edge sanitization
- do not publish `frontend` or `backend` directly on the public Internet unless forwarded headers are overwritten by the new public edge

## Top-Level Components
- `frontend/`
  - React + Vite SPA packaged behind NGINX
- `backend/`
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
11. The frontend does not persist the selected history in browser storage; on refresh it returns to the local welcome state until the user loads a history again.
12. On the first file upload without an active history, `POST /api/v1/chat/files` uses an internal Postgres draft during validation/counting/storage and promotes it to a visible chat history before returning success.
13. File upload goes through `POST /api/v1/chat/files` with a real `chat_history_id`, or neither id for the blank-page attachment flow.
14. A text-only first send goes directly to `POST /api/v1/chat/completions` with neither id.
15. Chat send goes through `frontend/src/chat/api/streamChatApi.ts` to `POST /api/v1/chat/completions` with an optional `chat_history_id`.
16. The frontend consumes SSE `start`, `block`, `delta`, `status`, `done`, and `error`.
17. `block` is either a readable thinking block or a provider-native tool event fragment with stable block identity; ordinary answer text remains `delta`.

## Backend Flow
1. `backend/app/main.py`
   - starts FastAPI
   - verifies Redis
   - runs Alembic migrations
   - runs startup housekeeping
   - starts background housekeeping
2. `backend/app/api/v1/api.py`
   - registers auth, models, and chat routers
3. `backend/app/api/v1/endpoints/`
   - stays thin
   - owns HTTP shape only
4. `backend/app/services/chat/completions/route_selection.py`
   - resolves `model_id` and `tool_ids`
5. `backend/app/services/chat/operations.py`
   - starts token-fenced operations on chat histories and internal blank-upload staging drafts
   - stores validation/provider deadlines in Postgres
   - rejects late commits when the owner token no longer matches
6. `backend/app/services/chat/completions/validation.py`
   - validates the selected route
   - enforces provider readiness, usage caps, and chat rate limits
7. `backend/app/services/chat/completions/request_builder.py`
   - rebuilds provider context from persisted history
   - assembles the provider request
   - conditionally resolves exact input-token counts near the soft threshold
   - runs context compaction when needed
8. `backend/app/services/chat/completions/turn_persistence.py`
   - persists user message and assistant placeholder
9. `backend/app/services/chat/completions/provider_execution.py`
   - executes the provider stream
   - persists final success or failure outcomes
10. `backend/app/services/chat/completions/orchestrator.py`
   - starts backend-owned provider execution
   - emits live SSE events if the browser is still connected
11. `backend/app/providers/catalog.py`
   - builds the public model catalog
   - validates model/tool selections
12. `backend/app/providers/dispatcher.py`
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

Important runtime values from `.env`:
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
- Interrupted internal upload staging drafts are deleted by housekeeping after `CHAT_DRAFT_TTL_SECONDS`

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
  - internal blank-page upload staging drafts in `chat_drafts` while upload validation/counting/storage is in progress
  - token-fenced chat operations in `chat_operations`
  - legacy remembered-chat summary rows in `chat_history_memories`; current runtime uses `chat_context_checkpoints`
  - unified operator events in `operator_events`
  - append-only usage ledger rows in `usage_ledger_events`
  - user usage cap overrides and reset baselines in `user_usage_caps`
- Redis is used for:
  - minute/hour chat rate limits
- provider-side conversation state is not treated as the source of truth

## Chat Persistence Model
- `POST /api/v1/chat/completions` starts a token-fenced `chat_operations` row before validation
- text-only first sends create a `chat_histories` row at send time and use that row as the operation scope
- `POST /api/v1/chat/completions` accepts an owned `chat_history_id` or neither id
- blank-page file upload starts an internal draft-scoped operation, validates/counts/stores the file, creates `chat_histories.id = chat_drafts.id`, copies draft file rows into `chat_history_files`, deletes the staging draft/file rows, and returns the persisted history
- failed blank-page upload validation/counting/storage deletes the internal draft and any staged file rows before returning the error
- backend persists:
  - user message
  - assistant placeholder
  - resolved route metadata
  - final success or error outcome
  - append-only usage ledger events with normalized usage, provider raw usage, and price snapshot
- backend-local rejects such as validation failures, active operation conflicts, usage caps, rate limits, and provider-readiness failures are not persisted as chat turns
- those backend-local rejects are audit-logged in `operator_events`
- local validation, request preparation, compaction, and attachment preparation must complete before `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`
- provider execution uses `CHAT_PROVIDER_EVENT_IDLE_TIMEOUT_SECONDS` as the next-event idle timeout and `CHAT_PROVIDER_MAX_RUNTIME_SECONDS` as a hard cap
- the assistant placeholder stores the current operation `deadline_at`; provider event arrival stores `first_response_at` once and refreshes the next-event deadline on the first event, provider-state transitions, and throttled heartbeat intervals
- if a deadline is exceeded, the backend marks the assistant row `status='error'`, clears `deadline_at`, excludes the turn from future context, clears the active operation token, and writes an `operator_events` timeout row
- if provider output arrives after timeout handling, it is not authoritative because the operation token no longer matches
- if provider execution fails, the assistant message is kept renderable but marked `excluded_from_context=true`
- persisted provider-attempted failures keep provider-specific `result_code`, `result_message`, `finish_reason`, and safe `error_detail`
- future provider context is rebuilt from:
  - a checkpoint summary when one exists
  - persisted non-error messages after the checkpoint coverage boundary
  - the latest request user message

Current operation states:
- live states: `running`, `provider_streaming`
- terminal states: `succeeded`, `failed`, `timed_out`
- each operation has exactly one scope: `chat_history_id` or `draft_id`
- draft-scoped operations are only used for blank-page `attach_file`
- PostgreSQL partial unique indexes enforce one live operation per history, one live operation per draft, and one live draft-attach operation per auth session

Crash and housekeeping semantics:
- normal mutation flow commits the product mutation, then marks the operation terminal
- a process crash after a file attach/delete/toggle commit but before terminal operation update can leave the visible mutation applied while the operation still looks live
- startup/hourly housekeeping closes expired live operations as `timed_out`, clears owner active-operation fields, and writes an operator event when the operation row still exists
- housekeeping does not roll back already-committed product mutations; recovery is best-effort plus operator visibility
- deleting a whole history, or deleting the last file from an empty file-only history, deletes the history row and cascades the operation row; after that there may be no operation row left for housekeeping to close
- chat send transitions the operation to `provider_streaming` before persisting the user/assistant rows; a crash in that small gap leaves an operation without message rows, and housekeeping can time out the operation and clear the active token
- stale empty history cleanup assumes `HOUSEKEEPING_INTERVAL_MINUTES` remains greater than `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`; if that invariant changes, add an active-operation guard before deleting empty histories

## Attachment Persistence Model
- persisted attachments belong to a `chat_history`; blank-page uploads use a `chat_draft` only as internal staging before the upload response is returned
- the frontend never stores attachment state outside the current in-memory render
- local file attach creates no durable client state; only backend responses define what exists
- `stored_files`
  - stores backend-owned file bytes in PostgreSQL
  - deduplicates identical file content per user by `sha256`
  - uses `lifecycle_state` values `active`, `pending_delete`, and `delete_failed` to track physical cleanup state
- `chat_history_files`
  - stores one logical attachment row per history
  - blocks same-history duplicate content by `UNIQUE(chat_history_id, stored_file_id)`
  - allows the same stored file to be referenced by different histories
  - stores whether each attachment is active for future prompt sends
- `chat_draft_files`
  - stores logical attachment rows only while blank-page upload validation/counting/storage is in progress
  - uses the same file ids when the upload is promoted into `chat_history_files`
- `stored_file_provider_states`
  - caches provider-specific token counts
  - caches provider-managed remote file refs after attach-time upload
  - OpenAI and Anthropic store provider file ids
  - Vertex stores private GCS `gs://...` object URIs
- `chat_message_attachments`
  - snapshots which attachments were present when a persisted turn reached provider dispatch
- file-first flow:
  - frontend sends `POST /api/v1/chat/files` with no id
  - backend creates a `chat_drafts` row, validates the upload, counts tokens for supported providers, stores the blob, creates `chat_draft_files`, promotes the draft to `chat_histories`, deletes the staging draft rows, and returns the visible history
- attachment operations use `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS` and the same DB operation-token fence as chat sends
- text-first flow:
  - frontend sends `POST /api/v1/chat/completions` with no id
  - backend creates a persisted history and starts a send operation immediately
- provider-managed files are not the source of truth
  - OpenAI and Anthropic `file_id` values are disposable execution refs
  - deleting a provider file does not delete the logical attachment if the PostgreSQL row still exists
- provider uploads happen at attach time and are recreated at send time if the stored remote id is missing or the remote copy was deleted out of band
- only active history attachments are injected into future provider requests
- provider-side remote attachment copies are reconciled by housekeeping; send-time also verifies stored remote ids and recreates missing remote copies while DB-owned blobs remain the source of truth
- provider-side remote attachment copies are deleted after `CHAT_ATTACHMENT_REMOTE_TTL_HOURS` without use while DB-owned blobs remain the source of truth
- when the last logical attachment reference is removed, the blob moves to `pending_delete`; remote delete failures move it to `delete_failed` with retry metadata, and housekeeping retries due rows with backoff
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

## Operational Data Model
- `operator_events`
  - single operator-facing event log for request rejects, usage cap rejects, provider turn failures, stale execution cleanup, and attachment cleanup failures
- `user_usage_caps`
  - optional per-user cap override
  - `baseline_estimated_price_usd` is moved forward by `reset-cap`, so operators can unlock a user without cron/time-window logic
- `usage_ledger_events`
  - append-only spend/audit ledger
  - successful assistant turns append a `billable` row with user, session, provider, model, token, raw-usage, and price snapshots
  - ledger rows intentionally snapshot chat ids instead of depending on deletable chat-history rows
- default cap is `USAGE_DEFAULT_CAP_USD` when a user has no row in `user_usage_caps`
- enforcement uses `usage_ledger_events.total_cost_usd`, not deletable chat transcript rows
- usage caps are intentionally post-paid: the backend checks current ledger spend before dispatch and records actual estimated spend after successful provider/compression work

## Deployment Smoke Readiness
- `/health` is the Docker startup gate
- when `DEPLOYMENT_SMOKE_REQUIRED=true`, `/health` runs deployment smoke until it passes, caches that pass in process memory, and then becomes lightweight
- because `frontend` depends on `backend: service_healthy`, public traffic does not reach the product until smoke passes
- the smoke code lives in `backend/app/deployment_smoke/`
- it bypasses public auth/session/chat routes and does not create product users, sessions, histories, messages, stored files, or operator-event rows
- `python -m app.deployment_smoke` manually exercises one direct text request per exposed provider plus direct provider/GCS attachment upload-delete checks
- current deployment expects Vertex AI, OpenAI, and Anthropic to be configured and ready
- attach-time file preparation also expects all three providers to be usable; one provider outage can block file upload by design

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
- compression does not set a backend output-token cap; the summary size is controlled by the compression instruction target
- chat history rendering still uses raw `chat_messages`
- checkpoint summaries are inference-only and live in a dedicated table

## Provider Layer

Shared provider layer:
- `backend/app/providers/types.py`
- `backend/app/providers/catalog.py`
- `backend/app/providers/dispatcher.py`

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
  - stateful provider chunks to shared answer, thinking-block, and raw tool-block events
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
  - stream-lifetime validation that a terminal response and visible final answer were received

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
  - `backend/app/providers/<provider>/models.py`
  - `backend/app/providers/<provider>/config.py`
- change tool exposure or display names:
  - `backend/app/providers/<provider>/tools.py`
  - `backend/app/providers/<provider>/models.py`
- change shared provider routing:
  - `backend/app/providers/catalog.py`
  - `backend/app/providers/dispatcher.py`
- change chat execution lifecycle:
  - `backend/app/services/chat/completions/orchestrator.py`
  - `backend/app/services/chat/completions/validation.py`
  - `backend/app/services/chat/completions/request_builder.py`
  - `backend/app/services/chat/completions/provider_execution.py`
  - `backend/app/services/chat/completions/turn_persistence.py`
  - `backend/app/services/chat/operations.py`
  - `backend/app/workers/chat_execution_cleanup.py`

## Active vs Inactive Areas
- active:
  - guest login
  - backend-owned Microsoft OAuth
  - session conflict handling
  - persisted chat histories
  - streaming chat with backend-owned execution
  - backend-owned model catalog
  - provider-native hosted tools
  - context checkpoints in `chat_context_checkpoints`
  - usage ledger in `usage_ledger_events`
- inactive or legacy:
  - `chat_history_memories` model/table remains present, but current runtime compaction uses `chat_context_checkpoints`
