# API

Base host:
- upstream HTTPS host that fronts this stack
- direct local receive port: `http://localhost:8081`

Versioned prefix:
- `/api/v1`

Auth model:
- session-cookie based
- cookie name: `session_id`
- cookie flags in default Compose: `HttpOnly`, `Secure`, `SameSite=Strict`

## Active Routes

### `GET /health`
- Purpose: backend liveness check
- Example response:

```json
{
  "status": "ok",
  "service": "proxy-api"
}
```

### `GET /api/v1/models`
- Purpose: list models exposed by the backend
- Current behavior: returns a single public id, `vertex-default`

### `GET /api/v1/auth/me`
- Purpose: return current session state from the incoming `session_id` cookie
- `200`: authenticated session
- `401`: no valid session

### `POST /api/v1/auth/login/guest`
- Purpose: create a guest user and guest session
- Result: sets the `session_id` cookie
- `200`: guest session created

### `POST /api/v1/auth/logout`
- Purpose: delete the current session and clear the cookie
- `204`: logout processed

### `POST /api/v1/chat/completions`
- Purpose: protected streaming chat endpoint
- Requires: authenticated session with capability `chat:send`
- Request body:

```json
{
  "model": "vertex-default",
  "use_rag": false,
  "messages": [
    {
      "role": "user",
      "content": "hello"
    }
  ]
}
```

- Response: `text/event-stream`
- SSE events:
  - `start`
  - `delta`
  - `done`
  - `error`
- If `use_rag=true` and `VERTEX_AI_RAG_CORPORA` is configured, the backend attaches a Vertex AI RAG retrieval tool to the provider request before streaming begins

- Error status:
  - `400`: invalid payload or unsupported model
  - `401`: no valid session
  - `403`: missing capability
  - `409`: chat already in progress for the session
  - `429`: chat rate limit exceeded
  - `503`: Redis coordination unavailable or Vertex not configured

## Current Session Policy
- guest idle timeout: `6 hours`
- guest absolute lifetime: `24 hours`
- backend stores only a hash of the session key

## Not Active Yet
- `usage` and quota endpoints exist as scaffolds only
- Microsoft auth callback flow is not registered
- Vertex AI RAG corpus creation/import automation is not exposed by this API
