# API

Current HTTP surface exposed by frontend NGINX and backend FastAPI.

## Base
- Public host: `https://ai.example.com`
- API prefix: `/api/v1`
- Auth: backend-owned session cookie only
- Main cookies:
  - `session_id`
  - `session_conflict_id`
- session lifetime:
  - one rolling backend-owned `expires_at`
  - TTL: `AUTH_SESSION_TTL_MINUTES`
  - idle expiry is determined from `last_seen_at`
  - session-limit eviction also moves the older session into `expired`

## Public Routes
- `GET /health`
  - backend health probe
  - when `DEPLOYMENT_SMOKE_REQUIRED=true`, this probe runs the deployment smoke check until it passes
  - Docker keeps `backend` unhealthy, and therefore keeps `frontend` from starting, until this returns `200`
  - deployment smoke bypasses public auth/session/chat routes, so this probe does not create user/session/chat records
- `GET /api/v1/models`
  - returns the backend-owned public model catalog
  - frontend model/tool selector must use this as source of truth

## Auth Routes
- `GET /api/v1/auth/me`
  - returns current session or a structured auth issue response
- `POST /api/v1/auth/login/guest`
  - creates or reuses a guest user and issues a session cookie
- `GET /api/v1/auth/login/microsoft`
  - starts backend-owned Microsoft OAuth redirect flow
- `GET /api/v1/auth/callback/microsoft`
  - finishes Microsoft OAuth flow and issues a local session cookie
- `POST /api/v1/auth/session-conflicts/resolve`
  - resolves session-limit conflicts by evicting the oldest active session
- `POST /api/v1/auth/logout`
  - clears the current session and conflict cookies

## Chat Routes
- `GET /api/v1/chat/histories`
  - authenticated
  - lists current user's chat histories
- `POST /api/v1/chat/completions`
  - accepts the latest user input as scalar `prompt`
  - persisted chat history is loaded and assembled by the backend
  - `tool_ids`, `model_id`, and `chat_history_id` remain optional request selections
- `GET /api/v1/chat/histories/{history_id}`
  - authenticated
  - returns one history plus persisted messages
  - assistant messages include backend-merged completed thinking/tool blocks from `chat_message_blocks`
- `PATCH /api/v1/chat/histories/{history_id}/title`
  - authenticated
  - updates one owned history title
- `PUT /api/v1/chat/histories/{history_id}/pin`
  - authenticated
  - pins one owned history at the end of the pinned section
- `DELETE /api/v1/chat/histories/{history_id}/pin`
  - authenticated
  - removes one owned history from the pinned section
- `DELETE /api/v1/chat/histories/{history_id}`
  - authenticated
  - deletes one owned history
- `POST /api/v1/chat/completions`
  - authenticated
  - requires capability `chat:send`
  - returns `text/event-stream`
- `POST /api/v1/chat/files`
  - authenticated
  - uploads one file to an owned `chat_history_id`, or no id for the blank-page attachment flow
  - when no id is sent, the backend uses an internal Postgres draft while validation/counting/storage runs, promotes it to a persisted chat history on success, and returns that history with the uploaded file list
  - failed blank-page validation/counting/storage removes the internal draft and any staged file rows before returning the error
  - mutation timeout uses `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`
- `PATCH /api/v1/chat/histories/{history_id}/files/{file_id}`
  - authenticated
  - updates one owned history attachment activation state
- `GET /api/v1/chat/histories/{history_id}/files/{file_id}/content`
  - authenticated
  - returns one owned history attachment for inline preview
- `DELETE /api/v1/chat/histories/{history_id}/files/{file_id}`
  - authenticated
  - deletes one owned history attachment
  - deletes the empty history when the last file is removed from a file-only history

## Chat Request Contract

`POST /api/v1/chat/completions` request body:

- `chat_history_id`
  - optional
  - must reference an existing owned chat history when present
  - if omitted, backend creates a new chat history for the send
- `model_id`
  - required
  - must match an available model from `GET /api/v1/models`
- `tool_ids`
  - optional
  - each tool must be exposed by the selected model
- `prompt`
  - required
  - contains only the latest user input
  - blank input and input over the configured token limit are rejected
- backend rebuilds all earlier context from backend-owned storage

Important:
- the latest prompt has its own hard text-token limit
- when `chat_history_id` is present, backend rebuilds provider context from persisted non-error messages and treats `prompt` as the new turn
- instructions, persisted text context, and the latest prompt share the text-compaction budget
- attachments use an independent per-history/provider token limit and do not trigger text compaction
- local validation or coordination rejects do not create a persisted turn
- on the first text-only send from a brand-new local conversation, the frontend calls `POST /api/v1/chat/completions` with neither id
- once a chat turn is created, provider execution continues in the backend even if the browser SSE connection closes

## Chat History Metadata

- chat history auto-titles are normalized and capped by `GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS`
- manually renamed titles are capped by `CHAT_HISTORY_TITLE_MAX_CHARS`
- frontend display truncation is a presentation concern; backend stores the title text
- chat history list order is:
  - pinned histories first by `pin_order ASC`
  - unpinned histories after that by `COALESCE(last_message_at, created_at) DESC`
