# API

Active HTTP surface exposed through frontend NGINX and reached through sibling `root-proxy`.

## Base
- Public host: `https://ai.nextinsol.com`
- API prefix: `/api/v1`
- Auth: browser session cookie only
- Cookie name: `session_id`

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
      "id": "gemini",
      "provider": "vertex_ai",
      "display_name": "Gemini",
      "available": true,
      "default": true,
      "tools": [
        {
          "id": "rag",
          "display_name": "RAG",
          "available": true
        }
      ]
    },
    {
      "id": "chatgpt",
      "provider": "openai",
      "display_name": "ChatGPT",
      "available": false,
      "default": false,
      "tools": []
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
    "display_name": "Guest-7AF3C1",
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
  "login_required": true
}
```

### `POST /api/v1/auth/login/guest`
- Creates a guest user and session
- Sets the `session_id` cookie

### `GET /api/v1/auth/login/microsoft`
- Starts a backend-owned Microsoft OAuth authorization-code redirect
- Accepts optional query `return_to=/some/path`
- Responds with `302` to Microsoft or back to the SPA with `auth_error`

### `GET /api/v1/auth/callback/microsoft`
- Handles the Microsoft OAuth callback
- Exchanges the authorization code on the backend
- Creates or reuses a local human user
- Sets the local `session_id` cookie
- Responds with `302` back to the SPA

### `POST /api/v1/auth/logout`
- Deletes the current session and clears the cookie
- Returns `204`

### `POST /api/v1/chat/completions`
- Protected endpoint
- Requires capability `chat:send`
- Request body:

```json
{
  "model_id": "gemini",
  "tool_ids": ["rag"],
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
- `model_id` may be omitted or `null`
- `tool_ids` is optional
- at least one `user` message is required
- the last message must be a `user` message

Response type:
- `text/event-stream`

Events:

```text
event: start
data: {"model":"gemini","provider":"vertex_ai"}
```

```text
event: delta
data: {"delta_text":"partial output"}
```

```text
event: done
data: {"model":"gemini","provider":"vertex_ai","finish_reason":"STOP","usage":{"input_tokens":12,"output_tokens":34,"total_tokens":46}}
```

```text
event: error
data: {"detail":"vertex ai request failed"}
```

Status codes:
- `400`: invalid payload, unsupported model, unsupported tool selection
- `401`: no valid session
- `403`: missing capability
- `409`: chat already in progress for the same session
- `429`: chat rate limit exceeded
- `503`: Redis coordination unavailable or provider not configured

## Tool and Provider Notes
- `rag` is the only exposed tool id
- `rag` only works when `VERTEX_AI_RAG_CORPORA` is configured
- `chatgpt` appears in the catalog as a placeholder only
- Microsoft auth is backend-owned and optional until its env vars are configured
- usage endpoints are not registered
