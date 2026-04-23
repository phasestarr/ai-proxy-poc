# API

Active HTTP surface exposed through frontend NGINX and reached through sibling `root-proxy`.

## Base
- Public host: `https://ai.nextinsol.com`
- API prefix: `/api/v1`
- Auth: browser session cookie only
- Cookie name: `session_id`
- Session conflict cookie: `session_conflict_id`

## Routes

### `GET /health`

```json
{
  "status": "ok",
  "service": "proxy-api"
}
```

### `GET /api/v1/models`

Returns the backend-owned public model catalog.

Example:

```json
{
  "data": [
    {
      "id": "gemini-3.1-pro-preview",
      "provider": "vertex_ai",
      "display_name": "Gemini 3.1 Pro Preview",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Google Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "Vertex RAG",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Execution",
          "available": true
        },
        {
          "id": "url_context",
          "display_name": "URL Context",
          "available": true
        }
      ]
    },
    {
      "id": "gemini-3-flash-preview",
      "provider": "vertex_ai",
      "display_name": "Gemini 3 Flash Preview",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Google Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "Vertex RAG",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Execution",
          "available": true
        },
        {
          "id": "url_context",
          "display_name": "URL Context",
          "available": true
        }
      ]
    },
    {
      "id": "gemini-2.5-flash",
      "provider": "vertex_ai",
      "display_name": "Gemini 2.5 Flash",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Google Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "Vertex RAG",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Execution",
          "available": true
        },
        {
          "id": "url_context",
          "display_name": "URL Context",
          "available": true
        }
      ]
    },
    {
      "id": "gpt-5.4",
      "provider": "openai",
      "display_name": "GPT 5.4",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Web Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "File Search",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Interpreter",
          "available": true
        }
      ]
    },
    {
      "id": "gpt-5.4-mini",
      "provider": "openai",
      "display_name": "GPT 5.4 Mini",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Web Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "File Search",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Interpreter",
          "available": true
        }
      ]
    },
    {
      "id": "gpt-5-mini",
      "provider": "openai",
      "display_name": "GPT 5 Mini",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Web Search",
          "available": true
        },
        {
          "id": "retrieval",
          "display_name": "File Search",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Interpreter",
          "available": true
        }
      ]
    },
    {
      "id": "claude-opus-4-7",
      "provider": "anthropic",
      "display_name": "Claude Opus 4.7",
      "available": false,
      "tools": []
    },
    {
      "id": "claude-sonnet-4-6",
      "provider": "anthropic",
      "display_name": "Claude Sonnet 4.6",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Web Search",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Execution",
          "available": true
        }
      ]
    },
    {
      "id": "claude-haiku-4-5",
      "provider": "anthropic",
      "display_name": "Claude Haiku 4.5",
      "available": true,
      "tools": [
        {
          "id": "web_search",
          "display_name": "Web Search",
          "available": true
        },
        {
          "id": "code_execution",
          "display_name": "Code Execution",
          "available": true
        }
      ]
    }
  ]
}
```

### `GET /api/v1/auth/me`
- `200`: authenticated session
- `401`: no valid session

Authenticated example:

```json
{
  "authenticated": true,
  "session": {
    "user_id": "9e4df8f0-2f2b-4df0-bac5-76fdd8adf3d6",
    "auth_type": "guest",
    "display_name": "172.18.0.1",
    "email": null,
    "capabilities": ["chat:send"],
    "persistent": false,
    "idle_expires_at": "2026-04-03T08:30:00Z",
    "absolute_expires_at": "2026-04-04T02:30:00Z"
  }
}
```

Anonymous example:

```json
{
  "authenticated": false,
  "reason": "missing_session",
  "detail": "Sign in again to continue.",
  "action": "login",
  "redirect_to": "/",
  "login_required": true,
  "can_evict_oldest": false,
  "auth_type": null,
  "session_limit": null
}
```

Session conflict example:

```json
{
  "authenticated": false,
  "reason": "session_limit_reached",
  "detail": "guest session limit reached (2).",
  "action": "session_conflict",
  "redirect_to": "/",
  "login_required": true,
  "can_evict_oldest": true,
  "auth_type": "guest",
  "session_limit": 2
}
```

### `POST /api/v1/auth/login/guest`
- Creates or reuses the guest user for the request IP and issues a session
- Sets the `session_id` cookie
- Default guest session limit is `2`

### `GET /api/v1/auth/login/microsoft`
- Starts a backend-owned Microsoft OAuth authorization-code redirect
- Accepts optional query `return_to=/some/path`
- Responds with `302` to Microsoft or back to the SPA with `auth_error`

### `GET /api/v1/auth/callback/microsoft`
- Handles the Microsoft OAuth callback
- Exchanges the authorization code on the backend
- Creates or reuses a local human user
- Sets the local `session_id` cookie
- If the Microsoft user is already at the session limit, sets a short-lived `session_conflict_id` cookie and redirects back to the SPA so the common session-conflict UI can resolve it.

### `POST /api/v1/auth/session-conflicts/resolve`
- Resolves a session conflict by evicting the current oldest active session for that user/auth type
- Uses either the stale `session_id` cookie or the short-lived `session_conflict_id` cookie
- Sets a fresh `session_id` cookie
- Returns the authenticated session envelope

Request:

```json
{
  "resolution": "evict_oldest",
  "auth_type": "guest"
}
```

Response:

