# API

Current HTTP surface exposed by frontend NGINX and backend FastAPI.

## Base
- Public host: `https://ai.nextinsol.com`
- API prefix: `/api/v1`
- Auth: backend-owned session cookie only
- Main cookies:
  - `session_id`
  - `session_conflict_id`

## Public Routes
- `GET /health`
  - backend health probe
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
- `POST /api/v1/chat/histories`
  - authenticated
  - creates an empty history
- `GET /api/v1/chat/histories/{history_id}`
  - authenticated
  - returns one history plus persisted messages
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

## Chat Request Contract

`POST /api/v1/chat/completions` request body:

- `chat_history_id`
  - optional
  - if absent, backend creates a new history
- `model_id`
  - required
  - must match an available model from `GET /api/v1/models`
- `tool_ids`
  - optional
  - each tool must be exposed by the selected model
- `messages`
  - required
  - at least one `user` message is required
  - last message must be `user`
  - backend validates request shape, message count, tool count, and message content length

Important:
- those validation limits are request-schema limits, not provider token-window limits
- when `chat_history_id` is present, backend rebuilds provider context from persisted non-error messages and treats the request's last user message as the new turn
- local validation or coordination rejects do not create a persisted turn
- once a chat turn is created, provider execution continues in the backend even if the browser SSE connection closes

## Chat History Metadata

- chat history auto-titles are normalized from the first prompt and stored up to `80` characters without backend-added ellipsis
- manually renamed titles are stored up to `255` characters
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
- `status`
  - includes:
    - `provider`
    - `status_code`
    - `status_message`
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
- `status_code` values are provider-specific progress codes
- `result_code` values are provider-specific terminal outcome codes
- `detail` is a user-safe provider-aware detail string, not a raw SDK exception dump

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
  - auth session conflict
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
- `usage`

## Public Model Surface

Current public model ids:

- Vertex:
  - `gemini-3.1-pro-preview`
  - `gemini-3-flash-preview`
  - `gemini-3.1-flash-lite-preview`
- OpenAI:
  - `gpt-5.4`
  - `gpt-5.4-mini`
  - `gpt-5.4-nano`
- Anthropic:
  - `claude-opus-4-7`
  - `claude-sonnet-4-6`
  - `claude-haiku-4-5`

Notes:
- `claude-opus-4-7` is intentionally exposed as unavailable
- final availability and tool exposure come from backend provider model definitions, not the frontend

## Public Tool Surface

Current backend-owned public tool ids:

- `web_search`
- `retrieval`
- `code_execution`
- `url_context`

Provider notes:
- Vertex can expose all four tool ids
- OpenAI exposes `web_search`, `retrieval`, and `code_execution`
- Anthropic exposes `web_search` and `code_execution`
- actual tool availability is model-specific and must be read from `GET /api/v1/models`