- `updated_at` may change for metadata edits such as rename or pin state changes, but it is not the list-order source of truth

## SSE Events

`POST /api/v1/chat/completions` emits these event types:

- `start`
  - includes:
    - `model`
    - `provider`
    - `chat_history_id`
    - `user_message_id`
    - `assistant_message_id`
- `delta`
  - includes:
    - `delta_text`
  - contains only ordinary final-answer text
- `block`
  - thinking block includes:
    - `type: "thinking"`
    - `operation: "start" | "delta" | "end"`
    - stable `block_id` within the response stream
    - readable provider-authored `text_delta`
    - provider/event correlation `metadata`
  - tool block includes:
    - `operation: "start" | "delta" | "end"`
    - stable `block_id` within the response stream
    - `type: "tool"`
    - provider/event correlation `metadata`
    - `raw`, one complete JSON-compatible provider event or chunk without tool-specific projection
- `status`
  - includes:
    - `provider`
    - `status_code`
    - `status_message`
  - may appear before `start` for backend-owned internal pipeline steps such as context compaction
- `done`
  - includes:
    - `model`
    - `provider`
    - `result_code`
    - `result_message`
    - `finish_reason`
    - `usage`
- `error`
  - includes:
    - `result_code`
    - `result_message`
    - `retry_after_seconds`
    - `detail`

Notes:
- thinking blocks never contain signatures, encrypted reasoning, tool arguments, or answer text
- tool blocks are classified structurally and keep provider-native JSON instead of mapping each tool schema
- related tool block events share `block_id`
- live `block` events are still sent as SSE chunks for first-time rendering
- the backend also merges related block chunks by `block_id` and persists one `chat_message_blocks` row only when that block reaches `operation="end"`
- persisted block rows are not replayed over the active SSE stream; they are returned by `GET /api/v1/chat/histories/{history_id}`
- `status_code` values are provider-specific progress codes
- internal proxy status codes may also appear, including:
  - `context_text_tokens_estimated`
  - `context_text_tokens_exact`
  - `context_compaction_started`
- `result_code` values are provider-specific terminal outcome codes
- `detail` is currently part of the product error contract and can include provider-aware diagnostic text
- user/operator formatting for provider details is tracked separately in `docs/TO-DO.md`

Current internal pre-provider status semantics:
- `context_text_tokens_estimated`
  - emitted before provider execution
  - uses the backend heuristic for instructions, persisted text, and the latest prompt
- `context_text_tokens_exact`
  - emitted only when the backend called the provider-native count-tokens API
  - excludes tools and attachments from the count payload
- `context_compaction_started`
  - emitted when the request is still above threshold and the backend starts checkpoint compression
  - includes the token count that triggered compaction in the message text

## Status Codes
- `400`
  - request fails business-rule validation before a turn starts
- `401`
  - no valid session
- `403`
  - missing capability
- `404`
  - missing or unowned `chat_history_id`
- `409`
  - auth session conflict or chat operation already in progress
- `504`
  - validation, attachment mutation, or provider liveness timeout
- `422`
  - schema validation failure

After a chat turn starts, execution failures are emitted as SSE `error` events and also persisted on the assistant message row. Rejects that happen before provider dispatch are returned as normal HTTP errors and are not persisted.

Persisted assistant failures keep:
- `result_code`
- `result_message`
- `finish_reason`
- `error_detail`
- `provider`
- `model_id`
- any completed thinking/tool blocks that reached `operation="end"` before the failure

Usage and pricing are not stored on `chat_messages`; use `usage_ledger_events`
for spend and token audit.

## Persisted Message Blocks

`GET /api/v1/chat/histories/{history_id}` returns `blocks` on every message.
User messages normally have an empty list. Assistant messages contain completed
thinking/tool blocks in backend order.

Each block includes:

- `type`: `thinking` or `tool`
- `sequence`
- `block_id`: provider-neutral stable block identity from the live stream
- `text`: merged readable thinking text for thinking blocks, empty for tool blocks
- `metadata`: latest provider-neutral block metadata
- `raw_events`: merged provider-native raw events for tool blocks, empty for thinking blocks
- `started_at`
- `completed_at`

Assistant messages also include:

- `block_activity_started_at`: earliest persisted block start time
- `block_activity_completed_at`: latest persisted block completion time
- `block_activity_duration_ms`: elapsed persisted block activity duration

## Public Model Surface

`GET /api/v1/models` is the runtime source of truth. Model ids, availability,
tool exposure, helper model ids, and price cards are declared in each provider's
`config.py`; they are intentionally not duplicated in this document.

## Public Tool Surface

Provider notes:
- Vertex `retrieval` is Vertex RAG Engine backed by `retrieval.vertex_rag_store`
- tool display names are formatted from provider ids, for example `google_search` becomes `Google Search`
- actual tool availability is model-specific and must be read from `GET /api/v1/models`