```json
{
  "authenticated": true,
  "session": {
    "user_id": "9e4df8f0-2f2b-4df0-bac5-76fdd8adf3d6",
    "auth_type": "guest",
    "display_name": "172.18.0.1",
    "email": null,
    "capabilities": ["chat:send"],
    "persistent": false,
    "idle_expires_at": "2026-04-03T08:30:00Z",
    "absolute_expires_at": "2026-04-04T02:30:00Z"
  }
}
```

### `POST /api/v1/auth/logout`
- Deletes the current session and clears the cookie
- Also clears any `session_conflict_id` cookie
- Returns `204`

### `GET /api/v1/chat/histories`
- Protected endpoint
- Returns the current user's chat history summaries

```json
{
  "histories": [
    {
      "id": "6aa8a9a4-3ef2-4f3c-a3f4-1b63a7d063aa",
      "title": "Summarize the deployment path.",
      "created_at": "2026-04-20T01:00:00Z",
      "updated_at": "2026-04-20T01:01:00Z",
      "last_message_at": "2026-04-20T01:01:00Z",
      "message_count": 2
    }
  ]
}
```

### `POST /api/v1/chat/histories`
- Protected endpoint
- Creates an empty chat history
- Normal chat sends do not need this; `/chat/completions` auto-creates a history when `chat_history_id` is absent

Request:

```json
{
  "title": "New investigation"
}
```

### `GET /api/v1/chat/histories/{history_id}`
- Protected endpoint
- Returns one history plus persisted messages
- Only histories owned by the current user are visible

### `DELETE /api/v1/chat/histories/{history_id}`
- Protected endpoint
- Deletes one history owned by the current user
- `chat_messages` are deleted by FK cascade
- Returns `204`

### `POST /api/v1/chat/completions`
- Protected endpoint
- Requires capability `chat:send`
- Request body:

```json
{
  "chat_history_id": "6aa8a9a4-3ef2-4f3c-a3f4-1b63a7d063aa",
  "model_id": "gemini-2.5-flash",
  "tool_ids": ["web_search", "retrieval"],
  "messages": [
    {
      "role": "system",
      "content": "Answer tersely."
    },
    {
      "role": "user",
      "content": "Summarize the deployment path."
    }
  ]
}
```

Rules:
- `model_id` is required at request time
- `chat_history_id` is optional; if omitted, the backend creates a new chat history
- `tool_ids` is optional
- at least one `user` message is required
- the last message must be a `user` message
- when `chat_history_id` is present, the backend rebuilds provider context from stored non-error messages and treats the request's last user message as the new turn
- after a turn is created, the backend owns provider execution and persists the final success or error outcome even if the browser SSE connection closes

Response type:
- `text/event-stream`

Events:

```text
event: start
data: {"model":"gemini-2.5-flash","provider":"vertex_ai","chat_history_id":"6aa8a9a4-3ef2-4f3c-a3f4-1b63a7d063aa","user_message_id":"7b28a7e8-64f7-4df8-b120-8fd64ef74040","assistant_message_id":"e5b92fa8-5c7f-41b6-93c2-9b63578614ee"}
```

```text
event: delta
data: {"delta_text":"partial output"}
```

```text
event: done
data: {"model":"gemini-2.5-flash","provider":"vertex_ai","result_code":"success","result_message":"Response ready.","finish_reason":"STOP","usage":{"input_tokens":12,"output_tokens":34,"total_tokens":46}}
```

```text
event: error
data: {"result_code":"provider_rate_limited","result_message":"The selected provider is rate limiting requests.","error_origin":"provider","error_http_status":429,"provider":"vertex_ai","provider_error_code":"RESOURCE_EXHAUSTED","retry_after_seconds":null,"detail":"vertex ai request failed (429 RESOURCE_EXHAUSTED): quota exceeded"}
```

Status codes:
- `400`: request validation that fails before a chat turn can be created
- `401`: no valid session
- `403`: missing capability
- `404`: `chat_history_id` does not belong to the current user
- `409`: auth session conflict
- `422`: schema validation failure, such as message content exceeding the request limit

After a chat turn is created, request-in-progress, Redis rate-limit, provider-configuration, and provider-execution failures are returned as SSE `error` events and persisted on the assistant `chat_messages` row with `result_code`, `result_message`, `error_origin`, `error_http_status`, `provider_error_code`, and `retry_after_seconds`.

## Tool and Provider Notes
- exposed hosted tool ids are model-specific and currently include `web_search`, `retrieval`, `code_execution`, and `url_context`
- `web_search` maps to the provider-native web search tool
- Vertex `retrieval` works when `VERTEX_AI_RAG_CORPORA` is configured and the selected model exposes it
- OpenAI `retrieval` maps to Responses API `file_search` and requires `OPENAI_VECTOR_STORE_IDS`
- `code_execution` maps to the provider-native code execution tool
- Vertex `url_context` maps to Gemini URL context and does not add env requirements
- exposed Gemini public model ids are `gemini-3.1-pro-preview`, `gemini-3-flash-preview`, and `gemini-2.5-flash`
- exposed OpenAI public model ids are `gpt-5.4`, `gpt-5.4-mini`, and `gpt-5-mini`
- exposed Anthropic public model ids are `claude-opus-4-7`, `claude-sonnet-4-6`, and `claude-haiku-4-5`
- `claude-opus-4-7` is intentionally exposed as unavailable until the API model is available
- Anthropic exposes `web_search` and `code_execution`; it does not expose `retrieval`
- Microsoft auth is backend-owned and optional until its env vars are configured
- usage endpoints are not registered
